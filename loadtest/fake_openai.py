"""
Fake OpenAI-compatible server for load tests.

Serves just the two endpoints the backend uses, with deterministic content and configurable
latency, so load tests run without an API key, without cost and without rate limits:

    POST /v1/embeddings        -> deterministic 1536-dim unit vector derived from the input text
    POST /v1/chat/completions  -> JSON shaped like the real prompts in app/services/ai.py
                                  (job metadata, re-ranking list, bilingual match analysis)

Point the backend at it with environment variables only, so the same server works for any
commit (no code change needed):

    OPENAI_BASE_URL=http://127.0.0.1:9999/v1 OPENAI_API_KEY=stub

Run:  python loadtest/fake_openai.py --port 9999 --chat-latency-ms 400 --embed-latency-ms 100
"""
import argparse
import asyncio
import hashlib
import json
import re
import time

import numpy as np
import uvicorn
from fastapi import FastAPI, Request

EMBEDDING_DIM = 1536

app = FastAPI()
CONFIG = {"chat_latency_ms": 400.0, "embed_latency_ms": 100.0}
COUNTERS = {"embeddings": 0, "chat": 0}


def fake_embedding(text: str) -> list:
    """Deterministic unit vector for ``text`` (same text -> same vector, on any machine)."""
    seed = int.from_bytes(hashlib.sha256(text.encode("utf-8", "ignore")).digest()[:8], "big")
    vec = np.random.default_rng(seed).standard_normal(EMBEDDING_DIM)
    vec /= np.linalg.norm(vec)
    return vec.tolist()


def _chat_content(prompt: str) -> str:
    if "You must respond with only a list" in prompt:
        match = re.search(r"\((\d+) in total\)", prompt)
        count = int(match.group(1)) if match else 0
        return json.dumps(list(range(count)))
    if "job_summary" in prompt:
        language = "Korean" if "Respond in Korean" in prompt else "English"
        return json.dumps({
            "job_summary": f"[stub {language}] One sentence summary of the job.",
            "detail_analysis": f"[stub {language}]\n- Matching point one\n- Matching point two",
        })
    if "employment_type" in prompt:
        return json.dumps({
            "employment_type": "Full-time",
            "experience_level": "Junior",
            "skills": ["Python", "SQL", "Docker"],
        })
    return "[stub]"


@app.post("/v1/embeddings")
async def embeddings(request: Request):
    body = await request.json()
    COUNTERS["embeddings"] += 1
    await asyncio.sleep(CONFIG["embed_latency_ms"] / 1000)
    inputs = body.get("input")
    inputs = inputs if isinstance(inputs, list) else [inputs]
    return {
        "object": "list",
        "model": body.get("model", "text-embedding-3-small"),
        "data": [
            {"object": "embedding", "index": i, "embedding": fake_embedding(str(text))}
            for i, text in enumerate(inputs)
        ],
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    COUNTERS["chat"] += 1
    await asyncio.sleep(CONFIG["chat_latency_ms"] / 1000)
    prompt = "\n".join(str(m.get("content", "")) for m in body.get("messages", []))
    return {
        "id": f"chatcmpl-stub-{COUNTERS['chat']}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "gpt-4o-mini"),
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": _chat_content(prompt)},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@app.get("/stub-stats")
async def stub_stats():
    """Number of calls served so far (handy to confirm the backend really used the stub)."""
    return COUNTERS


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--chat-latency-ms", type=float, default=400.0, help="fixed delay per chat completion")
    parser.add_argument("--embed-latency-ms", type=float, default=100.0, help="fixed delay per embedding")
    args = parser.parse_args()
    CONFIG["chat_latency_ms"] = args.chat_latency_ms
    CONFIG["embed_latency_ms"] = args.embed_latency_ms
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
