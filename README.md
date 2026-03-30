# Make Money Easy

以台股資料為核心的模擬交易與策略研究工具。  
目前專案已經有可操作的前端工作區，使用者可以建立 workspace、同步股票資料、管理觀察清單、查看持倉、執行回測，以及監看策略訊號與自動化交易設定。

這份 README 以目前 `frontend/src` 的實作為準，重點放在：

- 前端每個頁面現在能做什麼
- 每個功能實際串接到哪些 API
- API 後面對應的 route / service / 資料來源是什麼

## 1. 目前技術架構

### Frontend

- React 19
- Vite
- React Router
- TanStack Query
- Recharts
- `frontend/src/api/client.ts` 透過 `/api/v1` 呼叫後端

### Backend

- FastAPI
- SQLAlchemy
- SQLite
- APScheduler
- `twstock`

### 資料來源

- SQLite：儲存使用者、帳戶、持倉、成交、觀察清單、策略訊號、回測結果、股票主檔與歷史資料
- `twstock` / TWSE / TPEX：提供股票主檔、即時報價、月資料與區間歷史資料

## 2. 前端頁面總覽

| 頁面 | 路由 | 主要用途 | 主要後端 |
| --- | --- | --- | --- |
| 登入頁 | `/login` | 選擇既有 workspace 使用者 | `users` |
| Workspace 設定 | `/setup` | 建立/更新帳戶、匯入持倉、同步股票資料 | `users`、`portfolio`、`jobs`、`stocks` |
| Dashboard | `/dashboard` | 看資產總覽、持倉、觀察股、報價圖表、自動化交易設定 | `users`、`portfolio`、`watchlist`、`stocks`、`strategies` |
| Market | `/market` | 管理 watchlist 與預設同步池 | `watchlist`、`jobs` |
| Backtests | `/backtests` | 執行單股/多股回測、查看績效與交易明細 | `backtests`、`strategies`、`jobs`、`stocks` |
| Signals | `/signals` | 檢視最新策略訊號與最近成交 | `strategies`、`portfolio` |

補充：

- `/logs` 目前會直接導向 `/backtests`
- `frontend/src/pages/LogsPage.tsx` 存在，但目前沒有掛到主路由

## 3. 各頁面功能與後端串接

### 3.1 登入頁 `/login`

功能：

- 使用使用者名稱或 email 選取既有 workspace
- 成功後把 `active_user_id` 存到 localStorage

前端實作：

- 頁面：[frontend/src/pages/LoginPage.tsx](./frontend/src/pages/LoginPage.tsx)
- 本地狀態：[frontend/src/lib/storage.ts](./frontend/src/lib/storage.ts)

串接 API：

- `POST /api/v1/users/login`

後端對應：

- Route：[app/api/routes/users.py](./app/api/routes/users.py)
- Service：[app/services/user_service.py](./app/services/user_service.py)
- Repository：`UserRepository`
- 資料來源：SQLite `users`、`accounts`

### 3.2 Workspace 設定頁 `/setup`

功能：

- 建立新的 workspace 使用者
- 更新既有 workspace 的名稱、email、初始資金、可用現金
- 手動輸入持倉
- 透過股票代碼自動完成查詢股票
- 在持倉編輯時抓即時報價，自動回填市價
- 預覽目前資料同步目標
- 更新股票主檔
- 針對自選代碼或預設清單同步歷史區間資料

前端實作：

- 頁面：[frontend/src/pages/SetupPage.tsx](./frontend/src/pages/SetupPage.tsx)
- 持倉編輯器：[frontend/src/components/PositionEditor.tsx](./frontend/src/components/PositionEditor.tsx)
- 股票自動完成：[frontend/src/components/StockAutocompleteInput.tsx](./frontend/src/components/StockAutocompleteInput.tsx)

串接 API：

