# Day 6：JWT、API 安全防護與自訂 Decorator

## 課程目標

完成本課後，學生可以：

1. 解釋 JWT 嘅三段結構及簽名用途。
2. 由 Flask `/api/login` 簽發短效 access token。
3. 用自訂 `@token_required` 裝飾器保護 API。
4. 由 Fetch API 將 JWT 放入 `Authorization: Bearer <token>` header。
5. 正確處理 token 缺失、無效、過期及用戶不存在。

## 1. Stateful 同 Stateless

Day 5 將登入者放喺 server-side session，瀏覽器用 cookie 帶回 session id。伺服器需要保存 session 狀態，跨服務部署時通常要共享 session store。

Day 6 改用 JWT：伺服器簽發一張自包含嘅 token，之後每個 API request 自己帶 token。API 可以驗證簽名及 claims，而唔需要查詢 session。注意：無狀態唔代表無風險，token 一旦被盜仍然可以被使用，所以要用 HTTPS、短有效期及妥善嘅儲存策略。

## 2. JWT 結構

JWT 通常由三段 Base64URL 字串組成，中間以句點分隔：

```text
header.payload.signature
```

- **Header**：描述 token 類型及演算法，例如 `HS256`。
- **Payload**：claims，例如 `sub`（用戶 id）、`username`、`iat`（簽發時間）及 `exp`（過期時間）。
- **Signature**：伺服器用 secret key 對前兩段簽名，防止 payload 被竄改。

JWT payload 只係編碼，唔係加密。任何持有 token 嘅人都可能解碼 payload，所以唔好放密碼、信用卡或其他機密資料。

HS256 可抽象表示為：

$$
\mathrm{signature} = \mathrm{HMAC\mathchar`-SHA256}
\left(\mathrm{base64url(header)} \, . \,
\mathrm{base64url(payload)},\; \mathrm{SECRET\_KEY}\right)
$$

只有持有相同 secret key 嘅伺服器，先可以驗證簽名是否正確。前端唔應該持有 secret key。

## 3. 登入及驗證流程

```text
Client -- username/password --> POST /api/login
Client <-- JWT + expiry -------- 200 OK
Client -- Authorization: Bearer JWT --> POST /api/messages
Decorator -- decode + verify --> current_user
Client <-- message JSON -------- 201 Created
```

`/api/login` 只在帳密正確時簽發 token。`@token_required` 會：

1. 讀取 `Authorization` header。
2. 確認格式係 `Bearer <token>`。
3. 用相同 secret key 驗證簽名。
4. 驗證 `exp`，過期就拒絕。
5. 根據 `sub` 找回資料庫用戶。
6. 將 `current_user` 傳入真正嘅 view function。

裝飾器將共通安全規則集中管理，令每個受保護路由唔需要重複貼驗證程式。

## 4. API 狀態碼合約

| 狀態碼 | 意義 | Day 6 例子 |
| --- | --- | --- |
| `200 OK` | 請求成功 | 登入並取得 token、公開讀取留言 |
| `201 Created` | 新資源建立 | 註冊帳號、建立留言 |
| `400 Bad Request` | request body 或欄位不合法 | 缺少 `content`、非 JSON |
| `401 Unauthorized` | 沒有有效身份憑證 | 缺少、錯誤或過期 JWT |
| `409 Conflict` | 資源狀態衝突 | 帳號已存在 |

可以用以下分類理解狀態碼：

$$
\text{2xx} = \text{成功}, \qquad
\text{4xx} = \text{客戶端需要修正請求}, \qquad
\text{5xx} = \text{伺服器處理失敗}
$$

## 5. Browser Fetch 與 localStorage

登入成功後，前端將 token 放入 `localStorage`：

```javascript
localStorage.setItem('jwt_token', data.token);

fetch('/api/messages', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('jwt_token')}`
    },
    body: JSON.stringify({ content: 'Hello JWT' })
});
```

`localStorage` 方便教學及示範跨頁保留 token，但 production 應評估 XSS 風險；高安全性應用常考慮 HttpOnly、Secure、SameSite cookie 配合 CSRF 防護。無論選邊種方式，都唔可以將 JWT 當成加密資料庫。

前端渲染留言時使用 `textContent`，避免將使用者輸入直接放入 `innerHTML`。當 API 回 `401`，應清除 token 並要求用戶重新登入。

## 6. 執行及測試

先安裝依賴：

```bash
cd Day6
pip install Flask Flask-SQLAlchemy PyJWT Werkzeug
python app.py
```

開啟 `http://127.0.0.1:5000/`。預設示範帳號係 `admin`，密碼係 `admin123`。亦可以用 curl 觀察 API：

```bash
curl http://127.0.0.1:5000/api/messages
curl -X POST http://127.0.0.1:5000/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"content":"沒有 token，預期 401"}'
```

登入取得 token 後，再把 token 放入以下 request：

```bash
curl -X POST http://127.0.0.1:5000/api/messages \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -d '{"content":"由 JWT 保護嘅留言"}'
```

## 安全檢查清單

- production 使用長度足夠、由環境變數提供嘅 `SECRET_KEY`。
- 使用 HTTPS，避免 token 喺網絡上被截取。
- 設定合理而短嘅 access token expiry。
- JWT payload 不放敏感資料。
- 驗證 `algorithms` allow-list，唔接受客戶端任意指定演算法。
- 對 request body 做型別、空值及長度驗證。
- 401 response 唔洩露過多身份或資料庫細節。

## 課堂練習

1. 加入 refresh token，實作 access token 過期後重新換發。
2. 為 `POST /api/messages` 加入角色 claims，例如只有 `admin` 可以刪除留言。
3. 實作 `DELETE /api/messages/<id>`，只准留言作者或管理員操作。
4. 將 token 驗證錯誤分成「缺少」、「格式錯誤」及「已過期」，但保持對外訊息不洩露 secret 或內部資料。