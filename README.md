# RAG API

一個精簡的 RAG（檢索增強生成）問答服務。把 `docs.txt` 裡的文件切成段落並轉成向量，收到問題時找出最相關的段落，再交給本機 Ollama 上的 LLM，只根據這些段落用繁體中文回答。每次問答都會記錄到 MongoDB，可以透過 API 查詢歷史紀錄。

## 請求流程

```
服務啟動（lifespan）
  └─ 讀取 docs.txt → 依空行切段 → bge-m3 向量化 → 向量存在記憶體
  └─ 建立 MongoDB 連線（rag.qa_logs）

POST /ask
  1. 問題 → bge-m3 向量化
  2. 與所有段落計算餘弦相似度，取前 k 段
  3. 段落 + 問題組成 prompt → qwen2.5:3b 生成答案
  4. 問答寫入 MongoDB（失敗只記 log，不影響回應）
  5. 回傳答案與來源段落

GET /history
  └─ 從 MongoDB 依時間由新到舊取出最近的問答紀錄
```

## API 說明

服務啟動後，可以在 `http://localhost:8000/docs` 開啟 FastAPI 自動產生的 Swagger UI 直接測試。

### `GET /health`

回傳服務狀態，以及知識庫切出的段落數。

```json
{"status": "ok", "chunks": 6}
```

### `POST /ask`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `question` | string | 必填，至少 1 個字 |
| `k` | int | 取幾段相關資料，預設 2，範圍 1–5 |

請求範例：

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "機房溫度要維持幾度？", "k": 2}'
```

> Windows 的終端機直接在指令裡打中文，容易因為編碼問題收到 `400 There was an error parsing the body`，建議改用 `/docs` 頁面測試。

回應範例（實際執行結果）：

```json
{
  "answer": "機房溫度要維持在 18 到 27 度之間。",
  "sources": [
    {
      "score": 0.776,
      "text": "伺服器機房位於 B 棟 3 樓，進入需刷員工證並登記。機房溫度應維持在 18 到 27 度之間。"
    },
    {
      "score": 0.453,
      "text": "當伺服器磁碟使用率超過 85% 時，系統會自動發送警告信給維運人員，需在 24 小時內處理。"
    }
  ]
}
```

`score` 是餘弦相似度，取到小數點後 3 位。

錯誤回應：

| 狀態碼 | 情況 |
|---|---|
| 422 | `question` 是空字串，或 `k` 不在 1–5 之間 |
| 503 | 連不到 Ollama（`{"detail": "無法連線到 Ollama"}`） |

### `GET /history`

| 查詢參數 | 型別 | 說明 |
|---|---|---|
| `limit` | int | 回傳幾筆，預設 10，範圍 1–50 |

```bash
curl "http://localhost:8000/history?limit=5"
```

回應是陣列，依 `created_at` 由新到舊排序。每筆包含 `question`、`k`、`answer`、`sources`、`created_at`（不含 MongoDB 的 `_id`）：

```json
[
  {
    "question": "機房溫度要維持幾度？",
    "k": 2,
    "answer": "機房溫度要維持在 18 到 27 度之間。",
    "sources": [{"score": 0.776, "text": "伺服器機房位於 B 棟 3 樓，..."}],
    "created_at": "2026-10-23T05:10:00.123000"
  }
]
```

錯誤回應：

| 狀態碼 | 情況 |
|---|---|
| 422 | `limit` 不是整數或不在 1–50 之間 |
| 503 | 連不到 MongoDB（`{"detail": "無法連線到資料庫"}`） |

## 使用技術

- **FastAPI**、**Pydantic**：API 與請求驗證
- **httpx**（AsyncClient）：非同步呼叫 Ollama
- **Ollama**：`bge-m3`（向量）、`qwen2.5:3b`（生成）
- **MongoDB**（`pymongo` 的 `AsyncMongoClient`）：問答紀錄
- **pytest**：測試
- **Docker / Docker Compose**、**GitHub Actions**：部署與 CI

## 本機執行

需要 Python 3.13 和 [Ollama](https://ollama.com)。所有指令都要在專案根目錄執行，因為服務啟動時是用相對路徑讀取 `docs.txt`。

1. 下載模型（Ollama 要保持執行中）：

```bash
ollama pull bge-m3
```

```bash
ollama pull qwen2.5:3b
```

2. 安裝套件：

```bash
python -m pip install -r requirements.txt
```

3. （選用）啟動 MongoDB。沒有 MongoDB 的話，`/ask` 仍可使用，只是不會留紀錄，`/history` 會回傳 503。可以只用 compose 起資料庫：

```bash
docker compose up -d mongo
```

4. 啟動服務：

```bash
python -m uvicorn app:app --reload
```

服務在 `http://localhost:8000`。啟動時會先把所有段落向量化，所以 Ollama 必須已經在執行。

