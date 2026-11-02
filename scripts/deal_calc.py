#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接单金额计算器：分期拆分 / 中途叫停结算 / 维护报价区间。

纯标准库，无网络依赖。金额一律按元计算，四舍五入到分。

用法：
    python deal_calc.py split --total 16000
    python deal_calc.py split --total 16000 --plan 30/40/30
    python deal_calc.py settle --total 16000 --progress 60 --cost 2000 --received 4800
    python deal_calc.py maintain --total 16000
"""

import argparse
import sys
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CONTRIB = ("定金", "中期款", "尾款")


def dwidth(s):
    """按终端显示宽度计算字符串长度（中文占 2 列）。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s, width, right=False):
    gap = max(0, width - dwidth(s))
    return (" " * gap + s) if right else (s + " " * gap)


def row(cells, widths, rights=None):
    rights = rights or [False] * len(cells)
    return "  ".join(pad(str(c), w, r) for c, w, r in zip(cells, widths, rights)).rstrip()


def money(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt(x):
    d = money(x)
    if d == d.to_integral_value():
        return "¥{:,.0f}".format(d)
    return "¥{:,.2f}".format(d)


def parse_plan(text):
    raw = text.replace("，", ",").replace("/", ",").replace("%", "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    try:
        plan = [Decimal(p) for p in parts]
    except Exception:
        raise ValueError("分期比例格式不对，示例：50/30/20")
    if len(plan) not in (2, 3):
        raise ValueError("分期只能写 2 段或 3 段，示例：50/30/20 或 50/50")
    total = sum(plan)
    if total != Decimal(100):
        raise ValueError("分期比例合计必须是 100，当前合计 {}".format(total))
    return plan


def cmd_split(args):
    total = money(args.total)
    if total <= 0:
        raise ValueError("合同金额必须大于 0")
    plan = parse_plan(args.plan)

    amounts = [money(total * p / Decimal(100)) for p in plan]
    diff = total - sum(amounts)
    if diff != 0:
        amounts[0] += diff  # 尾差并入定金，保证合计严格等于合同额

    labels = CONTRIB[: len(plan)] if len(plan) == 3 else ("定金", "尾款")

    print("合同总额：{}".format(fmt(total)))
    print("分期方案：{}".format(" / ".join(str(int(p)) + "%" for p in plan)))
    print("-" * 44)
    for label, p, amt in zip(labels, plan, amounts):
        print(row([label, "{}%".format(int(p)), fmt(amt)], [6, 5, 11], [False, True, True]))
    print("-" * 44)
    print(row(["合计", "100%", fmt(sum(amounts))], [6, 5, 11], [False, True, True]))

    deposit = amounts[0]
    if deposit / total < Decimal("0.3"):
        print("\n[风险] 定金比例低于 30%，不建议接受。先做后付的白嫖概率极高。")
    print("\n提醒：{0} 到账当天才开工。没到账不排期、不建仓库、不写需求。".format(fmt(deposit)))
    if len(plan) == 3:
        print("中期款绑定事件：进度 60%~70% 的中期交付验收通过后 3 个工作日内。")


def cmd_settle(args):
    total = money(args.total)
    progress = Decimal(str(args.progress))
    if not (0 <= progress <= 100):
        raise ValueError("进度请填 0~100")
    cost = money(args.cost)
    received = money(args.received)

    done = money(total * progress / Decimal(100))
    payable = money(done + cost)
    balance = money(payable - received)

    print("合同总额：{}".format(fmt(total)))
    pct = int(progress) if progress == progress.to_integral_value() else progress
    print("已完成进度：{}%".format(pct))
    print("-" * 44)
    print(row(["已完成部分折价", fmt(done)], [16, 12], [False, True]))
    print(row(["未摊销前期成本", fmt(cost)], [16, 12], [False, True]))
    print(row(["应结总额", fmt(payable)], [16, 12], [False, True]))
    print(row(["已收款项", fmt(received)], [16, 12], [False, True]))
    print("-" * 44)
    if balance >= 0:
        print(row(["待收余额", fmt(balance)], [16, 12], [False, True]) + "   <- 甲方还应支付")
    else:
        print(row(["待收余额", fmt(abs(balance))], [16, 12], [False, True]) + "   <- 我方应退还")

    if payable > total:
        print("\n[注意] 应结总额已超过合同额，检查前期成本是否重复计入。")
        print("       若前期成本已在阶段报价中摊销，此处应填 0。")

    collected_ratio = (received / total * 100) if total else Decimal(0)
    print("\n已收占比：{}%".format(int(collected_ratio)))
    if balance > 0:
        print("话术：截至 {}% 已完成部分折价 {done}，加上前期已发生的环境搭建与方案成本 {cost}，"
              "合计 {payable}，已收 {received}，请结清 {balance} 后我移交已完成部分的可运行成果。".format(
                  pct, done=fmt(done), cost=fmt(cost),
                  payable=fmt(payable), received=fmt(received), balance=fmt(balance)))


def cmd_maintain(args):
    total = money(args.total)
    low_rate, high_rate = Decimal("0.05"), Decimal("0.10")
    low = money(total * low_rate)
    high = money(total * high_rate)

    print("项目总价：{}".format(fmt(total)))
    print("维护报价区间（项目总价的 5%~10% / 月）")
    print("-" * 44)
    print(row(["周期", "按 5%", "按 10%"], [8, 11, 11], [False, True, True]))
    print(row(["月度", fmt(low), fmt(high)], [8, 11, 11], [False, True, True]))
    print(row(["季度", fmt(low * 3), fmt(high * 3)], [8, 11, 11], [False, True, True]))
    print(row(["半年", fmt(low * 6), fmt(high * 6)], [8, 11, 11], [False, True, True]))
    print("-" * 44)
    print("按次服务：¥500 ~ ¥2,000 / 次（按复杂度）")
    print("\n签约建议：按季度签，不做月付。月付的对账与催款管理成本高于收益。")
    print("报价话术：维护是项目总价的 5%~10% 每月，包含 bug 修复、小调整和数据备份，按季度签。")


def main():
    ap = argparse.ArgumentParser(
        description="接单金额计算器：分期拆分 / 中途叫停结算 / 维护报价区间")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("split", help="按比例拆分分期金额")
    p1.add_argument("--total", required=True, type=float, help="合同总额")
    p1.add_argument("--plan", default="50/30/20", help="分期比例，默认 50/30/20")
    p1.set_defaults(func=cmd_split)

    p2 = sub.add_parser("settle", help="中途叫停按比例结算")
    p2.add_argument("--total", required=True, type=float, help="合同总额")
    p2.add_argument("--progress", required=True, type=float, help="已完成进度 0~100")
    p2.add_argument("--cost", default=0, type=float, help="未摊销的前期准备成本")
    p2.add_argument("--received", default=0, type=float, help="已收款项")
    p2.set_defaults(func=cmd_settle)

    p3 = sub.add_parser("maintain", help="维护报价区间")
    p3.add_argument("--total", required=True, type=float, help="项目总价")
    p3.set_defaults(func=cmd_maintain)

    args = ap.parse_args()
    try:
        args.func(args)
    except ValueError as e:
        print("参数错误：{}".format(e))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
