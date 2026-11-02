#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客户沟通记录风险扫描：识别红线信号、需留意信号与正向信号。

输入可以是聊天记录文件、--text 参数，或标准输入。按行扫描，输出命中位置与处理建议。

用法：
    python risk_scan.py --file chat.txt
    python risk_scan.py --text "你先做着，做好了我们再谈钱"
    type chat.txt | python risk_scan.py
"""

import argparse
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# (分组, 名称, 正则, 解读)
RULES = [
    # ---------- 红线：命中即建议婉拒 ----------
    ("红线", "先做后付", r"(先做|先干|先开发|先帮我做|先出个|做好了|做完(了)?(再|之后)).{0,14}(谈|说|聊|算)?\s*(钱|费用|价格|报价|预算)", "白嫖概率接近 100%，没有预算就没有优先级"),
    ("红线", "拒绝书面", r"(语音|打电话|电话里|电话沟通).{0,8}(聊|说|沟通|就行|比较好)|不用(写|发|整理)(邮件|文档|需求)|口头(说|讲|答应)就行", "需求变更时你会听到\"我没说过\""),
    ("红线", "纯比价", r"(别人|有人|其他|另一家|之前那家|朋友|同行).{0,10}(报价|价格|才报|只要|给).{0,6}\d|报价(是|才).{0,4}(你的)?(一半|三分之|几分之)", "决策逻辑是谁便宜找谁，永远不会有满意价格"),
    ("红线", "换过多家外包", r"(换过|换了|找过).{0,5}(三|3|四|4|几|好几).{0,4}(家|个|波)", "要么甲方挑剔，要么需求本身不成立"),
    ("红线", "说不清目的", r"(先做出来|试试看|做着玩|看看效果|先上线再说|别人都有|大家都做)", "项目优先级低，随时搁置，你的排期白排"),
    ("红线", "低估工作量", r"(这个|这|那个).{0,6}(很|挺|超)?简单(吧|嘛|的嘛|啊)|简单(搞|弄|做)一下|顺手(做|弄|加)", "不认可工作量的人，也不会认可你花的时间"),

    # ---------- 需留意：提高定金、收窄范围 ----------
    ("需留意", "预算缺失或含糊", r"(不清楚|不知道|你(说|定|报)|看着给|市场价).{0,10}(预算|价格|报价|多少钱)|(预算|价格|报价).{0,6}(不清楚|不知道|没定|待定|再说|你(说|定|报))", "连预算都没有的项目，优先级通常也最低"),
    ("需留意", "无明确期限", r"(不着急|慢慢来|有时间就|不急|什么时候都行)", "没有 deadline = 没有验收压力 = 尾款无限拖"),
    ("需留意", "免费试探", r"(免费|白帮忙|帮我看(一下|看)|先试用|试做|练手)", "免费开口子 = 免费 on-call"),
    ("需留意", "范围蔓延预兆", r"(顺便|再加|能不能再|另外再|既然做了|一起做(了)?吧|改一下又不难)", "范围蔓延的起点，必须走变更流程"),
    ("需留意", "压价", r"(便宜(点|些)|能不能少|打个折|优惠|太高了|超预算)", "先降范围，不降价格"),
    ("需留意", "拖延付款", r"(下周|月底|走完流程|财务|老板批).{0,8}(付|打款|结|给钱)|钱(马上|很快)(到|就)", "付款条件要绑定可验证事件，不绑日期"),
    ("需留意", "多人决策", r"(问一下|问下|跟|和).{0,6}(老板|领导|合伙人|技术|他们).{0,6}(确认|商量|汇报|决定)", "确认可能被推翻，合同需指定唯一授权代表"),
    ("需留意", "只说\"好用\"这类模糊词", r"(不好用|不满意|感觉(不对|不行)|体验不好|差(点|点意思))", "模糊词可被定义成任何东西，验收标准必须可判定"),

    # ---------- 正向信号 ----------
    ("正向", "有具体预算", r"预算.{0,8}\d|\d+(\.\d+)?\s*(万|千|k|K|元|块)", "有预期就有谈判空间"),
    ("正向", "有明确期限", r"(\d+月\d+[日号]|\d+/\d+|下(周|个?月)|月底|季度末|上线前|deadline|必须.{0,6}(上线|交付))", "有截止日期和决策压力，交付意愿强"),
    ("正向", "有可量化目标", r"(转化率|提升|降低|节省|减少|提高到|做到|涨到).{0,8}\d|(\d+%|\d+倍)", "有可量化指标 = 靠谱客户，也给了你验收抓手"),
    ("正向", "认作品而来", r"(看到你(的|写的)|用过你|你那个|你写的|你的(项目|工具|文章)|朋友推荐|别人推荐)", "信任成本接近零，价格敏感度显著更低"),
    ("正向", "愿意书面确认", r"(邮件|文档|合同|确认书|签字|盖章|书面)", "愿意留痕的客户，后续扯皮概率低"),
]

COMPILED = [(g, n, re.compile(p), note) for g, n, p, note in RULES]


def read_input(args):
    if args.text:
        return args.text
    if args.file:
        with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def scan(text):
    lines = [ln.strip() for ln in text.splitlines()]
    hits = []
    for idx, line in enumerate(lines, 1):
        if not line:
            continue
        line_hits = []
        for group, name, rx, note in COMPILED:
            m = rx.search(line)
            if m:
                line_hits.append({
                    "line": idx,
                    "group": group,
                    "name": name,
                    "match": m.group(0),
                    "note": note,
                    "text": line[:80],
                })
        # 同一行已命中风险信号时，不再计入正向信号，避免"月底走完流程就打款"被算成有期限
        if any(h["group"] in ("红线", "需留意") for h in line_hits):
            line_hits = [h for h in line_hits if h["group"] != "正向"]
        hits.extend(line_hits)
    return hits


def report(hits):
    order = {"红线": 0, "需留意": 1, "正向": 2}
    hits = sorted(hits, key=lambda h: (order[h["group"]], h["line"]))

    red = [h for h in hits if h["group"] == "红线"]
    warn = [h for h in hits if h["group"] == "需留意"]
    good = [h for h in hits if h["group"] == "正向"]

    if not hits:
        print("未命中任何已知信号。")
        print("提醒：脚本只做文本匹配，判断仍要看三问的答案——预算数字、时间点、可量化目标。")
        return 0

    for group, title in (("红线", "红线信号（命中即建议婉拒或大幅提高门槛）"),
                         ("需留意", "需留意信号（提高定金比例、收窄范围、补书面确认）"),
                         ("正向", "正向信号")):
        items = [h for h in hits if h["group"] == group]
        if not items:
            continue
        print("\n【{}】".format(title))
        print("-" * 62)
        for h in items:
            print("第 {:<3} 行  {:<10} 命中：{}".format(h["line"], h["name"], h["match"]))
            print("           解读：{}".format(h["note"]))
        print()

    print("=" * 62)
    if red:
        print("结论：命中 {} 条红线信号 → 建议婉拒，或至少要求提高定金至 50% 并大幅收窄范围。".format(len(red)))
        print("      红线命中 2 条及以上，不要接。省下的时间比这单的钱值。")
    elif len(warn) >= 2:
        print("结论：命中 {} 条需留意信号 → 条件接。".format(len(warn)))
        print("      条件：定金不低于 50%、需求文档必须书面确认、验收期限写进合同。")
    elif warn:
        print("结论：1 条需留意信号 → 可接，但把这一条在合同里补掉。")
    else:
        core = {"有具体预算", "有明确期限", "有可量化目标"}
        got = sorted({h["name"] for h in good} & core)
        if len(got) == 3:
            print("结论：三问齐了（预算 / 时间点 / 可量化目标都有明确回答）→ 可进入报价阶段。")
            print("      下一步：出报价单 + 合同，定金不低于 30%，到账再开工。")
        else:
            print("结论：未命中红线 → 可继续推进，但三问还缺 {}。".format(
                "、".join(n for n in ["有具体预算", "有明确期限", "有可量化目标"] if n not in got)))

    print("\n仍需人工确认的两件事：")
    print("  1. 他有没有在周末或深夜给你发需求？（没有边界感的客户，交付后也没有）")
    print("  2. 对接人是不是付款人？若不是，要确认谁是授权代表。")
    if good:
        names = []
        for h in good:
            if h["name"] not in names:
                names.append(h["name"])
        print("  正向信号 {} 条：{}。说明这单的基础质量不错，别只盯风险。".format(
            len(good), " / ".join(names)))
    return 0


def main():
    ap = argparse.ArgumentParser(description="客户沟通记录风险扫描")
    ap.add_argument("--file", help="聊天记录文本文件路径")
    ap.add_argument("--text", help="直接传入一段文本")
    args = ap.parse_args()

    text = read_input(args)
    if not text.strip():
        print("没有可扫描的文本。用 --file 指定文件，或 --text 传入文本，或通过管道输入。")
        return 1
    return report(scan(text))


if __name__ == "__main__":
    sys.exit(main())