- `GET /api/v1/users/{user_id}`
- `GET /api/v1/portfolio/positions?user_id=...`
- `POST /api/v1/portfolio/bootstrap`
- `GET /api/v1/jobs/sync/targets?user_id=...`
- `POST /api/v1/jobs/sync/stocks`
- `POST /api/v1/jobs/sync/history-range`
- `GET /api/v1/stocks/search?q=...`
- `GET /api/v1/stocks/{code}/quote`

後端對應：

- 使用者與帳戶：`users` route -> `UserService`
- 建立/更新帳戶與持倉：`portfolio` route -> `PortfolioService`
- 同步目標解析與資料同步：`jobs` route -> `MarketDataService`
- 股票搜尋與即時報價：`stocks` route -> `StockRepository` + `TwStockClient`

資料來源：

- SQLite：使用者、帳戶、持倉、已同步股票主檔與歷史資料
- `twstock`：股票 metadata、即時報價、區間歷史資料

同步目標邏輯：

- 如果輸入手動代碼，使用 `custom` 模式
- 否則使用 `default` 模式
- `default` 模式會合併：
  - 使用者 watchlist
  - 預設產業池

預設產業池定義於：

- [app/services/market_data_service.py](./app/services/market_data_service.py)

### 3.3 Dashboard `/dashboard`

功能：

- 顯示使用者資產摘要
- 顯示目前持倉
- 從 watchlist 快速切換股票
- 查看單一股票即時報價
- 查看指定日期區間的 K 線圖
- 自動輪詢報價
- 查看與修改自動化交易設定

前端實作：

- 頁面：[frontend/src/pages/DashboardPage.tsx](./frontend/src/pages/DashboardPage.tsx)
- K 線圖：[frontend/src/components/KLineChart.tsx](./frontend/src/components/KLineChart.tsx)
- 持倉表格：[frontend/src/components/PositionTable.tsx](./frontend/src/components/PositionTable.tsx)

串接 API：

- `GET /api/v1/users/{user_id}`
- `GET /api/v1/portfolio?user_id=...`
- `GET /api/v1/portfolio/positions?user_id=...`
- `GET /api/v1/watchlist?user_id=...`
- `GET /api/v1/strategies/catalog`
- `GET /api/v1/strategies/automation/{user_id}`
- `PUT /api/v1/strategies/automation/{user_id}`
- `GET /api/v1/stocks/{code}/quote?force_refresh=true`
- `GET /api/v1/stocks/{code}/history-range?start_date=...&end_date=...`

後端對應：

- 使用者與資產摘要：`PortfolioService`
- Watchlist：`WatchlistService`
- 策略清單：`StrategyService.list_strategy_definitions`
- 自動化設定：`AutomationService.get_or_create_config` / `update_config`
- 即時報價與歷史區間：`TwStockClient` + `StockRepository`

資料來源：

- SQLite：帳戶、持倉、watchlist、策略自動化設定、已同步歷史資料
- `twstock`：即時報價；若需要也會補抓區間歷史資料

自動化設定實際影響：

- 只是設定策略名稱與下單 sizing 參數
- 真正每日執行由排程 job 觸發，不是在 Dashboard 頁面直接下單

### 3.4 Market `/market`

功能：

- 顯示目前 watchlist
- 顯示預設同步池中的股票
- 新增 watchlist 股票
- 移除 watchlist 股票
- 依產業分組展示追蹤名單

前端實作：

- 頁面：[frontend/src/pages/MarketPage.tsx](./frontend/src/pages/MarketPage.tsx)

串接 API：

- `GET /api/v1/watchlist?user_id=...`
- `POST /api/v1/watchlist`
- `DELETE /api/v1/watchlist/{code}?user_id=...`
- `GET /api/v1/jobs/sync/targets?user_id=...`

後端對應：

- Watchlist CRUD：`watchlist` route -> `WatchlistService`
- 預設同步池：`jobs` route -> `MarketDataService.resolve_sync_targets`

資料來源：

