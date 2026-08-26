以下係 Day 9 由淺入深嘅完整實習流程。建議你喺 workspace 根目錄執行，因為你已經將 Day 9 檔案複製到：

```text
/workspaces/python_flask_test1
```

**開始前**

確認根目錄有 Day 9 版本嘅：

```text
app.py
Dockerfile
docker-compose.yml
requirements.txt
templates/tasks.html
```

啟動：

```bash
cd /workspaces/python_flask_test1
docker compose up --build
```

另一個 terminal 檢查：

```bash
docker compose ps
docker compose exec redis redis-cli ping
```

Redis 應回傳：

```text
PONG
```

---

## 1. 20 分鐘：比較同步與 Celery latency

### 1.1 先測試同步概念

同步工作會直接阻塞 Flask web process：

```python
@app.post('/api/tasks/sync')
@token_required
def sync_task_api(current_user):
    del current_user
    task_request = TaskRequest.model_validate(request.get_json(silent=True))
    time.sleep(task_request.delay_seconds)
    return jsonify({
        'status': 'SUCCESS',
        'answer': f'完成：{task_request.question}',
    }), 200
```

測試：

```bash
time curl -X POST http://localhost:5000/api/tasks/sync \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"question":"同步測試","delay_seconds":5}'
```

預期：

- HTTP request 大約等待 5 秒
- Flask worker 一直被該 request 佔用
- 同時間大量 request 會造成阻塞

### 1.2 測試 Celery 非同步工作

```bash
time curl -X POST http://localhost:5000/api/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"question":"Celery 測試","delay_seconds":5}'
```

預期：

- 很快收到 `202 Accepted`
- Response 包含 `task_id`
- 真正工作由 Celery worker 執行
- Flask 不需要等待 5 秒

記錄比較：

| 項目 | 同步 | Celery |
|---|---|---|
| HTTP response | 等工作完成 | 立即回 `202` |
| 耗時工作位置 | Flask web process | Celery worker |
| 是否阻塞 web | 會 | 不會 |
| 查詢方式 | 直接取得結果 | 使用 task id 查詢 |

---

## 2. 25 分鐘：觀察 Redis、worker 和 task status

### 2.1 查看服務

```bash
docker compose ps
```

應該見到：

```text
web       Up
worker    Up
redis     Up
```

### 2.2 查看 web log

```bash
docker compose logs -f web
```

另一個 terminal 查看 worker：

```bash
docker compose logs -f worker
```

提交一個 task：

```bash
curl -s -X POST http://localhost:5000/api/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"question":"觀察 queue","delay_seconds":10}'
```

### 2.3 查詢 task status

```bash
curl -s http://localhost:5000/api/tasks/TASK_ID \
  -H "Authorization: Bearer YOUR_TOKEN"
```

可能看到：

```json
{
  "task_id": "...",
  "status": "PROGRESS",
  "progress": {
    "percent": 10,
    "step": "processing"
  }
}
```

最後應變成：

```json
{
  "task_id": "...",
  "status": "SUCCESS",
  "result": {
    "answer": "..."
  }
}
```

### 2.4 觀察 Redis queue

```bash
docker compose exec redis redis-cli LLEN celery
```

提交多個長任務：

```bash
for i in 1 2 3 4 5; do
  curl -s -X POST http://localhost:5000/api/tasks \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer YOUR_TOKEN" \
    -d "{\"question\":\"任務 $i\",\"delay_seconds\":10}"
  echo
done
```

觀察 worker log：

```bash
docker compose logs -f worker
```

---

## 3. 20 分鐘：加入 email task 和 retry/backoff

### 3.1 建立 email Celery task

```python
import smtplib
from email.message import EmailMessage
```

```python
@celery.task(
    bind=True,
    autoretry_for=(TimeoutError, ConnectionError),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
)
def send_email_task(self, recipient, subject, body):
    message = EmailMessage()
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)

    with smtplib.SMTP(
        os.environ['SMTP_HOST'],
        int(os.environ.get('SMTP_PORT', '587')),
        timeout=10,
    ) as smtp:
        smtp.starttls()
        smtp.login(
            os.environ['SMTP_USERNAME'],
            os.environ['SMTP_PASSWORD'],
        )
        smtp.send_message(message)

    return {'sent_to': recipient}
```

`autoretry_for` 只處理暫時性錯誤：

- `TimeoutError`
- `ConnectionError`

不要對輸入錯誤、無效 email 或權限錯誤自動 retry。

### 3.2 加入 API

```python
@app.post('/api/email')
@token_required
def email_api(current_user):
    del current_user
    data = request.get_json(silent=True) or {}

    recipient = data.get('recipient')
    subject = data.get('subject')
    body = data.get('body')

    if not all(isinstance(value, str) and value.strip()
               for value in (recipient, subject, body)):
        return jsonify({
            'error': 'Validation Error',
            'message': 'recipient、subject、body 必須是非空文字。',
        }), 422

    task = send_email_task.delay(recipient, subject, body)

    return jsonify({
        'task_id': task.id,
        'status': 'PENDING',
    }), 202
```

### 3.3 設定 SMTP environment variables

不要將密碼寫入程式碼：

```bash
export SMTP_HOST=smtp.example.com
export SMTP_PORT=587
export SMTP_FROM=your@email.com
export SMTP_USERNAME=your@email.com
export SMTP_PASSWORD=your-password
```

實際使用 Docker 時，將它們放到 `.env`，並在 `docker-compose.yml` 注入。

---

## 4. 25 分鐘：Docker healthcheck 和非 root user

### 4.1 修改 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/')" || exit 1

