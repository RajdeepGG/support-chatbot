from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import asyncio
import time
import json
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

# -------------------------------------------------------------------------
# WebSocket Connection Manager with Inactivity Monitoring
# -------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.last_activity: Dict[WebSocket, float] = {}
        self.alerted: Dict[WebSocket, bool] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.update_activity(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.last_activity:
            del self.last_activity[websocket]
        if websocket in self.alerted:
            del self.alerted[websocket]

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    def update_activity(self, websocket: WebSocket):
        self.last_activity[websocket] = time.time()
        self.alerted[websocket] = False  # Reset alert status on new activity

manager = ConnectionManager()

# Background task to check for inactivity
async def inactivity_monitor():
    while True:
        await asyncio.sleep(5)  # Check every 5 seconds
        now = time.time()
        # Create a copy to iterate safely as connections might close
        for websocket in list(manager.active_connections):
            try:
                last = manager.last_activity.get(websocket, now)
                # If inactive for > 30 seconds and haven't alerted yet
                if now - last > 30 and not manager.alerted.get(websocket, False):
                    # Send nudge
                    nudge_msg = "\n\nBot: Are you still there? Let me know if you need more help!"
                    await manager.send_message(nudge_msg, websocket)
                    manager.alerted[websocket] = True
            except Exception as e:
                print(f"Error in inactivity monitor: {e}")
                manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    print("Loading knowledge base...")
    rag.load_docs()
    # Start the background monitor
    asyncio.create_task(inactivity_monitor())

# -------------------------------------------------------------------------
# Chat Logic (Refactored for reuse)
# -------------------------------------------------------------------------

async def process_chat(user_msg: str, offer_id: Optional[str]):
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
    search_query = f"{user_msg} {offer_context_query}".strip()
    
    # 4. Search Knowledge Base
    docs = rag.search_docs(search_query)
    
    # 5. Fallback Logic
    if not docs or len(docs) == 0:
        yield "I’m not sure about this. Let me connect you to a human agent."
        return

    # 6. Generate Response with LLM
    context_str = "\n\n".join(docs)
    
    system_prompt = (
        "You are a helpful support assistant. Use the following context to answer the user's question. "
        "If the answer is not in the context, say you don't know. "
        "Keep the answer concise and helpful."
    )
    
    full_prompt = f"{system_prompt}\n\nContext:\n{context_str}\n\nUser Question: {user_msg}\nAnswer:"

    # Yield chunks from LLM
    for chunk in llm.ask_llm(full_prompt):
        yield chunk

# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------

# Keep the HTTP endpoint for backward compatibility (optional, but good practice)
class ChatRequest(BaseModel):
    message: str
    offer_id: Optional[str] = None

@app.post("/chat")
async def chat(request: ChatRequest):
    async def response_generator():
        async for chunk in process_chat(request.message, request.offer_id):
            yield chunk
            
    return StreamingResponse(response_generator(), media_type="text/plain")

# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            manager.update_activity(websocket)
            
            # Parse Payload
            try:
                payload = json.loads(data)
                user_msg = payload.get("message", "")
                offer_id = payload.get("offer_id")
            except json.JSONDecodeError:
                user_msg = data
                offer_id = None
            
            if not user_msg:
                continue

            # Stream response back
            # We assume the UI has already printed "You: [msg]"
            # We print "Bot: " (or UI handles it)
            # Let's send a newline first to ensure separation if needed, or rely on UI formatting.
            
            async for chunk in process_chat(user_msg, offer_id):
                await manager.send_message(chunk, websocket)
            
            # Send a delimiter or just let it be? 
            # For this simple chat, we just stream chunks.
            # Update activity again after sending response
            manager.update_activity(websocket)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