- SQLite：watchlist、stocks
- `twstock`：新增 watchlist 時如果本地沒有股票 metadata，會補抓並寫回 stocks

### 3.5 Backtests `/backtests`

功能：

- 輸入單一股票或多檔股票代碼
- 選擇策略、日期區間、初始資金、下單 sizing、最大持倉檔數
- 執行回測
- 查看回測績效摘要
- 查看資產曲線或價格圖
- 查看逐筆交易紀錄
- 查看歷史回測結果清單

前端實作：

- 頁面：[frontend/src/pages/BacktestsPage.tsx](./frontend/src/pages/BacktestsPage.tsx)
- 權益曲線圖：[frontend/src/components/BacktestEquityChart.tsx](./frontend/src/components/BacktestEquityChart.tsx)
- 價格圖：[frontend/src/components/BacktestPriceChart.tsx](./frontend/src/components/BacktestPriceChart.tsx)

串接 API：

- `GET /api/v1/strategies/catalog`
- `GET /api/v1/jobs/sync/targets`
- `GET /api/v1/backtests?limit=...`
- `POST /api/v1/backtests/run`
- `GET /api/v1/stocks/{code}/history-range?start_date=...&end_date=...`

後端對應：

- Route：[app/api/routes/backtests.py](./app/api/routes/backtests.py)
- Service：[app/services/backtest_service.py](./app/services/backtest_service.py)
- 策略評估：`BacktestService` 內部呼叫 `StrategyService`
- 股票池預設值：`MarketDataService.DEFAULT_SYNC_POOL_INDUSTRIES`

回測邏輯重點：

- 支援單股與多股組合回測
- 依策略的 `execution_timing` 決定是當日收盤成交，還是次日開盤成交
- 回測結果會寫入 SQLite `backtest_results`
- 前端圖表需要單股歷史資料時，會再呼叫 `history-range`

### 3.6 Signals `/signals`

功能：

- 顯示每檔股票最新一筆策略訊號
- 支援依產業過濾
- 依 `SELL / HOLD / BUY` 分頁查看
- 同頁顯示最近成交紀錄

前端實作：

- 頁面：[frontend/src/pages/StrategySignalsPage.tsx](./frontend/src/pages/StrategySignalsPage.tsx)

串接 API：

- `GET /api/v1/strategies/signals?latest_only=true`
- `GET /api/v1/portfolio/trades?user_id=...&limit=30`

後端對應：

- 訊號列表：`strategies` route -> `StrategyService.list_signals`
- 成交列表：`portfolio` route -> `OrderService.list_trades`

資料來源：

- SQLite `strategy_runs`
- SQLite `trades`

注意：

- 這一頁目前是「監看頁」
- 前端目前沒有直接綁定 `POST /api/v1/strategies/run`
- 訊號通常來自排程工作或其他 API 呼叫後寫入資料庫

## 4. 前端共用元件與後端關係

### 股票自動完成 `StockAutocompleteInput`

檔案：

- [frontend/src/components/StockAutocompleteInput.tsx](./frontend/src/components/StockAutocompleteInput.tsx)

功能：

- 使用 `datalist` 提供股票代碼 / 名稱搜尋
- 搜尋結果會帶出最新價格
- 輸入精確代碼後會自動 resolve

串接 API：

- `GET /api/v1/stocks/search`

後端：

- `stocks` route
- `StockRepository.search_stocks`
- `StockRepository.get_latest_price`

### 持倉編輯器 `PositionEditor`

檔案：

- [frontend/src/components/PositionEditor.tsx](./frontend/src/components/PositionEditor.tsx)

功能：

- 新增/刪除持倉列
- 輸入股票代碼後抓即時報價，回填 `market_price`

串接 API：

- `GET /api/v1/stocks/{code}/quote`

後端：

- `stocks` route
- `TwStockClient.get_realtime_quote`

## 5. 後端模組對照

### API Router

- [app/api/router.py](./app/api/router.py)

目前主要提供：

