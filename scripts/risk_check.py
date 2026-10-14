#!/usr/bin/env python3
"""台股風險燈號檢查器。

用法：
  # 輸入當日數值，更新燈號
  python3 scripts/risk_check.py --set pb=4.19 pe=26.64 index=48341 --set margin_chg_20d=8.2

  # 只看結果，不寫檔
  python3 scripts/risk_check.py --set pb=4.6 --dry-run

  # 顯示目前狀態
  python3 scripts/risk_check.py --show

輸出最後一行是機器可讀的結論：
  RESULT changes=<變化數> score=<風險分數> zone=<區間>
燈號沒有變化時 changes=0，排程就不發通知。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "data", "config.json")
STATE = os.path.join(ROOT, "data", "state.json")
HISTORY = os.path.join(ROOT, "data", "history.csv")
CHECKLIST = os.path.join(ROOT, "CHECKLIST.md")

RED, GREEN, GREY = "🔴", "🟢", "⚪"
TRUE_WORDS = {"true", "yes", "y", "1", "是", "t"}
FALSE_WORDS = {"false", "no", "n", "0", "否", "f"}


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def parse_value(raw: str):
    low = raw.strip().lower()
    if low in TRUE_WORDS:
        return True
    if low in FALSE_WORDS:
        return False
    if low in {"", "na", "n/a", "none", "null", "-"}:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return raw


def evaluate(rule, metrics):
    """三值邏輯：True=紅燈條件成立，False=不成立，None=資料不足。"""
    op = rule["op"]
    if op in {"any", "all"}:
        results = [evaluate(sub, metrics) for sub in rule["of"]]
        if op == "any":
            if True in results:
                return True
            return None if None in results else False
        if False in results:
            return False
        return None if None in results else True

    value = metrics.get(rule["metric"])
    if value is None:
        return None
    if op == "gte":
        return float(value) >= rule["value"]
    if op == "lte":
        return float(value) <= rule["value"]
    if op == "is_true":
        return bool(value)
    if op == "is_false":
        return not bool(value)
    raise ValueError(f"未知的運算子: {op}")


def zone_for(score, bands):
    for band in bands:
        if band["min"] <= score <= band["max"]:
            return band
    return bands[-1]


def light_of(verdict):
    return {True: RED, False: GREEN, None: GREY}[verdict]


def fmt(value, unit=""):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{text}{unit}"


def build_rows(config, metrics, asof=None):
    asof = asof or {}
    rows = []
    for ind in config["indicators"]:
        verdict = evaluate(ind["rule"], metrics)
        values = ", ".join(
            f"{meta['label']} {fmt(metrics.get(key), meta.get('unit', ''))}"
            for key, meta in ind["metrics"].items()
        )
        rows.append({
            "id": ind["id"],
            "rank": ind["rank"],
            "name": ind["name"],
            "weight": ind["weight"],
            "threshold": ind["threshold_text"],
            "verdict": verdict,
            "light": light_of(verdict),
            "values": values,
            "labels": "、".join(m["label"] for m in ind["metrics"].values()),
            "why": ind["why"],
            "source": ind["source"],
            "cadence": ind["cadence"],
            "asof": asof.get(ind["id"], ""),
        })
    return rows


def render_checklist(config, rows, metrics, score, covered, band, today, changes):  # noqa: PLR0913
    port = config["portfolio"]
    out = []
    out.append("# 台股風險燈號 — 每日追蹤表")
    out.append("")
    out.append(f"- 更新日期：**{today}**")
    out.append(f"- 加權指數：**{fmt(metrics.get('index'))}**（基準 {port['baseline_index']:,} / {port['baseline_date']}）")
    out.append(f"- 風險分數：**{score} / 100**（資料覆蓋 {covered} 分）")
    out.append(f"- 所在區間：**{band['zone']}**")
    out.append(f"- 建議動作：{band['action']}")
    out.append("")
    if changes:
        out.append("## ⚠️ 本次燈號變化")
        out.append("")
        for ch in changes:
            out.append(f"- {ch['light_before']} → {ch['light_after']}　**{ch['name']}**（權重 {ch['weight']}）")
        out.append("")
    else:
        out.append("本次燈號無變化。")
        out.append("")
    out.append("## 十大風險指標（由上到下＝風險權重由高到低）")
    out.append("")
    out.append("| # | 燈號 | 指標 | 權重 | 紅燈門檻 | 目前數值 | 資料日期 | 頻率 |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        out.append(
            f"| {r['rank']} | {r['light']} | {r['name']} | {r['weight']} | {r['threshold']} "
            f"| {r['values']} | {r['asof'] or '—'} | {r['cadence']} |"
        )
    out.append("")
    grey = [r for r in rows if r["verdict"] is None]
    if grey:
        out.append("### ⚪ 資料不足的指標")
        out.append("")
        for r in grey:
            out.append(f"- **{r['name']}**（權重 {r['weight']}）— 需要：{r['labels']}　來源：{r['source']}")
        out.append("")
        out.append("灰燈不計入風險分數。覆蓋率低於 70 分時，分數要當成參考值，不要直接拿來減碼。")
        out.append("")
    out.append("## 分數對應動作")
    out.append("")
    out.append("| 分數 | 區間 | 動作 |")
    out.append("|---|---|---|")
    for b in config["score_bands"]:
        out.append(f"| {b['min']}–{b['max']} | {b['zone']} | {b['action']} |")
    out.append("")
    out.append("點位階梯與反向回補規則見 [docs/ladder.md](docs/ladder.md)。")
    out.append("指標定義、門檻理由與資料來源見 [docs/risk-indicators.md](docs/risk-indicators.md)。")
    out.append("")
    out.append("> 這是個人紀律工具，不是投資建議。門檻是自己設的參數，不是市場定律。")
    out.append("")
    return "\n".join(out)


def append_history(today, metrics, rows, score, covered, band):
    exists = os.path.exists(HISTORY)
    fields = ["date", "index", "score", "covered", "zone"] + [r["id"] for r in rows]
    with open(HISTORY, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        if not exists:
            writer.writeheader()
        row = {
            "date": today,
            "index": metrics.get("index", ""),
            "score": score,
            "covered": covered,
            "zone": band["zone"],
        }
        for r in rows:
            row[r["id"]] = {True: "RED", False: "GREEN", None: "GREY"}[r["verdict"]]
        writer.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser(description="台股風險燈號檢查器")
    ap.add_argument("--set", nargs="+", default=[], metavar="KEY=VALUE",
                    help="輸入指標數值，可重複使用。例：--set pb=4.19 pe=26.6")
    ap.add_argument("--from-json", help="從 JSON 檔讀入數值")
    ap.add_argument("--asof", nargs="+", default=[], metavar="ID=DATE",
                    help="標註某個指標的資料日期。例：--asof concentration=2026-04-30")
    ap.add_argument("--date", default=date.today().isoformat(), help="資料日期，預設今天")
    ap.add_argument("--dry-run", action="store_true", help="只顯示結果，不寫入任何檔案")
    ap.add_argument("--show", action="store_true", help="顯示上次儲存的狀態後結束")
    ap.add_argument("--reset", action="store_true", help="清空舊數值，只用這次輸入的值")
    args = ap.parse_args()

    config = load_json(CONFIG)
    if config is None:
        print("找不到 data/config.json", file=sys.stderr)
        return 2
    state = load_json(STATE, {"date": None, "metrics": {}, "lights": {}}) or {}

    if args.show:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    metrics = {} if args.reset else dict(state.get("metrics", {}))
    if args.from_json:
        metrics.update(load_json(args.from_json, {}) or {})
    for item in args.set:
        if "=" not in item:
            print(f"格式錯誤，需要 KEY=VALUE：{item}", file=sys.stderr)
            return 2
        key, raw = item.split("=", 1)
        metrics[key.strip()] = parse_value(raw)

    asof = dict(state.get("asof", {}))
    for item in args.asof:
        if "=" in item:
            key, raw = item.split("=", 1)
            asof[key.strip()] = raw.strip()

    rows = build_rows(config, metrics, asof)
    score = sum(r["weight"] for r in rows if r["verdict"] is True)
    covered = sum(r["weight"] for r in rows if r["verdict"] is not None)
    band = zone_for(score, config["score_bands"])

    before = state.get("lights", {})
    changes = []
    for r in rows:
        old = before.get(r["id"])
        if old is not None and old != r["light"]:
            changes.append({
                "name": r["name"], "weight": r["weight"],
                "light_before": old, "light_after": r["light"],
            })

    print(f"日期 {args.date}　指數 {fmt(metrics.get('index'))}　風險分數 {score}/100"
          f"（覆蓋 {covered}）　{band['zone']}")
    for r in rows:
        stamp = f"　(資料 {r['asof']})" if r["asof"] else ""
        print(f"  {r['light']} [{r['weight']:>2}] {r['name']}　門檻 {r['threshold']}　現值 {r['values']}{stamp}")
    if changes:
        print("\n燈號變化：")
        for ch in changes:
            print(f"  {ch['light_before']} → {ch['light_after']}  {ch['name']}（權重 {ch['weight']}）")
        print(f"\n建議動作：{band['action']}")
    else:
        print("\n燈號無變化，不需通知。")

    if not args.dry_run:
        new_state = {
            "date": args.date,
            "score": score,
            "covered": covered,
            "zone": band["zone"],
            "metrics": metrics,
            "asof": asof,
            "lights": {r["id"]: r["light"] for r in rows},
        }
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump(new_state, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        append_history(args.date, metrics, rows, score, covered, band)
        with open(CHECKLIST, "w", encoding="utf-8") as fh:
            fh.write(render_checklist(config, rows, metrics, score, covered, band, args.date, changes))

    print(f"RESULT changes={len(changes)} score={score} zone={band['zone']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
