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
| 第三層：體質 | 市場廣度、量價背離 | 頭部結構的徵兆。訊號較早，但假訊號多。只在指數接近高點時有意義。 |
| 第四層：情緒 | 股債利差、當沖熱度 | 輔助確認。單獨出現不足以行動。 |

**槓桿（第 2 名）的權重接近評價（第 1 名）的理由：** 評價決定下跌的深度，槓桿決定下跌的
速度。強制平倉會把 10% 的修正放大成 25% 的崩跌。歷次台股急殺，融資餘額都在高檔。

## 怎麼用

1. 每個指標只有兩種狀態：🔴 達到門檻，🟢 未達到。沒有中間值，避免自己找理由。
2. 資料缺失顯示 ⚪，不計入分數，但會降低覆蓋率。覆蓋率低於 70 分時，分數只能當參考。
3. 分數 = 所有紅燈的權重加總（0–100）。對應動作見 [`docs/ladder.md`](ladder.md)。
4. 門檻每季檢討一次。**不要在盤中改門檻。** 盤中改門檻等於沒有門檻。

## 通知規則

| 轉換 | 意義 | 通知？ |
|---|---|---|
| 🟢 → 🔴 | 新增風險 | **是** |
| 🔴 → 🟢 | 風險解除 | **是** |
| ⚪ → 🔴 | 補上資料後發現已達門檻 | **是** |
| ⚪ → 🟢 | 只是補上資料 | 否 |
| 🔴 / 🟢 → ⚪ | 資料遺失 | 否 |

每天收到「一切正常」的通知，三週後你就不會再讀它。所以只有上面三種轉換會推播。

## 已知限制（誠實說明）

- **門檻是個人設定值，不是統計最適解。** 台股的大型頭部樣本只有 5 到 6 次，任何「最佳門檻」
  都是對小樣本過度配適。這些數字是數量級上的合理設定，不是校準過的參數。
- **指標之間有相關性。** PB 與 PE 常同時轉紅，融資與當沖也會。所以分數在高檔會跳得比較快，
  這是刻意的設計，不是錯誤。
- **這套系統不預測時間。** 它只回答「現在承受的風險有多大」。
- **資料有時間落差，有些數值是推算的。** 追蹤表會標註每個指標的資料日期，推算的數值會在
  「資料備註」說明推算方法。看到備註就知道那個數字不是官方原始值。
- **紅燈的意義會隨階段改變。** 融資餘額在上漲期轉紅代表槓桿在累積（風險升高）；在下跌期
  維持紅燈代表去槓桿還沒走完（風險正在被清掉）。分數不分辨這兩者，要自己看備註。

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
        if ind.get("query"):
            parts.append(f"- **每日查詢關鍵字**：`{ind['query']}`")
        parts.append("- **輸入欄位**：" + "、".join(
            f"`{k}`（{m['label']}，單位 {m.get('unit', '')}）"
            for k, m in ind["metrics"].items()
        ))
        parts.append(f"\n{ind['why']}\n")
    parts.append("\n---\n")
    parts.append("> 這是個人紀律工具，不是投資建議。\n")
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    print(f"寫入 docs/risk-indicators.md（{len(config['indicators'])} 個指標，"
          f"權重合計 {sum(i['weight'] for i in config['indicators'])}）")


if __name__ == "__main__":
    main()
