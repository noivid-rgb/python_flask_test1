# Day 5：前後端分離與 RESTful API

## 課程目標

完成本課後，學生可以：

1. 分辨傳統 Server-side Rendering 同前後端分離。
2. 用 Flask 建立回傳 JSON 嘅 RESTful API。
3. 用 `fetch()` 非同步讀取及新增留言，避免 Page Reload。
4. 根據 HTTP 狀態碼處理成功、驗證失敗及未授權情況。

## 1. 由模板提交到 API

Day 4 嘅流程係：瀏覽器送出 HTML form，Flask 寫入資料庫，再回傳一張完整 HTML 頁面。Day 5 將流程拆開：

```text
Browser loads /                      -> Flask returns HTML shell
JavaScript fetches GET /api/messages -> Flask returns JSON
JavaScript fetches POST /api/messages -> Flask validates JSON and writes DB
Flask returns JSON                   -> JavaScript updates only the message list
```

前端負責畫面同互動，後端負責資料及規則。日後 React、Vue、手機 App 都可以重用相同 API。

## 2. RESTful API 設計

本課將留言視為 `messages` resource：

| HTTP method | URL | 用途 | 成功狀態碼 |
| --- | --- | --- | --- |
| `GET` | `/api/messages` | 讀取全部留言 | `200 OK` |
| `POST` | `/api/messages` | 建立一則留言 | `201 Created` |
| `POST` | `/api/login` | 建立登入 session | `200 OK` |
| `POST` | `/api/logout` | 清除登入 session | `200 OK` |

API 只交換資料，不回傳用來排版嘅 HTML。`Content-Type: application/json` 告訴伺服器 request body 係 JSON；`jsonify()` 就會產生正確嘅 JSON response。

## 3. HTTP 狀態碼

可以將 response 狀態分成以下幾類：

$$
\text{2xx} = \text{請求成功}, \qquad
\text{4xx} = \text{客戶端請求有問題}, \qquad
\text{5xx} = \text{伺服器處理失敗}
$$

本課重點：

- `200 OK`：GET、登入或登出成功。
- `201 Created`：新會員或新留言已建立。
- `400 Bad Request`：JSON 格式錯誤、缺少欄位或內容為空。
- `401 Unauthorized`：未登入或帳密錯誤。
- `409 Conflict`：註冊時帳號已存在。

狀態碼係程式可判斷嘅合約；錯誤訊息則提供人類可理解嘅補充資料。

## 4. Fetch API 非同步流程

```javascript
const response = await fetch('/api/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: 'Hello API' })
});
const data = await response.json();
```

`fetch()` 會回傳 Promise。先檢查 `response.ok`，再解析 `response.json()`；唔好只依賴 `fetch()` 有冇 reject，因為 HTTP `400` 或 `401` 本身通常唔會令 Promise reject。

本範例用 `textContent` 渲染留言，而唔係將使用者輸入直接串入 `innerHTML`，避免留言內容被當成 HTML 執行。

## 5. 登入與資料驗證

Day 5 為咗保持 Day 4 嘅會員概念，後端用 Flask session 記住登入者。`POST /api/messages` 會先檢查 session，再檢查 body：

1. body 必須係 JSON object。
2. `content` 必須係文字。
3. 去除前後空白後不可為空。
4. 通過驗證先寫入 SQLite。

密碼只儲存 hash，唔儲存明文。正式部署時必須用環境變數設定 `SECRET_KEY`，並配合 HTTPS、CSRF 防護、輸入長度限制及更完整嘅錯誤記錄。

## 6. 執行及測試

```bash
cd Day5
python app.py
```

開啟 `http://127.0.0.1:5000/`，預設帳號係 `admin`，密碼係 `admin123`。課堂示範可以用瀏覽器 DevTools Network 分頁觀察：

```bash
curl http://127.0.0.1:5000/api/messages
curl -X POST http://127.0.0.1:5000/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"content":"未登入會收到 401"}'
```

第二個 request 預期會收到 `401 Unauthorized`。登入後再送出留言，就會收到 `201 Created`，而畫面只更新列表，唔會重新載入整頁。

## 課堂練習

1. 加入 `GET /api/messages/<id>`，不存在時回傳 `404 Not Found`。
2. 為留言加入建立時間，並以 ISO 8601 字串回傳。
3. 將前端嘅 `loadMessages()` 改成每 10 秒輪詢一次，觀察 API 如何支援多個客戶端。
4. 以 Postman 或另一個 HTML client 呼叫同一組 API，驗證前後端已經解耦。