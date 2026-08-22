# Day 7：數據驗證、序列化與 LLM API

## 課程目標

完成本課後，學生可以：

1. 用 Pydantic 將不可信 JSON 轉換成有型別嘅 Python model。
2. 用 Marshmallow 將 ORM model 序列化成 API response JSON。
3. 以 `422 Unprocessable Entity` 回報 schema validation 錯誤。
4. 將 JWT 驗證同 AI endpoint 結合。
5. 用統一 provider abstraction 切換 Groq、Gemini 或 mock provider。

## 1. 為什麼 API 需要 schema

HTTP request body 係外部輸入，唔應該假設欄位存在、型別正確或長度合理。schema 係 API contract：它定義欄位、型別、預設值、限制及輸出形狀。

本課使用兩個方向：

| 工具 | 方向 | Day 7 用途 |
| --- | --- | --- |
| Pydantic | JSON -> Python model | 驗證 `/api/chat` request 同 response |
| Marshmallow | Python/ORM object -> JSON | 序列化留言列表及新留言 |

驗證成功先進入商業邏輯，失敗就立即回應，令核心程式唔需要到處寫 `isinstance` 檢查。

## 2. Pydantic request validation

```python
class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
```

`prompt` 不可為空且最多 2000 字；`temperature` 只接受 $0 \leq temperature \leq 2$。`extra='forbid'` 會拒絕未定義欄位，避免 client 靜靜傳入拼錯或未支援嘅參數。

`ValidationError.errors()` 會提供 field、錯誤類型及訊息，後端回傳 `422`，前端可以據此顯示欄位錯誤。

## 3. Marshmallow serialization

```python
class MessageSchema(Schema):
    id = fields.Int(required=True)
    username = fields.Str(required=True)
    content = fields.Str(required=True)

message_schema.dump(messages)
```

序列化將 SQLAlchemy object 轉換成穩定嘅公開格式。欄位白名單亦有安全好處：資料庫新增 password hash、internal flag 等欄位時，不會意外洩露到 API response。

`textContent` 用於瀏覽器渲染留言，避免把使用者輸入當成 HTML 執行。

## 4. JWT + AI API

`POST /api/chat` 同留言 POST 一樣受 `@token_required` 保護：

```text
Client -> Authorization: Bearer JWT + JSON prompt
Decorator -> 驗證簽名、exp、user id
Pydantic -> 驗證 prompt、temperature
Provider -> 呼叫 mock/Groq/Gemini
Client <- { provider, model, answer }
```

順序好重要：先認證，再驗證輸入，最後先消耗外部 AI API。無效 request 唔應該消耗 token quota。

## 5. Provider abstraction

環境變數控制 provider：

```bash
export LLM_PROVIDER=mock
export LLM_MODEL=llama-3.1-8b-instant
```

`mock` 唔需要 API key，適合課堂、單元測試及前端開發。Groq：

```bash
export LLM_PROVIDER=groq
export GROQ_API_KEY='在終端機輸入你自己的 key'
export LLM_MODEL='llama-3.1-8b-instant'
```

Gemini：

```bash
export LLM_PROVIDER=gemini
export GEMINI_API_KEY='在終端機輸入你自己的 key'
export LLM_MODEL='gemini-1.5-flash'
```

API key 只放 server environment，唔可以放入 HTML、JavaScript、git 或 JWT payload。正式應用亦要加入 timeout、retry/backoff、rate limit、request budget、敏感資料過濾及 provider error monitoring。

## 6. 狀態碼設計

| 狀態碼 | 意義 | Day 7 例子 |
| --- | --- | --- |
| `200` | 成功 | 登入、讀取留言、AI 回應 |
| `201` | 資源已建立 | 註冊、建立留言 |
| `400` | 基本 request 格式錯誤 | 帳號欄位錯誤 |
| `401` | 沒有有效 JWT | 呼叫 chat 但無 Bearer token |
| `409` | 資源衝突 | 帳號重複 |
| `422` | JSON 形狀或欄位值不符合 schema | prompt 空白、temperature 超界 |
| `502` | 上游 provider 回應失敗 | Groq/Gemini network 或 provider error |
| `503` | 本機配置不完整 | provider 選 groq 但無 API key |

## 7. 執行及測試

```bash
cd Day7
pip install Flask Flask-SQLAlchemy PyJWT Pydantic Marshmallow groq google-genai
python app.py
```

開啟 `http://127.0.0.1:5000/`，用 `admin / admin123` 登入。預設 `mock` provider 會立即回應，毋須真實 key。

未登入測試：

```bash
curl -i -X POST http://127.0.0.1:5000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"hello"}'
```

應收到 `401`。取得 JWT 後，用無效 schema 測試：

```bash
curl -i -X POST http://127.0.0.1:5000/api/chat \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -d '{"prompt":"", "temperature": 9}'
```

應收到 `422`，而有效 request 應收到 `200` 及 `{ "provider": "mock", "answer": "..." }`。

## 課堂練習

1. 為 `ChatResponse` 加入 `usage` schema，回傳 token usage（provider 有提供時）。
2. 將留言建立 `created_at`，用 Marshmallow `DateTime` 輸出 ISO 8601。
3. 為 prompt 加入最大 request size 及簡單敏感資料遮罩。
4. 為 Groq/Gemini provider 寫 mock-based unit test，測試 timeout 及 `502` response。
5. 實作 conversation history，但限制每次送到 provider 嘅總字數。