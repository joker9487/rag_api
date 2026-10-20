from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import rag

state = {}


@asynccontextmanager
async def lifespan(app):
    state["client"] = httpx.AsyncClient(timeout=120)
    state["chunks"] = rag.load_chunks("docs.txt")
    state["vectors"] = await rag.embed(state["client"], state["chunks"])
    yield
    await state["client"].aclose()


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
    return {
        "answer": answer,
        "sources": [{"score": round(s, 3), "text": c} for s, c in results],
    }