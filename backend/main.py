from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import asyncio
import time
import json
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
import priority
import sla
import offer_logic
import mock_offer_api
import guard_rails
CHAT_MODE = os.getenv("CHAT_MODE", "full")
if CHAT_MODE != "decision_tree":
    import rag
    import llm
else:
    rag = None
    llm = None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
UI_DIR = str(Path(__file__).resolve().parent.parent / "ui")
app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")
app.mount("/icons", StaticFiles(directory=Path(UI_DIR) / "icons"), name="icons")
app.mount("/videos", StaticFiles(directory=Path(UI_DIR) / "videos"), name="videos")

@app.get("/")
async def root_page():
    return FileResponse(Path(UI_DIR) / "index.html")

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

# -------------------------------------------------------------------------
# WebSocket Connection Manager with Inactivity Monitoring
# -------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.last_activity: Dict[WebSocket, float] = {}
        self.alerted: Dict[WebSocket, bool] = {}
        self.nudge_enabled: Dict[WebSocket, bool] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.nudge_enabled[websocket] = True
        self.update_activity(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        if websocket in self.last_activity:
            del self.last_activity[websocket]
        if websocket in self.alerted:
            del self.alerted[websocket]
        if websocket in self.nudge_enabled:
            del self.nudge_enabled[websocket]

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    def update_activity(self, websocket: WebSocket):
        self.last_activity[websocket] = time.time()
        self.alerted[websocket] = False  # Reset alert status on new activity

manager = ConnectionManager()

# Background task to check for inactivity
async def inactivity_monitor():
    while True:
        await asyncio.sleep(15)  # Check every 15 seconds
        now = time.time()
        # Create a copy to iterate safely as connections might close
        for websocket in list(manager.active_connections):
            try:
                last = manager.last_activity.get(websocket, now)
                # If inactive for > 30 seconds and haven't alerted yet
                if now - last > 30 and manager.nudge_enabled.get(websocket, True) and not manager.alerted.get(websocket, False):
                    # Send nudge
                    nudge_msg = "\n\nStill there? Reply if you need assistance."
                    await manager.send_message(nudge_msg, websocket)
                    manager.alerted[websocket] = True
            except Exception as e:
                print(f"Error in inactivity monitor: {e}")
                manager.disconnect(websocket)

@app.on_event("startup")
async def startup_event():
    print("Loading knowledge base...")
    if rag:
        rag.load_docs()
    # Start the background monitor
    asyncio.create_task(inactivity_monitor())

# -------------------------------------------------------------------------
# Chat Logic (Refactored for reuse)
# -------------------------------------------------------------------------

async def process_chat(user_msg: str, offer_id: Optional[str], client_ip: str = "unknown"):
    # 1. Input Validation
    validation_result = guard_rails.input_validator.validate_input(user_msg)
    if not validation_result["valid"]:
        yield validation_result["message"]
        return
    
    # 2. Content Filtering
    if guard_rails.content_filter.contains_blocked_content(user_msg):
        yield "I'm sorry, I cannot process this request due to security policies. Please contact support for assistance."
        return
    
    # 3. Rate Limiting
    if await guard_rails.rate_limiter.is_rate_limited(client_ip):
        yield "Rate limit exceeded. Please wait a moment before sending more messages."
        return
    
    # 4. Domain Guard: keep responses offer-related
    if guard_rails.domain_guard.is_out_of_scope(user_msg):
        yield "I can help with offer-related support. Please ask an offer-related question."
        return
    
    if CHAT_MODE == "decision_tree":
        yield "Please use the options above to continue."
        return
    
    # 5. Determine Priority
    priority_level = priority.determine_priority(user_msg)
    print(f"Priority: {priority_level}")

    # 2. Get Offer Context (if applicable)
    offer_context_query = ""
    offer = None
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
        "Keep the answer concise and helpful. "
        "Do not provide any information about credit cards, bank accounts, passwords, or other sensitive personal information. "
        "Do not discuss hacking, exploits, vulnerabilities, or illegal activities. "
        "If asked about sensitive topics, politely decline and suggest contacting support."
    )
    
    full_prompt = f"{system_prompt}\n\nContext:\n{context_str}\n\nUser Question: {user_msg}\nAnswer:"

    # Yield chunks from LLM and filter responses
    response_buffer = ""
    for chunk in llm.ask_llm(full_prompt):
        response_buffer += chunk
        yield chunk
    
    # Final content filtering on complete response
    filtered_response = guard_rails.content_filter.filter_response(response_buffer)
    if filtered_response != response_buffer:
        # If filtering occurred, yield the filtered version
        yield "\n" + filtered_response
    
    if offer_id:
        if not offer:
            offer = mock_offer_api.get_offer_details(offer_id)
        if offer and offer.get("user_status") == "EXPIRED" and "expired" in (offer_context_query or "").lower():
            recs = mock_offer_api.get_recommended_offers(exclude_offer_id=offer.get("offer_id"), limit=2)
            if recs:
                lines = []
                for r in recs:
                    title = r.get("title")
                    mins = r.get("estimated_time_minutes")
                    diff = r.get("difficulty")
                    lines.append(f"- {title} (~{mins} min, {diff})")
                yield "\n\nThis offer has expired. Recommended quick alternatives:\n" + "\n".join(lines)

# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------

# Keep the HTTP endpoint for backward compatibility (optional, but good practice)
class ChatRequest(BaseModel):
    message: str
    offer_id: Optional[str] = None

@app.post("/chat")
async def chat(request: ChatRequest, client_request: Request):
    client_ip = client_request.client.host if client_request.client else "unknown"
    
    async def response_generator():
        async for chunk in process_chat(request.message, request.offer_id, client_ip):
            yield chunk
            
    return StreamingResponse(response_generator(), media_type="text/plain")

# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    # Get client IP for rate limiting
    client_ip = websocket.client.host if websocket.client else "unknown"
    
    try:
        while True:
            data = await websocket.receive_text()
            manager.update_activity(websocket)
            
            # Parse Payload
            try:
                payload = json.loads(data)
                user_msg = payload.get("message", "")
                offer_id = payload.get("offer_id")
                event = payload.get("event")
            except json.JSONDecodeError:
                user_msg = data
                offer_id = None
                event = None
            
            if event == "clear_chat":
                manager.nudge_enabled[websocket] = True
                await manager.send_message("\n\n", websocket)
                manager.update_activity(websocket)
                continue
            
            if event == "end_chat":
                manager.nudge_enabled[websocket] = False
                await manager.send_message("\n\n", websocket)
                manager.update_activity(websocket)
                continue
            
            if not user_msg:
                continue

            # Stream response back
            async for chunk in process_chat(user_msg, offer_id, client_ip):
                await manager.send_message(chunk, websocket)
            await manager.send_message("\n\n", websocket)
            
            # Update activity again after sending response
            manager.update_activity(websocket)
            
            norm = user_msg.strip().lower()
            if any(p in norm for p in ["thanks", "thank you", "resolved", "clear now", "no more", "that helps", "issue resolved"]):
                manager.nudge_enabled[websocket] = False
            else:
                manager.nudge_enabled[websocket] = True
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
