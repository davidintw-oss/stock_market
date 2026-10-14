#!/usr/bin/env python3
"""從 data/config.json 產生 docs/risk-indicators.md，避免門檻與文件不一致。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "data", "config.json")
OUT = os.path.join(ROOT, "docs", "risk-indicators.md")

PREAMBLE = """# 十大風險指標

門檻與權重的唯一來源是 [`data/config.json`](../data/config.json)。這份文件由
`scripts/gen_indicator_doc.py` 產生，不要手改。

## 權重怎麼排

排序依據是「這個指標對**大幅回檔的機率與深度**的解釋力」，不是它預測轉折時間的能力。
沒有指標能預測時間點。

| 層級 | 指標 | 為什麼排這個順序 |
|---|---|---|
| 第一層：結構 | PB、融資餘額、PE、年線乖離 | 評價與槓桿決定「如果下跌，會跌多深」。這是跨市場、跨年代最穩定的統計關係。 |
| 第二層：集中與資金 | 台積電集中度、外資流向 | 台股的特殊風險。決定「下跌時有沒有分散保護」。 |
| 第三層：體質 | 市場廣度、量價背離 | 頭部結構的徵兆。訊號較早，但假訊號多。 |
| 第四層：情緒 | 股債利差、當沖熱度 | 輔助確認。單獨出現不足以行動。 |

**槓桿（第 2 名）的權重接近評價（第 1 名）的理由：** 評價決定下跌的深度，槓桿決定下跌的
速度。強制平倉會把 10% 的修正放大成 25% 的崩跌。歷次台股急殺，融資餘額都在高檔。

## 怎麼用

1. 每個指標只有兩種狀態：🔴 達到門檻，🟢 未達到。沒有中間值，避免自己找理由。
2. 資料缺失顯示 ⚪，不計入分數，但會降低覆蓋率。覆蓋率低於 70 分時，分數只能當參考。
3. 分數 = 所有紅燈的權重加總（0–100）。對應動作見 [`docs/ladder.md`](ladder.md)。
4. 門檻每季檢討一次。**不要在盤中改門檻。** 盤中改門檻等於沒有門檻。

## 已知限制（誠實說明）

- **門檻是個人設定值，不是統計最適解。** 台股的大型頭部樣本只有 5 到 6 次，任何「最佳門檻」
  都是對小樣本過度配適。這些數字是數量級上的合理設定，不是校準過的參數。
- **指標之間有相關性。** PB 與 PE 常同時轉紅，融資與當沖也會。所以分數在高檔會跳得比較快，
  這是刻意的設計，不是錯誤。
- **這套系統不預測時間。** 它只回答「現在承受的風險有多大」。
- **資料有時間落差。** 月頻指標（當沖、集中度、殖利率）最多落後一個月。追蹤表會顯示每個
  指標的資料日期。

---

## 指標明細
"""


def main():
    with open(CONFIG, encoding="utf-8") as fh:
        config = json.load(fh)
    parts = [PREAMBLE]
    for ind in config["indicators"]:
        parts.append(f"\n### {ind['rank']}. {ind['name']}　｜　權重 {ind['weight']}\n")
        parts.append(f"- **紅燈門檻**：{ind['threshold_text']}")
        parts.append(f"- **檢查頻率**：{ind['cadence']}")
        parts.append(f"- **資料來源**：{ind['source']}")
        keys = "、".join(
            f"`{k}`（{m['label']}，單位 {m.get('unit', '')}）" for k, m in ind["metrics"].items()
        )
        parts.append(f"- **輸入欄位**：{keys}")
        parts.append(f"\n{ind['why']}\n")
    parts.append("\n---\n")
    parts.append("## 輸入指令範例\n")
    parts.append("```bash")
    parts.append("python3 scripts/risk_check.py \\")
    all_keys = [k for ind in config["indicators"] for k in ind["metrics"]]
    parts.append("  --set index=48341.31 " + " ".join(f"{k}=" for k in all_keys[:4]) + " \\")
    parts.append("  --asof concentration=2026-04-30")
    parts.append("```\n")
    parts.append("> 這是個人紀律工具，不是投資建議。\n")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    print(f"寫入 {OUT}（{len(config['indicators'])} 個指標，權重合計 "
          f"{sum(i['weight'] for i in config['indicators'])}）")


if __name__ == "__main__":
    main()
