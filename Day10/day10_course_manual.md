# Day 10：雲端 PaaS 部署、CI/CD 與期末評核

## 時數及學習成果

- 講授：0.5 小時
- 實習：1.5 小時

完成本課後，學員能夠：

1. 將容器化 Flask app 部署至 Render 或 Azure App Service。
2. 用環境變數/Secrets 管理 production 設定，而唔將 key 寫入程式碼。
3. 用 Gunicorn 作為 production WSGI server，理解其與 Flask development server 嘅分工。
4. 用 health endpoint、logs 及 smoke test 驗證部署。
5. 解釋基本 CI/CD pipeline 由 commit 到 deployment 嘅流程。

## 1. PaaS 部署模型

PaaS（Platform as a Service）提供 runtime、網絡、TLS、部署及部分運維能力。開發者主要交付 source code 或 container image，平台負責執行：

```text
git push -> CI/build -> Container image -> PaaS release -> HTTPS URL
                                      \
                                       -> logs / health check / rollback
```

Render、Azure App Service 及 Heroku 嘅介面不同，但核心概念相似：build、start command、port、environment variables、health check、logs。

## 2. Gunicorn 與 WSGI

Flask 內置 `app.run()` 係 development server，適合本機除錯，唔應直接承擔 production traffic。Gunicorn 係 WSGI server，會管理多個 worker/thread 並將 HTTP request 交畀 Flask application：

```bash
gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 60 app:app
```

`app:app` 代表「由 `app.py` 匯入名為 `app` 嘅 WSGI object」。容器必須 bind `0.0.0.0`，而且使用平台提供嘅 `$PORT`；只 bind `127.0.0.1` 或寫死 port，雲端 router 就無法連入。

worker 數量要按 CPU、記憶體及 workload 壓測調整。每個 worker 都會消耗記憶體，唔係越多越快。

## 3. Docker production image

Day 10 Dockerfile 做幾件重要事情：

1. 使用 slim base image 減少 image size。
2. 先 copy `requirements.txt`，利用 Docker layer cache。
3. 以非 root `appuser` 執行服務，降低 container escape 後嘅權限。
4. 用 Gunicorn 作 CMD。
5. 只透過 environment variables 注入設定。

本機 smoke test：

```bash
cd Day10
docker build -t flask-day10 .
docker run --rm -p 5000:5000 -e SECRET_KEY=local-test-secret flask-day10
```

另一個 terminal：

```bash
curl http://localhost:5000/healthz
curl http://localhost:5000/readyz
```

預期 `/healthz` 及 `/readyz` 都回 `200`。若無 `SECRET_KEY`，`/readyz` 回 `503`，呢個係示範配置檢查，不應將真正 secret 寫入 Dockerfile。

## 4. Render 部署步驟

本資料夾嘅 `render.yaml` 使用 Docker runtime、`/healthz` health check，並要求 Render 自動產生 `SECRET_KEY`：

1. 將 repository push 到 GitHub。
2. Render 選 **New Blueprint**，連接 repository。
3. 確認 `render.yaml` 被讀取，檢查 service name、Dockerfile path 及 health check。
4. 點選 deploy，等待 image build 及 release。
5. 到 service Logs 確認 Gunicorn listening；瀏覽公開 URL 加 `/healthz`。
6. 以 curl 做首頁及 ready check，記錄 deployment URL、commit SHA 及 release time。

Render environment variables 係 server-side secrets。API key、database URL、JWT secret 不應出現於 git、Docker image layer、browser JavaScript 或 log。

## 5. Azure App Service 部署方向

Azure Container Registry + App Service 常見流程：

1. 建立 ACR，build/tag/push image。
2. App Service 選 Linux Container，指向 ACR image。
3. 在 **Configuration > Application settings** 加 `SECRET_KEY`、`APP_ENV` 及其他設定。
4. 設定 container port `5000`，health check path `/healthz`。
5. 啟用 Application Insights/Log stream，部署後檢查 `/healthz`。
6. 用 deployment slot 先做 staging smoke test，再 swap 到 production。

平台 command、registry authentication、managed identity 同 pricing 會變化，實習時以 Azure portal/CLI 當時文件為準；原則係 secret 進平台設定，唔進 repository。

## 6. CI/CD 基礎

本課 `.github/workflows/deploy-render.yml` 示範 push 到 `main` 後呼叫 Render Deploy Hook。Deploy Hook URL 必須存成 GitHub Actions secret：

```text
Repository Settings -> Secrets and variables -> Actions
Name: RENDER_DEPLOY_HOOK_URL
Value: Render 產生嘅 private deploy hook URL
```

更完整 pipeline 應包含：

```text
lint/type check -> unit test -> docker build -> vulnerability scan
       -> deploy staging -> health/smoke test -> approval -> production
```

避免只用「push 就 production」而無測試或 rollback。正式 workflow 要 pin action versions、限制 secret 權限、保留 artifact、設定 concurrency，並讓失敗部署唔會覆蓋正常版本。

## 7. 觀測、故障排查及 rollback

遇到部署失敗，按以下次序：

1. Build log：requirements、Dockerfile、Python import 是否成功？
2. Runtime log：Gunicorn command、port、worker crash、missing env var？
3. Health check：`/healthz` 是否快速而不依賴外部服務？
4. Readiness：`/readyz` 是否指出缺少設定或依賴不可用？
5. Smoke test：首頁、主要 API、認證及外部服務是否正常？
6. Rollback：回到上一個已知正常 image/commit，先恢復服務再調查。

Health endpoint 應保持輕量；深度資料庫/Redis check 可另設 readiness check，避免暫時依賴故障令平台反覆重啟 app。

## 期末筆試評核建議

### 理論題

1. 解釋 development server 同 Gunicorn WSGI server 嘅差異。
2. 點解 Docker container 內要使用 `0.0.0.0` 同平台 `$PORT`？
3. `SECRET_KEY` 應該放喺邊度？點解唔可以 commit 入 git？
4. 描述 health check、readiness check、CI/CD 及 rollback 嘅關係。

### 實作題

要求學生：

1. 用提供嘅 Dockerfile build image。
2. 以非 root user 啟動 Gunicorn。
3. 設定 secret，成功通過 `/healthz` 及 `/readyz`。
4. 將 app deploy 到 Render 或 Azure App Service。
5. 提交公開 URL、Dockerfile、deployment log 截圖/紀錄及 smoke test 結果。

### 評分 rubric（100 分）

| 項目 | 分數 |
| --- | ---: |
| Docker image 可 build、可啟動 | 20 |
| Gunicorn、port 及 health check 設定正確 | 20 |
| PaaS 成功部署並可公開訪問 | 25 |
| Secrets 沒有硬編碼，配置安全 | 15 |
| CI/CD 或可重現部署流程 | 10 |
| Logs、smoke test、文件及故障處理說明 | 10 |

## 實習流程（1.5 小時）

1. 15 分鐘：本機執行 Gunicorn 及 curl health checks。
2. 25 分鐘：build image，檢查 image layers 及非 root user。
3. 30 分鐘：建立 Render service 或 Azure App Service，配置 port/secrets。
4. 15 分鐘：執行公開 URL smoke test，閱讀 logs。
5. 15 分鐘：設定 CI/CD deploy hook 或 staging deployment。
6. 10 分鐘：完成期末評核提交物及 rollback 演練。