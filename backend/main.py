from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi import FastAPI
from pydantic import BaseModel
from rag import load_docs, search_docs
from llm import ask_llm
from priority import determine_priority
from sla import assign_sla
from offer_logic import get_offer_faq_query
from typing import Dict, List
from mock_offer_api import resolve_offer_id_by_title, get_offer_status
from offer_logic import get_offer_faq_query
from typing import Dict, List, Optional




# =========================
# Chat Memory (In-Memory)
# =========================
# chat_memory = []     # stores conversation
# MAX_TURNS = 5        # user + bot pairs


chat_sessions: Dict[str, List[str]] = {}
MAX_TURNS = 5

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins (OK for local dev)
    allow_credentials=True,
    allow_methods=["*"],  # allow POST, OPTIONS, etc.
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str
    selected_offer: Optional[str] = None

@app.on_event("startup")
def startup():
    load_docs()

# @app.post("/chat")
# def chat(req: ChatRequest):
#     docs = search_docs(req.message)

#     context = "\n".join(docs)
#     prompt = f"""
# You are a customer support assistant.
# Answer ONLY using the context below.
# If you don't know, say you will connect to a human agent.

# Context:
# {context}

# User Question:
# {req.message}
# """

    
    
#     return StreamingResponse(
#         ask_llm(prompt),
#         media_type="text/plain"
#     )

### this is the working code ###
# @app.post("/chat")
# def chat(req: ChatRequest):

#     # 1️⃣ Add user message to memory
#     chat_memory.append(f"User: {req.message}")

#     # 2️⃣ Trim memory if too long
#     if len(chat_memory) > MAX_TURNS * 2:
#         chat_memory.pop(0)

#     # 3️⃣ Search knowledge base
#     priority = determine_priority(req.message)
#     sla = assign_sla(priority)
#     print(f"Priority: {priority}")
#     print(f"SLA: {sla}")
#     docs = search_docs(req.message)
#     if priority == "HIGH" or not docs or len(docs)==0:
#         return StreamingResponse(
#         iter(["I’m not sure about this. Let me connect you to a human agent."]),
#         media_type="text/plain"
#     )

#     # 4️⃣ Build context and memory text
#     context = "\n".join(docs)
#     memory_text = "\n".join(chat_memory)

#     # 5️⃣ Build prompt
#     prompt = f"""
# You are a customer support assistant.

# Use the conversation history and the context below.

# IMPORTANT RULES:
# - Answer ONLY from the context
# - If answer is missing or unclear, say:
#   "I’m not sure about this. Let me connect you to a human agent."

# Conversation History:
# {memory_text}

# Context:
# {context}

# User Question:
# {req.message}
# """

#     # 6️⃣ Stream response AND store bot reply in memory
#     def stream():
#         full_answer = ""
#         for chunk in ask_llm(prompt):
#             full_answer += chunk
#             yield chunk

#         # store bot reply
#         chat_memory.append(f"Bot: {full_answer}")

#     return StreamingResponse(stream(), media_type="text/plain")


@app.post("/chat")
def chat(req: ChatRequest):

    # ─────────────────────────────
    # Session-based memory
    # ─────────────────────────────
    if req.session_id not in chat_sessions:
        chat_sessions[req.session_id] = []

    chat_memory = chat_sessions[req.session_id]
    chat_memory.append(f"User: {req.message}")

    if len(chat_memory) > MAX_TURNS * 2:
        chat_memory.pop(0)

    # ─────────────────────────────
    # Offer resolution
    # ─────────────────────────────
    offer_id = None
    offer_data = None
    
    if req.selected_offer:
        offer_id = resolve_offer_id_by_title(req.selected_offer)
        if offer_id:
            offer_data = get_offer_status(offer_id)

    # ─────────────────────────────
    # Priority & SLA
    # ─────────────────────────────
    priority = determine_priority(req.message)
    sla = assign_sla(priority)

    print("Priority:", priority)
    print("SLA:", sla)
    print("Offer ID:", offer_id)

    # ─────────────────────────────
    # Knowledge Base Search
    # ─────────────────────────────
    if offer_data:
        faq_query = get_offer_faq_query(offer_data)
        docs = search_docs(
        query=f"{faq_query} {req.message}",
        offer_name=req.selected_offer
    )
    else:
        docs = search_docs(req.message)


    # ─────────────────────────────
    # Human fallback check
    # ─────────────────────────────
    if priority == "HIGH" or not docs or len(docs) == 0:
        fallback_msg = "I’m not sure about this. Let me connect you to a human agent."
        chat_memory.append(f"Bot: {fallback_msg}")

        return StreamingResponse(
            iter([fallback_msg]),
            media_type="text/plain"
        )

    # ─────────────────────────────
    # Build context & memory
    # ─────────────────────────────
    context = "\n".join(docs)
    memory_text = "\n".join(chat_memory)

    # ─────────────────────────────
    # Prompt
    # ─────────────────────────────
    prompt = f"""
You are a customer support assistant.

Priority Level: {priority}
Expected SLA: {sla}

IMPORTANT RULES:
- Answer ONLY from the context
- If answer is missing or unclear, say:
  "I’m not sure about this. Let me connect you to a human agent."

Conversation History:
{memory_text}

Context:
{context}

User Question:
{req.message}
"""

    # ─────────────────────────────
    # Stream response + save memory
    # ─────────────────────────────
    def stream():
        full_answer = ""
        for chunk in ask_llm(prompt):
            full_answer += chunk
            yield chunk

        chat_memory.append(f"Bot: {full_answer}")

    return StreamingResponse(stream(), media_type="text/plain")
