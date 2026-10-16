#!/usr/bin/env python3
"""台股風險燈號檢查器。

每個指標只有三種狀態：🔴 達到門檻、🟢 未達到、⚪ 資料不足。
風險分數 = 所有紅燈的權重加總（0–100）。

用法：
  python3 scripts/risk_check.py --set pb=4.08 pe=25.96 index=47111.26
  python3 scripts/risk_check.py --set pb=4.6 --dry-run      # 試算，不寫檔
  python3 scripts/risk_check.py --show                      # 看上次儲存的狀態

最後一行是機器可讀的結論：
  RESULT changes=<變化數> score=<分數> zone=<區間>
changes=0 代表燈號沒有變化，排程就不發通知。
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
LIGHT_NAME = {RED: "RED", GREEN: "GREEN", GREY: "GREY"}
TRUE_WORDS = {"true", "yes", "y", "1", "是", "t"}
FALSE_WORDS = {"false", "no", "n", "0", "否", "f"}
MISSING_WORDS = {"", "na", "n/a", "none", "null", "-"}

# 只有這三種轉換要通知：新增紅燈、紅轉綠、綠轉紅。
# ⚪ → 🟢 只是補上資料，🔴/🟢 → ⚪ 只是資料遺失，兩者都不通知。
NOTIFY_TRANSITIONS = {(GREEN, RED), (RED, GREEN), (GREY, RED)}


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
    if low in MISSING_WORDS:
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


def fmt(value, unit=""):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, str):
        return value
    text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{text}{unit}"


def zone_for(score, bands):
    for band in bands:
        if band["min"] <= score <= band["max"]:
            return band
    return bands[-1]


def build_rows(config, metrics, asof, notes):
    rows = []
    for ind in config["indicators"]:
        verdict = evaluate(ind["rule"], metrics)
        rows.append({
            "id": ind["id"],
            "rank": ind["rank"],
            "name": ind["name"],
            "weight": ind["weight"],
            "threshold": ind["threshold_text"],
            "verdict": verdict,
            "light": {True: RED, False: GREEN, None: GREY}[verdict],
            "values": "，".join(
                f"{m['label']} {fmt(metrics.get(k), m.get('unit', ''))}"
                for k, m in ind["metrics"].items()
            ),
            "labels": "、".join(m["label"] for m in ind["metrics"].values()),
            "missing": "、".join(
                m["label"] for k, m in ind["metrics"].items() if metrics.get(k) is None
            ),
            "source": ind["source"],
            "query": ind.get("query", ""),
            "cadence": ind["cadence"],
            "asof": asof.get(ind["id"], ""),
            "note": notes.get(ind["id"], ""),
        })
    return rows


def render_checklist(config, rows, metrics, score, covered, band, today, changes, quiet):
    port = config["portfolio"]
    out = ["# 台股風險燈號 — 每日追蹤表", ""]
    out.append(f"- 更新日期：**{today}**")
    out.append(f"- 加權指數：**{fmt(metrics.get('index'))}**"
               f"（前波高點 {port['prev_peak_close']:,} / {port['prev_peak_date']}）")
    out.append(f"- 風險分數：**{score} / 100**（資料覆蓋 {covered} 分）")
    out.append(f"- 所在區間：**{band['zone']}**")
    out.append(f"- 建議動作：{band['action']}")
    out.append("")

    if changes:
        out.append("## ⚠️ 本次燈號變化")
        out.append("")
        for ch in changes:
            out.append(f"- {ch['light_before']} → {ch['light_after']}　**{ch['name']}**"
                       f"（權重 {ch['weight']}）")
        out.append("")
    else:
        out.append("本次燈號無變化。")
        out.append("")

    if quiet:
        out.append("<!-- 不通知的狀態變動（補資料或資料遺失） -->")
        for ch in quiet:
            out.append(f"- {ch['light_before']} → {ch['light_after']}　{ch['name']}"
                       f"（僅資料變動，不通知）")
        out.append("")

    out.append("## 十大風險指標（由上到下＝風險權重由高到低）")
    out.append("")
    out.append("| # | 燈號 | 指標 | 權重 | 紅燈門檻 | 目前數值 | 資料日期 |")
    out.append("|---|---|---|---|---|---|---|")
    for r in rows:
        out.append(f"| {r['rank']} | {r['light']} | {r['name']} | {r['weight']} "
                   f"| {r['threshold']} | {r['values']} | {r['asof'] or '—'} |")
    out.append("")

    noted = [r for r in rows if r["note"]]
    if noted:
        out.append("### 資料備註")
        out.append("")
        for r in noted:
            out.append(f"- **{r['name']}**：{r['note']}")
        out.append("")

    grey = [r for r in rows if r["verdict"] is None]
    if grey:
        out.append("### ⚪ 資料不足的指標")
        out.append("")
        for r in grey:
            out.append(f"- **{r['name']}**（權重 {r['weight']}）— 需要：{r['missing']}"
                       f"　來源：{r['source']}")
        out.append("")
        out.append("灰燈不計入風險分數。覆蓋率低於 70 分時，分數要當成參考值，"
                   "不要直接拿來減碼。")
        out.append("")

    out.append("## 分數對應動作")
    out.append("")
    out.append("| 分數 | 區間 | 動作 |")
    out.append("|---|---|---|")
    for b in config["score_bands"]:
        mark = " ←" if b is band else ""
        out.append(f"| {b['min']}–{b['max']} | {b['zone']}{mark} | {b['action']} |")
    out.append("")
    out.append("點位階梯與反向回補規則見 [docs/ladder.md](docs/ladder.md)。")
    out.append("指標定義與權重排序理由見 [docs/risk-indicators.md](docs/risk-indicators.md)。")
    out.append("")
    out.append("> 這是個人紀律工具，不是投資建議。門檻是自己設的參數，不是市場定律。")
    out.append("")
    return "\n".join(out)


def append_history(today, metrics, rows, score, covered, band):
    fields = ["date", "index", "score", "covered", "zone"] + [r["id"] for r in rows]
    rows_out = []
    if os.path.exists(HISTORY):
        with open(HISTORY, encoding="utf-8") as fh:
            rows_out = [r for r in csv.DictReader(fh) if r.get("date") != today]
    record = {
        "date": today,
        "index": metrics.get("index", ""),
        "score": score,
        "covered": covered,
        "zone": band["zone"],
    }
    for r in rows:
        record[r["id"]] = LIGHT_NAME[r["light"]]
    rows_out.append(record)
    rows_out.sort(key=lambda r: r["date"])
    with open(HISTORY, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows_out)


def collect_pairs(items, label):
    out = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"{label} 需要 KEY=VALUE 格式：{item}")
        key, raw = item.split("=", 1)
        out[key.strip()] = raw.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="台股風險燈號檢查器")
    ap.add_argument("--set", nargs="+", default=[], metavar="KEY=VALUE",
                    help="輸入指標數值。例：--set pb=4.08 pe=25.96")
    ap.add_argument("--asof", nargs="+", default=[], metavar="ID=DATE",
                    help="標註指標的資料日期。例：--asof concentration=2026-10-16")
    ap.add_argument("--note", nargs="+", default=[], metavar="ID=TEXT",
                    help="標註資料的取得方式或不確定處。")
    ap.add_argument("--from-json", help="從 JSON 檔讀入數值")
    ap.add_argument("--date", default=date.today().isoformat(), help="資料日期，預設今天")
    ap.add_argument("--dry-run", action="store_true", help="只顯示結果，不寫檔")
    ap.add_argument("--show", action="store_true", help="顯示上次儲存的狀態")
    ap.add_argument("--reset", action="store_true", help="清掉舊數值，只用這次輸入的")
    args = ap.parse_args()

    config = load_json(CONFIG)
    if config is None:
        print("找不到 data/config.json", file=sys.stderr)
        return 2
    state = load_json(STATE, {}) or {}

    if args.show:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    metrics = {} if args.reset else dict(state.get("metrics", {}))
    if args.from_json:
        metrics.update(load_json(args.from_json, {}) or {})
    for key, raw in collect_pairs(args.set, "--set").items():
        metrics[key] = parse_value(raw)
    asof = dict(state.get("asof", {}))
    asof.update(collect_pairs(args.asof, "--asof"))
    notes = dict(state.get("notes", {}))
    notes.update(collect_pairs(args.note, "--note"))

    rows = build_rows(config, metrics, asof, notes)
    score = sum(r["weight"] for r in rows if r["verdict"] is True)
    covered = sum(r["weight"] for r in rows if r["verdict"] is not None)
    band = zone_for(score, config["score_bands"])

    before = state.get("lights", {})
    changes, quiet = [], []
    for r in rows:
        old = before.get(r["id"])
        if old is None or old == r["light"]:
            continue
        entry = {"name": r["name"], "weight": r["weight"],
                 "light_before": old, "light_after": r["light"]}
        if (old, r["light"]) in NOTIFY_TRANSITIONS:
            changes.append(entry)
        else:
            quiet.append(entry)

    print(f"日期 {args.date}　指數 {fmt(metrics.get('index'))}　"
          f"風險分數 {score}/100（覆蓋 {covered}）　{band['zone']}")
    for r in rows:
        stamp = f"　[資料 {r['asof']}]" if r["asof"] else ""
        print(f"  {r['light']} [{r['weight']:>2}] {r['name']}"
              f"　門檻 {r['threshold']}　現值 {r['values']}{stamp}")
    if changes:
        print("\n燈號變化：")
        for ch in changes:
            print(f"  {ch['light_before']} → {ch['light_after']}  "
                  f"{ch['name']}（權重 {ch['weight']}）")
        print(f"\n建議動作：{band['action']}")
    elif quiet:
        print("\n只有資料變動，燈號未變，不需通知：")
        for ch in quiet:
            print(f"  {ch['light_before']} → {ch['light_after']}  {ch['name']}")
    else:
        print("\n燈號無變化，不需通知。")

    if not args.dry_run:
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump({
                "date": args.date, "score": score, "covered": covered,
                "zone": band["zone"], "metrics": metrics, "asof": asof,
                "notes": notes, "lights": {r["id"]: r["light"] for r in rows},
            }, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        append_history(args.date, metrics, rows, score, covered, band)
        with open(CHECKLIST, "w", encoding="utf-8") as fh:
            fh.write(render_checklist(config, rows, metrics, score, covered,
                                      band, args.date, changes, quiet))

    print(f"RESULT changes={len(changes)} score={score} zone={band['zone']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
