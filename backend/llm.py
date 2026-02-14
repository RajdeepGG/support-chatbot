import requests
import json
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "https://phi-1052636139195.europe-west1.run.app/api/generate")
MODEL_NAME = os.getenv("MODEL_NAME", "phi:latest")

def ask_llm(prompt):
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": True
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, stream=True)
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
