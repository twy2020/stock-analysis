# -*- coding: utf-8 -*-
"""Quant Lab 分析小工具：把 skill 里的两个高频动作做成命令。

    qlab.py expr   "<表达式>" --code 000001 [--tail 5] [--start 2025-01-01]
    qlab.py events "<条件表达式>" [--after 10] [--periods 1,2,3,5,10] [--sample 300] [--codes a,b]

它直接复用项目里的 expr.py / feature.py，语义跟页面、回测、筛选完全一致，不另起一套实现。
"""

import argparse
import json
import math
import os
import sqlite3
import sys

DEFAULT_PROJECT = r"C:\Users\35788\Desktop\量化工具"


def die(message):
    sys.stderr.write(message + "\n")
    raise SystemExit(2)


def find_project(explicit):
    candidate = explicit or os.environ.get("QUANTLAB_HOME") or DEFAULT_PROJECT
    candidate = os.path.abspath(os.path.expanduser(candidate))
    if not os.path.isfile(os.path.join(candidate, "expr.py")):
        die("在 %s 里没找到 expr.py——用 --project 指定量化工具目录，或设置 QUANTLAB_HOME" % candidate)
    return candidate


def load_modules(project):
    if project not in sys.path:
        sys.path.insert(0, project)
    import expr
    return expr


def open_db(path, readonly=True):
    if not os.path.isfile(path):
        die("找不到行情库：%s（用 --db 指定 market.db 路径）" % path)
    if readonly:
        from urllib.parse import quote
        uri = "file:%s?mode=ro" % quote(path.replace("\\", "/"), safe="/:")
        conn = sqlite3.connect(uri, uri=True, timeout=15)
    else:
        conn = sqlite3.connect(path, timeout=15)
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def is_num(value):
    # 注意：引擎里的比较、CROSS 这类函数返回的是 int 0/1，不是 float，
    # 只判 float 会把所有命中都漏掉（踩过一次）。
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not math.isnan(value) and not math.isinf(value)


def load_bars(conn, code, limit=None, start=None):
    sql = "SELECT date, open, high, low, close, volume, amount FROM bars WHERE code=?"
    args = [code]
    if start:
        sql += " AND date>=?"
        args.append(start)
    sql += " ORDER BY date"
    rows = conn.execute(sql, args).fetchall()
    if limit and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def build_fields(rows):
    def column(index):
        return [float(r[index]) if r[index] is not None else float("nan") for r in rows]
    return {"open": column(1), "high": column(2), "low": column(3),
            "close": column(4), "volume": column(5), "amount": column(6)}


def fmt(value, digits=3):
    if value is None:
        return "-"
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "inf"
    return ("%%.%df" % digits) % value


