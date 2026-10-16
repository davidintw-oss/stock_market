# 每日執行手冊

排程每個交易日台北時間 **16:47** 執行一次。這份文件是它照著做的步驟，也是你想手動跑時的依據。

## 這個容器的網路限制（重要）

實測結果（2026-10-16）：

| 方式 | 狀態 |
|---|---|
| `WebSearch` | ✅ 可用。唯一的對外資料管道。 |
| `WebFetch` | ❌ 全部網域 DNS 解析失敗 |
| `curl` / `python requests` | ❌ 同上 |

所以 `www.twse.com.tw`、`statementdog.com`、`goodinfo.tw`、`wantgoo.com` 都**抓不到**，
不要再嘗試。所有數字只能從 WebSearch 的結果裡讀出來。

**要解除這個限制**：在工作階段標題列的雲端環境選單 → Edit → Network access，
把這些網域加進允許清單（Allow package managers 的勾保持勾選）。
做法見 <https://code.claude.com/docs/en/cloud-environments#network-access>。
解除之後，年線乖離與股債利差這兩個灰燈才有機會自動化。

## 步驟

### 1. 讀前一次的狀態

```bash
python3 scripts/risk_check.py --show
```

`lights` 是上次的燈號，用來比對變化。`metrics` 是上次的數值，這次沒查到的項目會沿用。

### 2. 查今天的資料

每個指標的查詢關鍵字寫在 `data/config.json` 的 `query` 欄位，也列在
[risk-indicators.md](risk-indicators.md) 每一節。優先順序：

1. **指數收盤**（必查）— 「台股盤後 加權指數 收盤」
2. **融資餘額**（權重 14）— 「台股 融資餘額 增減 億元 盤後」
3. **外資買賣超與月線**（權重 9）— 「台股 外資 連續賣超 累計 億元 月線」
4. **PB / PE**（權重 15 + 13）— 「台股 大盤 股價淨值比 本益比」
5. **台積電影響大盤點數**（權重 10）— 「台積電 影響大盤 點 收盤」
6. **漲跌家數**（權重 8）— 「台股 上漲家數 下跌家數 盤後」

### 3. 查不到就不要填

沿用舊值，或留空讓它變灰燈。**絕對不要推測數字。**

兩種例外，可以推算，但一定要用 `--note` 寫明方法：

- **PB / PE**：淨值與獲利在月內不變，所以可以用指數比例換算。
  `新 PB = 舊 PB × (今日指數 ÷ 舊指數)`
- **台積電權重**：從「台積電跌 X%、影響大盤 N 點」反推。
  `權重 = (N ÷ 前一日指數) ÷ X%`
  用兩個不同交易日各算一次，數字接近才可信。

### 4. 執行引擎

```bash
python3 scripts/risk_check.py --date 2026-10-16 \
  --set index=47111.26 pb=4.08 margin_balance=6464.15 \
  --asof pb=2026-10-16 \
  --note "pb=依指數比例推算"
```

### 5. 看最後一行決定要不要通知

```
RESULT changes=N score=S zone=Z
```

- `changes=0` → 提交並 push，**不要產生任何報告**。這一天不通知。
- `changes>0` → 提交並 push，然後回報：哪些指標變燈、新分數與區間、
  `docs/ladder.md` 對應的動作、本次使用的資料日期。10 行以內。

### 6. 休市日

確認今天台股休市（颱風假、國定假日）就直接結束，不要執行引擎，也不要寫入歷史。

## 不可以做的事

- 不要修改 `data/config.json` 的門檻或權重。門檻只有本人能改。
- 不要修改 `docs/ladder.md`。
- 不要開 pull request。只 push 到 `claude/taiwan-stock-60k-target-95nopq`。
- 不要加上自己的點位預測或投資建議。只回報燈號與既定規則對應的動作。
