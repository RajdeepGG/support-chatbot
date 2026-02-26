import requests
import json
import os


def _normalize_url(u: str) -> str:
    u = (u or "").strip()
    if "/api/generate" in u:
        return u
    return u.rstrip("/") + "/api/generate"


OLLAMA_URL = _normalize_url(os.getenv("OLLAMA_URL", "http://ollama:11434/api/generate"))
MODEL_NAME = os.getenv("MODEL_NAME", "phi:latest")

# Tunable defaults for faster responses; override via env if needed
LLM_NUM_PREDICT = int(os.getenv("LLM_NUM_PREDICT", "120"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
LLM_TOP_K = int(os.getenv("LLM_TOP_K", "40"))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.9"))
LLM_REPEAT_PENALTY = float(os.getenv("LLM_REPEAT_PENALTY", "1.1"))
LLM_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "10m")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))


def ask_llm(prompt):
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": True,
        "options": {
            "num_predict": LLM_NUM_PREDICT,
            "temperature": LLM_TEMPERATURE,
            "top_k": LLM_TOP_K,
            "top_p": LLM_TOP_P,
            "repeat_penalty": LLM_REPEAT_PENALTY,
        },
        "keep_alive": LLM_KEEP_ALIVE,
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=LLM_TIMEOUT)
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode("utf-8"))
                    if "response" in data:
                        yield data["response"]
                except json.JSONDecodeError:
                    continue
    except requests.RequestException as e:
        yield f"Error communicating with LLM: {str(e)}"
