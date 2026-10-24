from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from pymongo import AsyncMongoClient
import asyncio
from pymongo.errors import PyMongoError
import db
import rag
import logging
state = {}


@asynccontextmanager
async def lifespan(app):
    #模型
    state["client"] = httpx.AsyncClient(timeout=120)
    state["chunks"] = rag.load_chunks("docs.txt")
    state["vectors"] = await rag.embed(state["client"], state["chunks"])

    #mongo資料庫
    state["mongo"] = AsyncMongoClient(
            os.getenv("MONGO_URL", "mongodb://localhost:27017"),
            serverSelectionTimeoutMS=2000,
        )
    state["logs"] = state["mongo"]["rag"]["qa_logs"]
    yield
    await state["client"].aclose()
    await state["mongo"].close()


app = FastAPI(title="RAG API", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    k: int = Field(default=2, ge=1, le=5)


@app.get("/health")
async def health():
    return {"status": "ok", "chunks": len(state["chunks"])}


@app.post("/ask")
async def ask(req: AskRequest):
    client = state["client"]
    try:
        results = await rag.retrieve(client, req.question, state["chunks"], state["vectors"], req.k)
        answer = await rag.generate(client, req.question, [c for _, c in results])
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="無法連線到 Ollama")
    except httpx.HTTPStatusError as e:
        logging.error(f"Ollama 回傳錯誤：{e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=502, detail=f"Ollama 回傳錯誤：{e.response.status_code}")
    result = {
        "answer": answer,
        "sources": [{"score": round(s, 3), "text": c} for s, c in results],
    }
    await db.save_log(state["logs"], {
        "question": req.question,
        "k": req.k,
        **result,
        "created_at": datetime.now(timezone.utc),
    })
    return result

@app.post("/search")
async def search(req: AskRequest):
    client = state["client"]
    try:
        results = await rag.retrieve(client, req.question, state["chunks"], state["vectors"], req.k)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="無法連線到 Ollama")
    except httpx.HTTPStatusError as e:
        logging.error(f"Ollama 回傳錯誤：{e.response.status_code} {e.response.text}")
        raise HTTPException(status_code=502, detail=f"Ollama 回傳錯誤：{e.response.status_code}")
    result = {
        "sources": [{"score": round(s, 3), "text": c} for s, c in results],
    }
    return result
    


class BrokenCollection:
    async def insert_one(self, doc):
        raise PyMongoError("連不到資料庫")


@app.get("/history")
async def history(limit: int = Query(default=10, ge=1, le=50)):
    try:
        return await db.get_history(state["logs"], limit)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="無法連線到資料庫")