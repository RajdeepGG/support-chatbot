from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import rag
import priority
import sla
import offer_logic
import llm
import mock_offer_api

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory chat history (for demonstration)
chat_memory = []

@app.on_event("startup")
async def startup_event():
    print("Loading knowledge base...")
    rag.load_docs()

class ChatRequest(BaseModel):
    message: str
    offer_id: Optional[str] = None

@app.post("/chat")
async def chat(request: ChatRequest):
    user_msg = request.message
    offer_id = request.offer_id
    
    chat_memory.append(f"User: {user_msg}")

    # 1. Determine Priority
    priority_level = priority.determine_priority(user_msg)
    print(f"Priority: {priority_level}")

    # 2. Get Offer Context (if applicable)
    offer_context_query = ""
    if offer_id:
        offer = mock_offer_api.get_offer_details(offer_id)
        if offer:
            offer_context_query = offer_logic.get_offer_faq_query(offer)
    
    # 3. Construct Search Query
    # We combine user message with offer context to guide RAG
    search_query = f"{user_msg} {offer_context_query}".strip()
    
    # 4. Search Knowledge Base
    docs = rag.search_docs(search_query)
    
    # 5. Fallback Logic
    # Only fallback if no relevant documents are found.
    # We previously blocked HIGH priority, but that prevented valid KB answers.
    if not docs or len(docs) == 0:
        fallback_msg = "I’m not sure about this. Let me connect you to a human agent."
        chat_memory.append(f"Bot: {fallback_msg}")
        return StreamingResponse(
            iter([fallback_msg]),
            media_type="text/plain"
        )

    # 6. Generate Response with LLM
    context_str = "\n\n".join(docs)
    
    system_prompt = (
        "You are a helpful support assistant. Use the following context to answer the user's question. "
        "If the answer is not in the context, say you don't know. "
        "Keep the answer concise and helpful."
    )
    
    full_prompt = f"{system_prompt}\n\nContext:\n{context_str}\n\nUser Question: {user_msg}\nAnswer:"

    return StreamingResponse(
        llm.ask_llm(full_prompt),
        media_type="text/plain"
    )