- `users`
- `portfolio`
- `stocks`
- `strategies`
- `backtests`
- `jobs`
- `market`
- `watchlist`

### 主要 Service

| Service | 角色 |
| --- | --- |
| `UserService` | 建立使用者、登入辨識 |
| `PortfolioService` | 建立/更新帳戶與持倉、回傳資產摘要 |
| `WatchlistService` | watchlist CRUD |
| `MarketDataService` | 股票主檔同步、歷史資料同步、同步目標解析 |
| `TwStockClient` | 封裝 `twstock`、TWSE、TPEX 的資料抓取 |
| `StrategyService` | 策略清單、策略評估、訊號寫入 |
| `AutomationService` | 自動化交易設定與每日自動執行 |
| `BacktestService` | 單股/多股回測與績效統計 |
| `OrderService` | 模擬下單、成交、交易紀錄 |

## 6. 排程與背景作業

排程定義：

- [app/jobs/scheduler.py](./app/jobs/scheduler.py)

目前排程時間為 `Asia/Taipei`：

- `06:00` 同步股票主檔 `run_sync_stocks_job`
- `09:30` 執行每日 workspace 自動化交易 `run_daily_workspace_automation_job`
- `14:10` 同步 workspace 收盤資料 `run_close_sync_workspace_data_job`

這些 job 和前端的關係：

- Dashboard 的自動化設定會影響 `09:30` 的自動交易行為
- Setup / Market 裡的 watchlist 與預設同步池會影響資料同步範圍
- Signals 頁看到的訊號，通常也是這些批次程序跑完後存下來的結果

## 7. 目前 UI 有用到與沒用到的 API

### 已接到 UI

- `/users/login`
- `/users/{user_id}`
- `/portfolio`
- `/portfolio/positions`
- `/portfolio/trades`
- `/portfolio/bootstrap`
- `/stocks/search`
- `/stocks/{code}/quote`
- `/stocks/{code}/history-range`
- `/strategies/catalog`
- `/strategies/automation/{user_id}`
- `/strategies/signals`
- `/backtests`
- `/backtests/run`
- `/jobs/sync/stocks`
- `/jobs/sync/targets`
- `/jobs/sync/history-range`
- `/watchlist`

### 後端存在，但目前前端沒有直接用到

- `/market/overview`
- `/strategies/run`
- `/backtests/{result_id}`
- `/jobs/sync/history`
- `/stocks/{code}/history`
- `/stocks/{code}/sync`

## 8. 目錄重點

```text
app/
  api/routes/            FastAPI routes
  services/              商業邏輯
  db/models/             SQLAlchemy models
  db/repositories/       DB 查詢封裝
  jobs/                  APScheduler jobs
  strategies/            策略實作

frontend/
  src/pages/             頁面
  src/components/        共用元件
  src/api/               前端 API client
  src/types/             API 型別
  src/lib/               格式化與 localStorage
```

## 9. 本機啟動

### 方式一：Docker Compose

```bash
docker compose up --build
```

啟動後：

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

### 方式二：本機開發

Backend:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Scheduler:

```bash
python scripts/run_scheduler.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

如果只想快速啟動後端與 scheduler：

```bash
python scripts/run_dev.py
```

注意：

- `scripts/run_dev.py` 不會啟動 Vite，前端仍要另外在 `frontend/` 目錄執行 `npm run dev`
- API 前綴是 `/api/v1`
- CORS 預設允許 `http://localhost:5173` 與 `http://127.0.0.1:5173`

## 10. 後續可優化方向

- 把 `Signals` 頁補上手動執行策略 `POST /strategies/run`
- 把 `/market/overview` 接進前端，做市場強弱看板
- 補真正的 job logs 頁，而不是把 `/logs` 重新導向 `/backtests`
- 補權限與真正登入驗證，目前是以 workspace user 切換為主
- 若資料量變大，可把 SQLite 升級為 PostgreSQL
