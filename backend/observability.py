import os
import time
import json
import hashlib
from prometheus_client import Counter, Histogram

ACCESS_COUNTER = Counter(
    "http_requests_total",
    "HTTP requests",
    ["method", "path", "status"],
)

ACCESS_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10],
)

ESCALATE_COUNTER = Counter(
    "escalate_events_total",
    "Escalation events",
)

CSAT_COUNTER = Counter(
    "csat_events_total",
    "CSAT events",
)

def _env(name, default):
    return os.getenv(name, default)

def _salt():
    return _env("LLM_LOG_SALT", "salt")

def _mode():
    return _env("LLM_LOG_MODE", "redacted").lower()

def _sample_rate():
    try:
        return float(_env("LLM_LOG_SAMPLE_RATE", "0.0"))
    except Exception:
        return 0.0

def _max_len():
    try:
        return int(_env("LLM_LOG_MAX_CHARS", "512"))
    except Exception:
        return 512

def _redact(text: str) -> str:
    import re
    t = text or ""
    t = re.sub(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "[EMAIL]", t)
    t = re.sub(r"\+?\d[\d\s\-\(\)]{7,}\d", "[PHONE]", t)
    t = re.sub(r"https?://\S+", "[URL]", t)
    t = re.sub(r"\b(?:\d[ -]*?){13,16}\b", "[ID]", t)
    t = re.sub(r"\b[\w.\-]+@[A-Za-z]{3,}\b", "[ID]", t)
    return t

def _hash(text: str) -> str:
    h = hashlib.sha256((_salt() + (text or "")).encode("utf-8")).hexdigest()
    return h

async def access_log_middleware(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = int((time.time() - start) * 1000)
    path = request.url.path
    method = request.method
    status = response.status_code
    ACCESS_COUNTER.labels(method, path, str(status)).inc()
    ACCESS_LATENCY.labels(method, path).observe(duration / 1000.0)
    try:
        rid = request.headers.get("x-request-id") or ""
        cip = request.client.host if request.client else ""
        js = {
            "component": "access",
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": duration,
            "request_id": rid,
            "client_ip": cip,
        }
        print(json.dumps(js, ensure_ascii=False))
    except Exception:
        pass
    return response

def log_llm(request_id: str, model: str, prompt: str, completion: str, duration_ms: int, tokens_prompt: int = 0, tokens_completion: int = 0, status: str = "ok"):
    mode = _mode()
    sr = _sample_rate()
    if mode == "off":
        js = {
            "component": "llm",
            "request_id": request_id,
            "model": model,
            "duration_ms": duration_ms,
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "status": status,
            "mode": mode,
        }
        print(json.dumps(js, ensure_ascii=False))
        return
    import random
    do_log = random.random() < sr if sr > 0 else False
    if not do_log:
        js = {
            "component": "llm",
            "request_id": request_id,
            "model": model,
            "duration_ms": duration_ms,
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "status": status,
            "mode": "meta",
        }
        print(json.dumps(js, ensure_ascii=False))
        return
    if mode == "full":
        p = prompt or ""
        c = completion or ""
        p = p[:_max_len()]
        c = c[:_max_len()]
        js = {
            "component": "llm",
            "request_id": request_id,
            "model": model,
            "duration_ms": duration_ms,
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "status": status,
            "mode": mode,
            "prompt": p,
            "completion": c,
        }
        print(json.dumps(js, ensure_ascii=False))
        return
    rp = _redact(prompt or "")[:_max_len()]
    rc = _redact(completion or "")[:_max_len()]
    js = {
        "component": "llm",
        "request_id": request_id,
        "model": model,
        "duration_ms": duration_ms,
        "tokens_prompt": tokens_prompt,
        "tokens_completion": tokens_completion,
        "status": status,
        "mode": "redacted",
        "prompt_preview": rp,
        "completion_preview": rc,
        "prompt_hash": _hash(prompt or ""),
        "completion_hash": _hash(completion or ""),
    }
    print(json.dumps(js, ensure_ascii=False))

