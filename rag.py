import httpx

OLLAMA = "http://localhost:11434"
EMBED_MODEL = "bge-m3"
CHAT_MODEL = "qwen2.5:3b"


def load_chunks(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return [c.strip() for c in text.split("\n\n") if c.strip()]


def embed(texts):
    r = httpx.post(
        f"{OLLAMA}/api/embed",
        json={"model": EMBED_MODEL, "input": texts},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["embeddings"]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    return dot / (norm_a * norm_b)


def retrieve(question, chunks, vectors, k=2):
    q_vec = embed([question])[0]
    scored = [(cosine(q_vec, v), c) for v, c in zip(vectors, chunks)]
    scored.sort(reverse=True)
    return scored[:k]


def ask(question, contexts):
    context_text = "\n\n".join(contexts)
    prompt = (
        f"資料：\n{context_text}\n\n"
        f"問題：{question}"
    )
    r = httpx.post(
        f"{OLLAMA}/api/generate",
        json={"model": CHAT_MODEL, "prompt": prompt, "stream": False},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["response"]


if __name__ == "__main__":
    chunks = load_chunks("docs.txt")
    vectors = embed(chunks)                     # 事前準備：每段轉向量（只做一次）
    print(f"共 {len(chunks)} 段，向量長度 {len(vectors[0])}\n")

    while True:
        question = input("問題（直接 Enter 結束）：")
        if not question:
            break
        results = retrieve(question, chunks, vectors)
        for score, chunk in results:
            print(f"  [{score:.3f}] {chunk[:30]}...")
        answer = ask(question, [c for _, c in results])
        print(f"回答：{answer}\n")