## 用 Docker Compose 執行

```bash
docker compose up --build
```

- 會啟動兩個服務：`api`（port 8000）和 `mongo`（`mongo:7`，port 27017，資料存在 `mongo_data` volume）。
- **Ollama 不在容器內**，要跑在主機上。API 容器透過 `http://host.docker.internal:11434` 連線，compose 已經設定 `extra_hosts`，Linux 上也解析得到。Linux 主機的 Ollama 需要設定 `OLLAMA_HOST=0.0.0.0`，才會接受容器的連線。
- `docs.txt` 以唯讀 volume 掛進容器。修改後重啟就好，不用重新 build：

```bash
docker compose restart api
```

- 啟動時如果連不到 Ollama，服務會啟動失敗、容器退出，再由 `restart: unless-stopped` 自動重試。
- 映像檔以非 root 使用者執行，並設有 `HEALTHCHECK`（打 `/health`，`start-period` 60 秒，留時間給啟動時的向量計算）。

## 環境變數

| 變數 | 預設值 | 說明 |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama 位址（結尾的 `/` 會被去掉） |
| `MONGO_URL` | `mongodb://localhost:27017` | MongoDB 連線字串 |

Docker Compose 中分別設為 `http://host.docker.internal:11434` 和 `mongodb://mongo:27017`。模型名稱是寫在 `rag.py` 裡的常數，不能用環境變數設定。

## 執行測試

測試**不需要** Ollama 和 MongoDB：`rag.embed`、`rag.generate`、`db.save_log`、`db.get_history` 都用 `monkeypatch` 換成假函式。

```bash
python -m pip install -r requirements-dev.txt
```

```bash
python -m pytest -v
```

只跑單一測試：

```bash
python -m pytest -v test/test_app.py::test_ask_ok
```

CI（`.github/workflows/test.yml`）在 push 和 pull request 時，於 Ubuntu + Python 3.13 安裝 `requirements-dev.txt` 並執行 `python -m pytest -v`。

## 設計重點

- **啟動時一次算好向量**：`lifespan` 載入文件並向量化所有段落，每次請求只需要向量化問題本身。
- **共用一個 `httpx.AsyncClient`**：`rag.py` 的網路函式都把 client 當作第一個參數傳入，不會各自建立連線。
- **模組屬性呼叫，方便測試**：`app.py` 用 `import rag`、`import db`，再透過 `rag.embed(...)` 這類寫法呼叫，測試才能用 `monkeypatch.setattr(rag, ...)` 換掉外部依賴。
- **限制答案來源**：prompt 要求模型只根據檢索到的資料回答，資料裡沒有答案時要回答「資料中沒有相關資訊」。
- **紀錄失敗不影響問答**：`db.save_log` 會攔下 `PyMongoError`，只記錄錯誤 log，`/ask` 照常回傳答案。
- **明確的錯誤對應**：連不到 Ollama 回 503，連不到 MongoDB 時 `/history` 回 503，參數不合法由 Pydantic 回 422。

## 已知限制

- **知識庫只有一個檔案**：只讀取 `docs.txt`，而且只依空行切段，沒有依長度切分或重疊。
- **向量只存在記憶體**：每次啟動都要重新計算，修改 `docs.txt` 後要重啟服務。檢索是純 Python 逐一計算餘弦相似度，只適合小量文件。
- **啟動依賴 Ollama**：Ollama 沒開時服務無法啟動。
- **只處理連線錯誤**：只有 `httpx.ConnectError` 會轉成 503。Ollama 回應逾時（120 秒）、模型沒有下載等其他錯誤，會變成 500。
- **沒有 MongoDB 時每次 `/ask` 會變慢**：連線逾時設為 2 秒，所以每次 `/ask` 會多等約 2 秒才放棄寫入紀錄。
- **模型寫死在程式裡**：要換模型得改 `rag.py`。
- **沒有串流、認證或速率限制**：回答一次回傳完整內容，`/history` 會公開所有問答紀錄。
- **MongoDB 沒有設定帳號密碼**：compose 的 MongoDB 沒有帳號密碼，又把 27017 port 開放到主機上。
