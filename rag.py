import httpx

OLLAMA = "http://localhost:11434"
EMBED_MODEL = "bge-m3"
CHAT_MODEL = "qwen2.5:3b"

PROMPT = (
    "只根據以下資料回答問題。如果資料中沒有答案，請回答「資料中沒有相關資訊」，不要推測補充額外內容。\n\n"
    "請用繁體中文回答。\n\n"
    "資料：\n{context}\n\n問題：{question}"
)


def load_chunks(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return [c.strip() for c in text.split("\n\n") if c.strip()]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b)


async def embed(client, texts):
    r = await client.post(f"{OLLAMA}/api/embed", json={"model": EMBED_MODEL, "input": texts})
    r.raise_for_status()
    return r.json()["embeddings"]


async def retrieve(client, question, chunks, vectors, k=2):
    q_vec = (await embed(client, [question]))[0]
    scored = [(cosine(q_vec, v), c) for v, c in zip(vectors, chunks)]
    scored.sort(reverse=True)
    return scored[:k]


async def generate(client, question, contexts):
    prompt = PROMPT.format(context="\n\n".join(contexts), question=question)
    r = await client.post(
        f"{OLLAMA}/api/generate",
        json={"model": CHAT_MODEL, "prompt": prompt, "stream": False},
    )
    r.raise_for_status()
    return r.json()["response"]