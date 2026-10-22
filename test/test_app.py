import httpx
import pytest
from fastapi.testclient import TestClient

import rag
import db
from app import app
import asyncio

async def fake_embed(client, texts):
    return [[1.0, 0.0] for _ in texts]       # 假向量


async def fake_generate(client, question, contexts):
    return "假的回答"

async def fake_save(collection, doc):
    return None

async def fake_history( collection, limit):
    return [{"question": "fake log q", "answer": "fake log ans"}]



@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(rag, "embed", fake_embed)
    monkeypatch.setattr(rag, "generate", fake_generate)

    monkeypatch.setattr(db, "save_log", fake_save)
    monkeypatch.setattr(db, "get_history", fake_history)

    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code==200
    assert r.json()["chunks"]==6


def test_ask_empty_question(client):
    r = client.post("/ask", json={"question": ""})
    assert r.status_code==422


def test_ask_ok(client):
    r = client.post("/ask", json={"question": "上班時間是幾點？"})
    assert r.status_code==200
    assert r.json()["answer"]=="假的回答"
    assert len(r.json()["sources"])==2


def test_ask_k1(client):
    r = client.post("/ask", json={"question": "上班時間是幾點？", "k": 1})
    assert r.status_code==200
    assert len(r.json()["sources"])==1


@pytest.mark.parametrize("k", [0, 10])
def test_ask_k_out_of_range(client, k):
    r = client.post("/ask", json={"question": "上班時間是幾點？", "k": k})
    assert r.status_code==422


def test_ask_ollama_down(client, monkeypatch):
    async def broken_generate(client, question, contexts):
        raise httpx.ConnectError("連不到 Ollama")

    monkeypatch.setattr(rag, "generate", broken_generate)
    r = client.post("/ask", json={"question": "上班時間是幾點？"})
    assert r.status_code==503


def test_get_history(client):
    r = client.get("/history")
    assert r.status_code == 200
    assert r.json() == [{"question": "fake log q", "answer": "fake log ans"}]


def test_get_history_limit_out_of_range(client):
    r = client.get("/history?limit=0")
    assert r.status_code == 422

@pytest.mark.parametrize("limit", [0, 51, "abc"])
def test_history_bad_limit(client, limit):
    r = client.get(f"/history?limit={limit}")
    assert r.status_code == 422

import asyncio
from pymongo.errors import PyMongoError

import db


class BrokenCollection:
    async def insert_one(self, doc):
        raise PyMongoError("連不到資料庫")


def test_save_log_db_down(caplog):
    asyncio.run(db.save_log(BrokenCollection(), {"question": "q"}))
    assert "寫入問答紀錄失敗" in caplog.text

def test_history_db_down(client, monkeypatch):
    async def broken_history(collection, limit):
        raise PyMongoError("連不到資料庫")

    monkeypatch.setattr(db, "get_history", broken_history)
    r = client.get("/history")
    assert r.status_code == 503