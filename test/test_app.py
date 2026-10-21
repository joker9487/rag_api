import httpx
import pytest
from fastapi.testclient import TestClient

import rag
from app import app


async def fake_embed(client, texts):
    return [[1.0, 0.0] for _ in texts]       # 假向量


async def fake_generate(client, question, contexts):
    return "假的回答"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(rag, "embed", fake_embed)
    monkeypatch.setattr(rag, "generate", fake_generate)
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
    