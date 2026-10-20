import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:3b"

def ask(prompt):
    r = httpx.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": prompt, "stream": False},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["response"]

if __name__ == "__main__":
    print(ask("簡單解釋python是甚麼"))