CMD ["python", "app.py"]
```

重建：

```bash
docker compose down
docker compose up --build
```

確認是否使用非 root：

```bash
docker compose exec web whoami
```

預期：

```text
appuser
```

查看 health status：

```bash
docker inspect --format='{{json .State.Health}}' \
  python_flask_test1-web-1
```

---

## 5. 20 分鐘：加入 Flower 監控

### 5.1 加入 Flower dependency

在 `requirements.txt` 加入：

```text
flower
```

### 5.2 在 Compose 加入 Flower service

```yaml
  flower:
    build: .
    command: celery -A app.celery flower --port=5555
    ports:
      - "5555:5555"
    environment:
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/1
    depends_on:
      - redis
      - worker
```

重建：

```bash
docker compose up --build
```

開啟：

```text
http://localhost:5555
```

你可以查看：

- worker 是否 online
- task 數量
- SUCCESS / FAILURE
- task 執行時間
- active tasks
- retry 次數

製造一個失敗 task 後，在 Flower 查看 failure。

---

# 課堂練習

## 1. 將 mock AI task 換成 Day 8 RAG

建議做法：

1. 將 Day 8 的以下邏輯抽到獨立檔案，例如 `rag_service.py`：
   - `DocumentChunk`
   - `TfidfVectorStore`
   - `split_into_chunks`
   - `call_llm`
2. Day 9 的 Celery task import 該服務。
3. task 接收 `question` 和 `user_id`。
4. task 執行 RAG search。
5. 將 answer、sources、user_id 存入資料庫。
6. API 只回傳 `task_id`。
7. status endpoint 在 `SUCCESS` 時回傳資料庫結果。

不要在 Flask request 裡直接執行 RAG 和 LLM，否則就失去 Celery 的作用。

---

## 2. 加入取消 task API

基本 API：

```python
from celery.result import AsyncResult

@app.post('/api/tasks/<task_id>/cancel')
@token_required
def cancel_task_api(current_user, task_id):
    task_record = TaskRecord.query.filter_by(
        task_id=task_id,
        user_id=current_user.id,
    ).first()

    if task_record is None:
        return jsonify({'error': 'Not Found'}), 404

    if task_record.status in ('SUCCESS', 'FAILURE', 'CANCELLED'):
        return jsonify({
            'error': 'Conflict',
            'message': '任務已經完成，不能取消。',
        }), 409

    celery.control.revoke(task_id, terminate=True, signal='TERM')
    task_record.status = 'CANCELLED'
    db.session.commit()

    return jsonify({
        'task_id': task_id,
        'status': 'CANCELLED',
    }), 200
```

測試：

```bash
curl -X POST http://localhost:5000/api/tasks/TASK_ID/cancel \
  -H "Authorization: Bearer YOUR_TOKEN"
```

注意 race condition：

- task 可能在 revoke 前已經完成
- worker 可能已經開始執行
- `terminate=True` 只適合可安全中斷的工作
- email、付款等副作用可能已經發生

因此 task 執行前應再檢查資料庫的 `cancel_requested` 狀態，並使用 idempotency key 避免重複副作用。

---

## 3. 只 retry upstream timeout

不要使用：

```python
autoretry_for=(Exception,)
```

這會連 validation error 都 retry。

較安全的寫法：

```python
@celery.task(
    bind=True,
    autoretry_for=(TimeoutError, ConnectionError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_kwargs={'max_retries': 3},
)
def process_ai_task(self, question, delay_seconds=5):
    if not question.strip():
        raise ValueError('question 不可為空')

    try:
        result = call_external_ai(question)
    except TimeoutError:
        raise
    except ConnectionError:
        raise

    return result
```

輸入錯誤應直接失敗，不應 retry：

```python
raise ValueError('Invalid question')
```

---

## 4. Redis healthcheck 和 depends_on condition

修改 Redis service：

```yaml
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10
```

修改 web、worker：

```yaml
    depends_on:
      redis:
        condition: service_healthy
```

完整重建：

```bash
docker compose down
docker compose up --build
```

檢查：

```bash
docker compose ps
```

Redis 應顯示：

```text
Up (healthy)
```

這只保證 Redis 已經可連線，不代表所有應用程式邏輯都正常，所以仍然要測試 login、建立 task 和查詢 task。

---

## 5. 為 task 加入 user id

資料庫 model：

```python
class TaskRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String( hundert), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='PENDING')
    question = db.Column(db.Text, nullable=False)
    result_json = db.Column(db.JSON)
```

`db.String( hundert)` 要改成正確的：

```python
task_id = db.Column(db.String(100), unique=True, nullable=False)
```

建立 task 時：

```python
task = process_ai_task.delay(
    task_request.question,
    task_request.delay_seconds,
)
```

之後儲存：

```python
record = TaskRecord(
    task_id=task.id,
    user_id=current_user.id,
    question=task_request.question,
    status='PENDING',
)
db.session.add(record)
db.session.commit()
```

查詢時必須限制 user：

```python
record = TaskRecord.query.filter_by(
    task_id=task_id,
    user_id=current_user.id,
).first()
```

如果 task 不屬於目前登入的 user，應回傳：

```text
404 Not Found
```

不要回傳「task 存在但屬於其他人」，否則會洩露 task id 資訊。

---

## 最終驗收清單

```bash
docker compose ps
docker compose exec redis redis-cli ping
curl -i http://localhost:5000/
```

然後確認：

- login 回傳 JWT
- 建立 task 回 `202`
- status 可看到 `PENDING`、`PROGRESS`、`SUCCESS`
- worker log 有執行 task
- Redis healthcheck 顯示 healthy
- Flower 可以看到 worker 和 task
- failed task 會顯示錯誤
- task 只能由建立它的 user 查詢
- cancel 不會錯誤取消已完成 task
- timeout 會 retry，validation error 不會 retry

停止環境：

```bash
docker compose down
```