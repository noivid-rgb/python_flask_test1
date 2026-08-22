# Day 9：Celery、Redis 與 Docker 容器化

## 時數及學習成果

- 講授：1.5 小時
- 實習：1.5 小時

完成本課後，學員能夠：

1. 分析長任務點解會阻塞 web worker，並用 Celery + Redis 排隊處理。
2. 建立回傳 `202 Accepted` 及 task id 嘅非同步 API。
3. 用 status endpoint 追蹤 `PENDING`、`PROGRESS`、`SUCCESS` 及 `FAILURE`。
4. 撰寫 Dockerfile，將 Flask app 打包成可重現 image。
5. 用 Docker Compose 協調 Flask、Celery worker 及 Redis 三個服務。

## 1. 點解需要 task queue

同步 request 如果直接做 AI 推理、報表生成或寄 email，web worker 會一直佔用連線：

```text
Browser -> Flask -> slow AI/email work -> response
                  (web worker 被鎖住)
```

Celery 將工作拆出去：

```text
Browser -> Flask -> 202 + task_id
                     |
                     v
                 Redis broker -> Celery worker -> Redis result backend
                     ^                                  |
Browser -> GET /api/tasks/<id> <-------------------------+
```

Flask 只負責驗證及 enqueue，worker 負責耗時工作。`202 Accepted` 表示已接受處理，不代表結果已完成。

## 2. Celery 核心概念

- **Task**：可由 worker 執行嘅 Python function。
- **Broker**：傳送 task message；本課用 Redis database 0。
- **Worker**：常駐程序，從 broker 取 task 並執行。
- **Result backend**：儲存狀態及結果；本課用 Redis database 1。
- **AsyncResult**：由 task id 查詢狀態。

`process_ai_task.delay(...)` 唔會直接執行 function，而係將 message 推入 broker。worker 執行 `self.update_state()` 後，前端就可以看到進度 metadata。

## 3. API 設計

| Method | Endpoint | 行為 | 回應 |
| --- | --- | --- | --- |
| `POST` | `/api/tasks` | 驗證並排入任務 | `202` + `task_id` |
| `GET` | `/api/tasks/<task_id>` | 查詢任務狀態 | `200` |

request 例子：

```json
{
  "question": "分析長文件並整理重點",
  "delay_seconds": 5
}
```

`delay_seconds` 只係教學用 mock 延遲，實務上會換成 LLM、email、PDF 或報表處理。server 要限制輸入範圍，避免有人提交無限長或無限慢嘅任務。

## 4. Retry、錯誤及可靠性

生產 task 通常要設計 `autoretry_for`、`retry_backoff`、最大重試次數及 idempotency key。寄 email 或扣款尤其要避免重試造成重複副作用。亦應加入：

- task timeout、queue routing 及 concurrency 設定
- dead-letter queue 或失敗 task dashboard
- 結果過期時間，避免 Redis 無限增長
- structured logging、trace id 及 metrics
- API rate limit 同使用者權限檢查

本課 API 只回傳一般化嘅 `Task failed`，詳細 exception 應留喺 server log，避免洩露內部資料。

## 5. Docker 基礎

**Image** 係不可變嘅應用程式模板，**container** 係 image 嘅執行實例。Dockerfile 依次：

1. 以 `python:3.12-slim` 作 base image。
2. 設定 `/app` workdir。
3. 複製 requirements 並安裝依賴。
4. 複製程式碼。
5. 用 `CMD` 啟動 Flask。

Compose 將同一份 image 分別以 web 及 worker command 啟動；兩者透過 service name `redis` 連接，而唔係 `localhost`。Compose network 內 `redis:6379` 先係正確 Redis host。

## 6. 執行及測試

本機有 Redis 時：

```bash
cd Day9
redis-server
celery -A app.celery worker --loglevel=info
python app.py
```

另一個 terminal 用 `curl` 或瀏覽器登入後呼叫 API。最簡單係直接使用 UI，觀察 task id 及每秒輪詢狀態。

Docker Compose：

```bash
cd Day9
docker compose up --build
```

開啟 `http://localhost:5000/`。停止並清理：

```bash
docker compose down
```

正式部署前應將 `SECRET_KEY` 放入 `.env` 或 secret manager，唔好使用教材 fallback；SQLite volume、Redis persistence、非 root user、image scanning 及 healthcheck 亦要按環境補上。

## 實習流程（1.5 小時）

1. 20 分鐘：同步 `time.sleep` 與 Celery task 對比 web request latency。
2. 25 分鐘：觀察 Redis queue、worker log 及 task status。
3. 20 分鐘：加入 email task，設計 retry/backoff。
4. 25 分鐘：修改 Dockerfile，加入 healthcheck 及非 root user。
5. 20 分鐘：Compose 加入 Flower monitoring service，檢查 failed task。

## 課堂練習

1. 將 mock AI task 換成 Day 8 RAG `/api/ask` 邏輯，將 answer 儲存到資料庫。
2. 加入 `POST /api/tasks/<id>/cancel`，使用 Celery revoke，並處理 race condition。
3. 實作 task retry，只有 upstream timeout 才重試，輸入驗證錯誤不可重試。
4. 加入 Redis healthcheck 及 web/worker `depends_on` health condition。
5. 為任務加入 user id，確保用戶只能查詢自己提交嘅 task。