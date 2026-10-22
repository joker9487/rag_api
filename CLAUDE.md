# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概述

一個精簡的 RAG（檢索增強生成）問答服務：由 FastAPI 提供 API，後端串接本機的 Ollama。Prompt、錯誤訊息與知識庫內容皆為繁體中文。

## 規則

- 一律以繁體中文回覆；任務相關內容（說明、文件、註解、commit 訊息等）都以中文為主。
- 修改任何檔案前，先說明要改什麼。
- `CLAUDE.md` 可在需要時由 Claude 自行更新（例如專案結構或指令有變動時）。
- 不要修改 `docs.txt`。
- 測試使用 pytest，且不能真的呼叫 Ollama：用 `monkeypatch` 換掉 `rag.embed`、`rag.generate`，參考 `test/test_app.py` 的 `client` fixture。

## 常用指令

所有指令都必須在專案根目錄執行，因為 `app.py` 啟動時以相對路徑讀取 `docs.txt`。

```bash
# 啟動 API（需要 Ollama 在 localhost:11434 運行，並已下載下列模型）
python -m uvicorn app:app --reload

# 執行全部測試（不需要 Ollama，embed/generate 已被 monkeypatch）
python -m pytest -v

# 執行單一測試
python -m pytest -v test/test_app.py::test_health
```

需要的 Ollama 模型：`ollama pull bge-m3`（向量）與 `ollama pull qwen2.5:3b`（對話）。

安裝相依套件：開發與測試用 `python -m pip install -r requirements-dev.txt`（含 pytest）；`requirements.txt` 只放執行期套件，Docker 映像檔只安裝這份。版本皆固定。

CI（`.github/workflows/test.yml`）在 push 與 pull request 時於 Ubuntu + Python 3.13 安裝 `requirements-dev.txt` 並執行 `python -m pytest -v`；CI 上沒有 Ollama，因此測試必須維持 monkeypatch。

### Docker

```bash
docker compose up --build
```

- Ollama 不在 Docker 內，跑在主機上；API 容器透過 `OLLAMA_URL=http://host.docker.internal:11434` 連線（compose 已加 `extra_hosts`，Linux 上也可解析）。Linux 主機的 Ollama 需設 `OLLAMA_HOST=0.0.0.0` 才接受容器連線。
- `docs.txt` 以唯讀 volume 掛入容器，修改後 `docker compose restart api` 即可，不必重新 build。
- 啟動時若連不到 Ollama，lifespan 會失敗使容器退出，由 `restart: unless-stopped` 自動重試。
- `mongo` 服務與 `MONGO_URL` 是預先建立的，程式目前尚未使用。

## 架構

- `rag.py` 是純 RAG 邏輯層：切段、餘弦相似度（純 Python，未使用 numpy）、以及非同步呼叫 Ollama（`/api/embed`、`/api/generate`）。模型名稱與 Ollama 位址是模組常數；Ollama 位址可用環境變數 `OLLAMA_URL` 覆寫（預設 `http://localhost:11434`）。所有網路函式的第一個參數都是共用的 `httpx.AsyncClient`，不會自行建立 client。
- `app.py` 把所有狀態放在模組層級的 `state` dict，於 FastAPI `lifespan` 中初始化：建立共用 client、將 `docs.txt` 依空行切段，並在啟動時一次算好所有段落的向量存在記憶體中。因此修改 `docs.txt` 後必須重啟服務。`/ask` 流程為 `rag.retrieve`（依餘弦相似度取前 k 段）→ `rag.generate`；`httpx.ConnectError` 會轉成 HTTP 503。
- `app.py` 透過模組屬性呼叫 `rag.embed` / `rag.generate`（使用 `import rag`，而非 `from rag import ...`），測試才能用 `monkeypatch.setattr(rag, ...)` 替換。請維持這種 import 寫法，否則測試會打到真的 Ollama。
- 測試使用 `with TestClient(app)`，才會執行 `lifespan`。`test_health` 斷言 chunk 數等於 `docs.txt` 中以空行分隔的段落數（目前為 6）。
- `ask.py` 是獨立的同步 Ollama 測試腳本，API 沒有使用它。

## 版控注意事項

- `.gitignore` 已排除 `__pycache__/`、`.pytest_cache/` 與 `*.log`。
- 開發在 feature 分支進行（例如 `feature/tests`），透過 PR 合併回 `main`。