def cmd_expr(args):
    project = find_project(args.project)
    expr = load_modules(project)
    conn = open_db(args.db)
    code = args.code.strip().upper().split(".")[0]
    rows = load_bars(conn, code, limit=args.limit, start=args.start)
    name = conn.execute("SELECT name FROM stocks WHERE code=?", (code,)).fetchone()
    conn.close()
    if not rows:
        die("本地库里没有 %s 的数据" % code)
    fields = build_fields(rows)
    series = expr.evaluate(args.expression, fields)
    start_index = max(0, len(rows) - max(1, args.tail))
    hits = [i for i, v in enumerate(series) if is_num(v) and v != 0]
    result = {
        "code": code, "name": name[0] if name else code,
        "range": [rows[0][0], rows[-1][0]], "bars": len(rows),
        "expression": args.expression,
        "hits_total": len(hits),
        "hits_last": [rows[i][0] for i in hits[-10:]],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print("%s %s   共 %d 根 K 线（%s ~ %s）" % (code, name[0] if name else "", len(rows), rows[0][0], rows[-1][0]))
    print("表达式：%s" % args.expression)
    print("全程命中 %d 次；最近命中的日期：%s" % (len(hits), ", ".join(result["hits_last"]) or "无"))
    if any(is_num(v) and v not in (0, 1) for v in series):
        print("提示：这条表达式返回的是数值序列（不是 0/1 判断条件），下面的「命中」只表示值非 0。")
    print()
    print("%-12s %9s %9s %9s %9s %14s  %s" % ("日期", "开", "高", "低", "收", "表达式值", "命中"))
    for i in range(start_index, len(rows)):
        value = series[i]
        flag = ""
        if is_num(value):
            flag = "<-- 命中" if value != 0 else "0"
        print("%-12s %9s %9s %9s %9s %14s  %s" % (
            rows[i][0], fmt(rows[i][1], 2), fmt(rows[i][2], 2), fmt(rows[i][3], 2), fmt(rows[i][4], 2),
            fmt(value, 4), flag))


def cmd_events(args):
    project = find_project(args.project)
    load_modules(project)
    import feature
    periods = [int(x) for x in str(args.periods).split(",") if x.strip()]
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] if args.codes else None
    result = feature.extract(args.db, args.condition, before=args.before, after=args.after,
                             codes=codes, sample=args.sample, periods=periods)
    summary = result["summary"]
    payload = {
        "condition": args.condition,
        "events": summary["events"], "stocks": summary["stocks"],
        "range": summary["range"], "periods": result["periods"],
        "dist": report_dist(result["dist"]),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print("条件：%s" % args.condition)
    print("事件数 %d，扫描股票 %d 只，事件区间 %s ~ %s" % (
        summary["events"], summary["stocks"], summary["range"][0], summary["range"][1]))
    print("事件后 %d 日整体：上涨 %.1f%%  均值 %s%%  中位 %s%%  最好 %s%%  最差 %s%%" % (
        args.after, summary["win_rate"], fmt(summary["avg_after"], 2), fmt(summary["median_after"], 2),
        fmt(summary["best"], 2), fmt(summary["worst"], 2)))
    print("事件后 %.0f 日内最大上冲均值 %s%%，最大回撤均值 %s%%" % (
        args.after, fmt(summary["avg_max_up"], 2), fmt(summary["avg_max_down"], 2)))
    print()
    print("%-8s %8s %9s %9s %9s %10s %10s %10s" % ("事件后", "样本n", "上涨概率", "下跌概率", "持平", "均值%", "中位数%", "标准差%"))
    for item in result["dist"]:
        print("%-8s %8d %8.1f%% %8.1f%% %8.1f%% %10s %10s %10s" % (
            "%d 日" % item["days"], item["n"], item["up_rate"], item["down_rate"], item["flat_rate"],
            fmt(item["mean"], 2), fmt(item["median"], 2), fmt(item["std"], 2)))
    print()
    print("提醒：① 先看 n，n<30 别当结论；② 事件重叠会让 n 虚高；③ 要和同期全市场基准比；")
    print("      ④ 未复权、停牌占位 K 线、剔除 ST 与否都会影响结果（详见 references/pitfalls.md）。")


def report_dist(dist):
    out = []
    for item in dist:
        out.append({
            "days": item["days"], "n": item["n"],
            "up_rate": round(item["up_rate"], 2), "down_rate": round(item["down_rate"], 2),
            "flat_rate": round(item["flat_rate"], 2), "mean": round(item["mean"], 3),
            "median": round(item["median"], 3), "std": round(item["std"], 3),
            "p5": round(item["p5"], 3), "p95": round(item["p95"], 3),
            "hist": [[h["lo"], h["hi"], h["n"]] for h in item["hist"]],
        })
    return out


def main():
    try:
        if not sys.stdout.isatty():
            sys.stdout.reconfigure(errors="replace")   # 管道里输出中文别因为编码炸掉
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Quant Lab 分析小工具（表达式验证 / 事件后收益分布）")
    parser.add_argument("--project", default="", help="量化工具目录，默认取 QUANTLAB_HOME 或 %s" % DEFAULT_PROJECT)
    parser.add_argument("--db", default="", help="market.db 路径，默认取 <项目>/market.db")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    sub = parser.add_subparsers(dest="command")

    common = argparse.ArgumentParser(add_help=False)
    # default=SUPPRESS：子命令后面没写这些参数时不覆盖主解析器上的值，放前放后都能用
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="输出 JSON")
    common.add_argument("--project", default=argparse.SUPPRESS, help="量化工具目录")
    common.add_argument("--db", default=argparse.SUPPRESS, help="market.db 路径")

    expr_parser = sub.add_parser("expr", parents=[common], help="在真实行情上验证一条表达式")
    expr_parser.add_argument("expression")
    expr_parser.add_argument("--code", default="000001")
    expr_parser.add_argument("--tail", type=int, default=5, help="打印最后几根，默认 5")
    expr_parser.add_argument("--limit", type=int, default=0, help="只取最近这么多根，0 = 全部")
    expr_parser.add_argument("--start", default="", help="起始日期 YYYY-MM-DD")

    events_parser = sub.add_parser("events", parents=[common], help="事件后收益概率分布")
    events_parser.add_argument("condition")
    events_parser.add_argument("--before", type=int, default=5)
    events_parser.add_argument("--after", type=int, default=10)
    events_parser.add_argument("--periods", default="1,2,3,5,10")
    events_parser.add_argument("--sample", type=int, default=300)
    events_parser.add_argument("--codes", default="", help="指定股票池，逗号分隔；给了就不抽样")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    project = find_project(args.project)
    if not args.db:
        args.db = os.path.join(project, "market.db")
    if args.command == "expr":
        cmd_expr(args)
    else:
        cmd_events(args)


if __name__ == "__main__":
    main()
