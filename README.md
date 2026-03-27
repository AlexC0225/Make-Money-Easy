# 台股模擬交易 App 專案規劃

本專案目標是開發一個以台股為核心的模擬交易 App，使用 `Python` 作為主要開發語言、`SQLite` 作為本地資料庫，並以 [`twstock`](https://twstock.readthedocs.io/zh-tw/latest/) 作為股票資料擷取與分析基礎。

現階段先聚焦在「可穩定運作的 MVP」：

- 可同步台股股票基本資料、歷史行情、即時報價
- 可建立使用者、虛擬資金帳戶、持倉與訂單
- 可執行模擬買賣、計算損益與交易成本
- 可套用基礎交易策略並回測
- 可為後續 Web / Mobile 前端保留擴充空間

## 1. 技術選型

### 核心技術

- 語言：`Python 3.11+`
- 資料庫：`SQLite`
- ORM / DB 存取：`SQLAlchemy`
- API 框架：`FastAPI`
- 資料驗證：`Pydantic`
- 任務排程：`APScheduler`
- 測試：`pytest`
- 套件管理：`uv` 或 `pip`

### 為什麼選這個組合

- `Python` 適合快速整合金融資料、策略模擬與 API 開發
- `SQLite` 適合 MVP 階段，部署簡單、資料結構清楚，後續可平滑升級到 `PostgreSQL`
- `FastAPI` 適合將模擬交易引擎、帳務、行情查詢做成清楚的服務接口
- `twstock` 已提供台股歷史資料、分析函式與即時報價包裝，能明顯降低初期整合成本

## 2. twstock 使用方式

根據 `twstock` 官方文件，本專案會這樣使用：

- `twstock.Stock('2330')`
  - 取得單一股票歷史資料
  - 可搭配 `fetch_from(year, month)` 拉取月度歷史行情
- `stock.moving_average(...)`
  - 計算均線
- `stock.ma_bias_ratio(...)`
  - 計算均線乖離
- `twstock.BestFourPoint(stock)`
  - 作為策略訊號判斷基礎
- `twstock.realtime.get('2330')`
  - 取得模擬撮合所需的即時價格與五檔資訊

### 重要限制

`twstock` 官方文件明確提到：`analytics` 分析模組只適用於 `stock.Stock` 的歷史資料，不能直接對 `realtime` 資料做分析。  
因此本專案的設計會拆成兩段：

- 歷史資料：
  - 用來計算均線、乖離、回測、策略訊號
- 即時資料：
  - 用來做模擬下單成交、盤中顯示、即時持倉估值

## 3. 專案架構

建議採用「分層式架構」，先把資料、交易引擎、策略、API 分開，後續才不會把模擬撮合與畫面綁死。

```text
make-money-easy/
├─ README.md
├─ requirements.txt
├─ pyproject.toml
├─ .env.example
├─ app/
│  ├─ main.py                  # FastAPI 入口
│  ├─ config.py                # 設定檔
│  ├─ api/
│  │  ├─ deps.py
│  │  ├─ routes/
│  │  │  ├─ auth.py
│  │  │  ├─ stocks.py
│  │  │  ├─ portfolio.py
│  │  │  ├─ orders.py
│  │  │  ├─ strategies.py
│  │  │  └─ backtest.py
│  ├─ core/
│  │  ├─ security.py
│  │  ├─ database.py
│  │  └─ enums.py
│  ├─ db/
│  │  ├─ models/
│  │  │  ├─ user.py
│  │  │  ├─ stock.py
│  │  │  ├─ market_data.py
│  │  │  ├─ order.py
│  │  │  ├─ trade.py
│  │  │  ├─ portfolio.py
│  │  │  └─ strategy.py
│  │  ├─ repositories/
│  │  └─ session.py
│  ├─ schemas/
│  │  ├─ stock.py
│  │  ├─ order.py
│  │  ├─ portfolio.py
│  │  └─ strategy.py
│  ├─ services/
│  │  ├─ twstock_client.py     # twstock 包裝層
│  │  ├─ market_data_service.py
│  │  ├─ quote_service.py
│  │  ├─ order_service.py
│  │  ├─ portfolio_service.py
│  │  ├─ settlement_service.py
│  │  └─ backtest_service.py
│  ├─ engine/
│  │  ├─ broker.py             # 模擬券商
│  │  ├─ matcher.py            # 撮合邏輯
│  │  ├─ risk.py               # 風控規則
│  │  └─ pnl.py                # 損益計算
│  ├─ strategies/
│  │  ├─ base.py
│  │  ├─ ma_cross.py
│  │  ├─ best_four_point.py
│  │  └─ hybrid_tw_strategy.py
│  ├─ jobs/
│  │  ├─ sync_stocks.py
│  │  ├─ sync_history.py
│  │  ├─ refresh_quotes.py
│  │  └─ run_signals.py
│  └─ utils/
│     ├─ fees.py
│     ├─ datetime.py
│     └─ logger.py
├─ data/
│  ├─ app.db
│  └─ seeds/
├─ tests/
│  ├─ test_market_data.py
│  ├─ test_orders.py
│  ├─ test_portfolio.py
│  ├─ test_strategy.py
│  └─ test_backtest.py
└─ scripts/
   ├─ init_db.py
   ├─ seed_demo_data.py
   └─ run_scheduler.py
```

## 4. 模組職責

### `services/twstock_client.py`

負責將 `twstock` 封裝成我們自己的資料介面，避免未來更換資料來源時需要大改整個系統。

功能：

- 取得股票基本資訊
- 擷取歷史行情
- 擷取即時報價
- 統一錯誤處理、重試機制、資料格式轉換

### `engine/`

這是模擬交易核心。

- `broker.py`
  - 接收買賣指令
  - 檢查資金、庫存、交易限制
- `matcher.py`
  - 用即時報價或回測資料模擬成交
- `risk.py`
  - 控制最大部位、單筆風險、停損
- `pnl.py`
  - 計算未實現損益、已實現損益、報酬率

### `strategies/`

負責策略訊號，不直接處理帳務與交易資料寫入。

- 輸入：歷史行情、即時報價、持倉狀況
- 輸出：`BUY` / `SELL` / `HOLD`

### `jobs/`

負責排程：

- 每日同步股票清單
- 每日同步歷史行情
- 開盤時段刷新報價
- 盤後批次產出策略訊號與績效統計

## 5. SQLite 資料庫設計

MVP 建議先建立以下資料表：

### `users`

- `id`
- `username`
- `email`
- `hashed_password`
- `created_at`

### `accounts`

- `id`
- `user_id`
- `initial_cash`
- `available_cash`
- `frozen_cash`
- `market_value`
- `total_equity`
- `created_at`

### `stocks`

- `id`
- `code`
- `name`
- `market`
- `industry`
- `is_active`
- `updated_at`

### `daily_prices`

- `id`
- `stock_id`
- `trade_date`
- `open_price`
- `high_price`
- `low_price`
- `close_price`
- `volume`
- `turnover`
- `transaction_count`

### `realtime_quotes`

- `id`
- `stock_id`
- `quote_time`
- `latest_trade_price`
- `open_price`
- `high_price`
- `low_price`
- `accumulate_trade_volume`
- `best_bid_price_json`
- `best_ask_price_json`
- `best_bid_volume_json`
- `best_ask_volume_json`

### `orders`

- `id`
- `user_id`
- `stock_id`
- `side`
- `order_type`
- `price`
- `quantity`
- `status`
- `filled_quantity`
- `avg_fill_price`
- `created_at`
- `updated_at`

### `trades`

- `id`
- `order_id`
- `user_id`
- `stock_id`
- `side`
- `fill_price`
- `fill_quantity`
- `fee`
- `tax`
- `executed_at`

### `positions`

- `id`
- `user_id`
- `stock_id`
- `quantity`
- `avg_cost`
- `market_price`
- `unrealized_pnl`
- `realized_pnl`
- `updated_at`

### `strategy_runs`

- `id`
- `strategy_name`
- `stock_id`
- `signal`
- `signal_reason`
- `signal_time`
- `snapshot_json`

### `backtest_results`

- `id`
- `strategy_name`
- `start_date`
- `end_date`
- `total_return`
- `max_drawdown`
- `win_rate`
- `profit_factor`
- `sharpe_ratio`
- `result_json`

## 6. 交易規則與模擬邏輯

台股模擬交易若要有真實感，建議 MVP 就納入以下規則：

### 成交與價格

- 預設使用即時成交價 `latest_trade_price` 作為模擬成交基礎
- 若要更貼近真實，可根據五檔加上簡單滑價模型
- 非交易時段下單時，可設定成：
  - 下一個交易日開盤成交
  - 或建立委託但不立即成交

### 成本

- 手續費：預設 `0.1425%`
- 證交稅：賣出預設 `0.3%`
- 參數化設計：後續可支援券商折扣

### 部位限制

- 單一股票最大持倉：帳戶資金 `15%`
- 同時持有檔數：最多 `5` 檔
- 單筆下單最小單位：
  - MVP 可先以整股 / 一張 `1000` 股為主
  - 零股可作為第二階段功能

### 風控

- 單筆停損：`-5%`
- 停利：`+10%` 或移動停利
- 每日最大虧損上限：帳戶淨值 `3%`
- 若觸發風控，當日停止新倉

## 7. 交易策略設計

本專案建議先做三層式策略，而不是只做單一訊號。

### 策略 1：流動性篩選

先排除不適合模擬交易的標的：

- 最近 `20` 日平均成交量高於門檻
- 價格高於 `10` 元
- 避免長期停牌或成交量極低標的

目的：

- 降低策略失真
- 避免因資料稀疏造成回測結果不可靠

### 策略 2：趨勢判斷

使用 `twstock.Stock` 的歷史資料來做均線判斷：

- `MA20 > MA60` 視為中期多頭
- 收盤價在 `MA20` 之上
- `MA5` 向上穿越 `MA20` 可視為進場加分條件

目的：

- 只在相對順勢的標的上找進場點

### 策略 3：訊號觸發

用 `BestFourPoint` 當作入場/出場訊號核心：

- 進場：
  - `best_four_point_to_buy()` 為真
  - 並且成交量高於 `20` 日均量
- 出場：
  - `best_four_point_to_sell()` 為真
  - 或跌破 `MA20`
  - 或觸發固定停損 / 停利

### 初版推薦策略：`hybrid_tw_strategy`

綜合上述三層條件，形成第一版主策略：

#### 買進條件

- 股票通過流動性篩選
- `MA20 > MA60`
- 最新收盤價 > `MA20`
- `BestFourPoint` 出現買點
- 單一帳戶尚未超過最大持倉檔數

#### 賣出條件

- `BestFourPoint` 出現賣點
- 或收盤價 < `MA20`
- 或虧損達 `5%`
- 或獲利達 `10%`

#### 優點

- 比純均線交叉更適合台股短中波段
- 比單看四大買賣點更能控制趨勢方向
- 易於解釋，適合作為模擬交易 App 的第一版策略

## 8. 開發流程

建議依照以下順序開發，避免一開始就把前端、策略、即時報價混在一起。

### Phase 1：建立基礎專案

- 初始化 `FastAPI` 專案
- 建立 `SQLite`、`SQLAlchemy`、資料表
- 建立設定檔與日誌系統
- 完成 `twstock_client`

交付成果：

- 可啟動 API
- 可成功拉取 `2330` 歷史資料與即時報價
- 可寫入資料庫

### Phase 2：市場資料層

- 建立股票主檔同步
- 建立歷史行情同步
- 建立即時報價刷新機制
- 建立資料清洗與去重邏輯

交付成果：

- 本地 DB 具備可查詢的股票與行情資料

### Phase 3：模擬交易核心

- 建立帳戶、訂單、成交、持倉模型
- 完成買賣撮合
- 完成損益與成本計算
- 實作停損、持倉限制與資金檢查

交付成果：

- 可以用 API 完整執行一筆模擬買進與賣出

### Phase 4：策略與回測

- 實作均線計算與 `BestFourPoint` 訊號
- 建立策略執行器
- 建立回測模組與績效指標
- 將策略訊號寫回 DB

交付成果：

- 可針對單一股票或股票池做回測

### Phase 5：展示層

可選擇以下其中一條：

- `Streamlit`
  - 快速做出操作介面與績效圖表
- 前後端分離
  - `FastAPI` + `React / Next.js`

若目標是先驗證功能，建議先上 `Streamlit`，之後再拆成正式前後端分離。

## 9. MVP API 建議

### 市場資料

- `GET /stocks`
- `GET /stocks/{code}`
- `GET /stocks/{code}/history`
- `GET /stocks/{code}/quote`

### 交易

- `POST /orders/buy`
- `POST /orders/sell`
- `GET /orders`
- `GET /trades`

### 帳戶與持倉

- `GET /portfolio`
- `GET /portfolio/positions`
- `GET /portfolio/performance`

### 策略與回測

- `POST /strategies/run`
- `GET /strategies/signals`
- `POST /backtests/run`
- `GET /backtests/{id}`

## 10. 測試策略

至少要涵蓋以下測試：

- `twstock` 資料擷取成功 / 失敗案例
- 歷史資料重複同步時不重複寫入
- 資金不足時不能買入
- 庫存不足時不能賣出
- 手續費 / 證交稅計算正確
- 停損停利規則正確觸發
- 回測績效指標計算正確

## 11. 後續擴充方向

- 支援 ETF、上櫃、零股交易
- 支援多策略比較
- 支援排行榜、模擬競賽
- 支援通知功能
- 將 SQLite 升級為 PostgreSQL
- 接入 Redis 做即時快取
- 提供手機 App 或 PWA

## 12. 建議的下一步

如果要開始實作，我建議直接照下面順序推進：

1. 建立專案骨架與 `pyproject.toml`
2. 建立 SQLite schema 與 SQLAlchemy models
3. 包裝 `twstock_client`
4. 完成 `history sync` 與 `realtime quote` API
5. 完成模擬下單與持倉計算
6. 再補 `BestFourPoint + 均線` 策略與回測

## 13. 參考資料

- `twstock` 快速上手：
  - https://twstock.readthedocs.io/zh-tw/latest/quickstart.html
- `twstock` 股票分析模組：
  - https://twstock.readthedocs.io/zh-tw/latest/reference/analytics.html
- `twstock` 歷史股票資料：
  - https://twstock.readthedocs.io/zh-tw/latest/reference/stock.html
- `twstock` 即時股票資訊：
  - https://twstock.readthedocs.io/zh-tw/latest/reference/realtime.html

---

如果要進入下一步，建議直接開始初始化專案骨架，先把：

- `FastAPI`
- `SQLite`
- `SQLAlchemy`
- `twstock_client`
- 基本資料表

一起建起來，這樣之後每個模組都能在同一個基礎上往前推。
