# Day 8：RAG、Vector Embeddings 與智能問答

## 時數及學習成果

- 講授：1.5 小時
- 實習：1.5 小時

完成本課後，學員能夠：

1. 解釋 RAG 嘅 chunking、embedding、vector search 及 generation pipeline。
2. 將私有文件切割成 chunks，產生向量並完成相似度檢索。
3. 建立帶有外部知識庫 context 嘅智能問答 API。
4. 顯示引用來源，令回答可以被人核對，而唔係盲目信任模型。

## 1. RAG 架構

一般 LLM 只知道訓練資料及 prompt 內容。RAG 先從外部知識庫找相關內容，再將內容放入 prompt：

```text
Private documents
      |
      v
Chunking -> Embedding -> Vector index
                              |
User question -> Query embedding -> Similarity search
                                      |
                                      v
                         Context + question -> LLM -> Answer + sources
```

RAG 唔係重新訓練模型，而係在 inference time 提供額外 context。文件更新時，只需要重新建立 index，通常比 fine-tuning 更適合頻繁變動嘅企業 FAQ。

## 2. Chunking

太長嘅文件直接送入模型會浪費 context window，亦令檢索粒度太粗；太短則會失去上下文。本範例以句子為單位，將內容合併到約 180 字嘅 chunk，並保存：

```python
DocumentChunk(chunk_id=0, source='shipping.md', text='...')
```

實務上可以按段落、標題、HTML/Markdown 結構或 token 數切割，並加入 overlap。切割後應抽樣檢查：每個 chunk 是否自洽、標題/權限 metadata 是否保留、敏感資料是否已移除。

## 3. Embedding 同 Vector Search

Embedding 係將文字映射到向量空間：語義相近嘅文字理想上會比較接近。今天的輕量實作以 TF-IDF 作為可解釋嘅 local embedding，每個 token 都有一個權重：

$$
\mathrm{tfidf}(t,d) = \mathrm{tf}(t,d) \times
\log\left(\frac{1 + N}{1 + \mathrm{df}(t)}\right) + 1
$$

對 query vector $q$ 同文件 vector $d$，用 cosine similarity 排序：

$$
\mathrm{cosine}(q,d) = \frac{q \cdot d}{\|q\|\|d\|}
$$

本範例用 Python dictionary 儲存 sparse vectors，適合幾份教學文件。大量資料應使用真正 embedding model 及 vector database，例如 pgvector、Qdrant、Weaviate 或 Milvus。

## 4. Retrieval 到 Prompt

`POST /api/ask` 嘅順序如下：

1. JWT decorator 驗證用戶。
2. Pydantic 驗證 `question` 同 `top_k`。
3. 將問題轉成 query vector。
4. 取最高分 top-k chunks。
5. 將 `[source#chunk_id] text` 放入 context。
6. 指示 LLM 只可根據 context 回答，找不到就回答「資料不足」。
7. 回傳 answer、provider、model 及 sources。

來源係 RAG 系統嘅重要可觀察性：沒有來源或 score 太低時，應該降低信心、要求澄清或拒絕回答，而唔係製造答案。
本範例用 `RAG_MIN_SCORE`（預設 `0.08`）過濾低相似度結果；threshold 應以驗證集調校，唔應盲目照抄。

## 5. 防止 prompt injection 及幻覺

文件本身可能包含「忽略之前指示」等惡意文字。檢索到嘅文件係 data，唔係 instruction；prompt 應該用清晰分隔符，並重申系統規則。仍然要：

- 對文件來源及租戶做 access control，唔可以因為相似度高就洩露別人文件。
- 對輸入、文件及輸出做敏感資料過濾。
- 設定 top-k、context size、token budget 及 rate limit。
- 記錄 query、source ids、scores、model、latency（避免記錄密碼/API key）。
- 用一組已知問題測試 answer correctness、groundedness、citation precision 及 latency。

「精確無幻覺」係設計目標，唔係任何 LLM 可以保證嘅性質；要靠檢索品質、prompt 約束、評估及人工 fallback 一起降低風險。

## 6. 執行及測試

```bash
cd Day8
pip install Flask Flask-SQLAlchemy PyJWT Pydantic groq google-genai
python app.py
```

預設 `LLM_PROVIDER=mock`，所以毋須 API key。用 `admin / admin123` 登入後，試問：

- `退款期限是幾多日？`：應檢索 `company_faq.md`。
- `香港本地送貨要幾耐？`：應檢索 `shipping.md`。
- `公司有冇提供太空旅行？`：應沒有相關 source，mock 回應會顯示沒有相關資料。

亦可以先測試未授權：

```bash
curl -i -X POST http://127.0.0.1:5000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"退款期限是幾多日？"}'
```

預期係 `401`。Groq/Gemini 使用方式跟 Day 7 相同，只將 environment provider 改為 `groq` 或 `gemini`，並在 server 設定對應 API key。

## 實習流程（1.5 小時）

1. 20 分鐘：閱讀 `split_into_chunks`，改變 chunk size 並觀察 `/api/knowledge`。
2. 25 分鐘：測試不同問題，記錄 top-k、source 及 score。
3. 25 分鐘：將 `TfidfVectorStore` 換成真正 embedding API 或 vector database。
4. 20 分鐘：加入文件 metadata filter，例如只查詢指定部門。
5. 20 分鐘：建立 10 條問題/標準答案，評估 retrieval hit rate 及回答是否有引用來源。

## 課堂練習

1. 加入 Markdown 文件上傳 API，限制檔案大小及副檔名，並重新建立 index。
2. 實作 overlap chunking，比較不同 overlap 對 retrieval score 嘅影響。
3. 加入最低 similarity threshold，低於 threshold 時直接回傳 `資料不足`。
4. 將 TF-IDF 替換為 `sentence-transformers` embedding，並比較語義問題嘅效果。
5. 加入 `tenant_id` metadata，驗證公司 A 絕對檢索不到公司 B 嘅文件。