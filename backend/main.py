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
import uuid
import observability
import offer_context as offer_context_mod
CHAT_MODE = os.getenv("CHAT_MODE", "full")
OFFER_CONTEXT_ENABLED = os.getenv("OFFER_CONTEXT_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
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
app.middleware("http")(observability.access_log_middleware)
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

@app.get("/metrics")
async def metrics():
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

# --------------------------------------------------------------------------
# WebSocket Connection Manager with Inactivity Monitoring
# --------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.last_activity: Dict[WebSocket, float] = {}
        self.alerted: Dict[WebSocket, bool] = {}
        self.nudge_enabled: Dict[WebSocket, bool] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.nudge_enabled[websocket] = False
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

# Track per-connection active generation task to allow cancellation on new messages
client_tasks: Dict[WebSocket, asyncio.Task] = {}

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

def _request_id_from_http(request: Request) -> str:
    return request.headers.get("x-request-id") or str(uuid.uuid4())

def _log_chat_request_safe(request_id: str, channel: str, message: str, offer_id: Optional[str], client_ip: str):
    try:
        observability.log_chat_request(
            request_id=request_id,
            channel=channel,
            message=message,
            offer_id=offer_id or "",
            client_ip=client_ip,
        )
    except Exception:
        pass

def _log_chat_response_safe(request_id: str, channel: str, response: str, duration_ms: int, offer_id: Optional[str], status: str = "ok"):
    try:
        observability.log_chat_response(
            request_id=request_id,
            channel=channel,
            response=response,
            duration_ms=duration_ms,
            offer_id=offer_id or "",
            status=status,
        )
    except Exception:
        pass

# -------------------------------------------------------------------------
# Chat Logic (Refactored for reuse)
# -------------------------------------------------------------------------

async def process_chat(user_msg: str, offer_id: Optional[str], offer_context: Optional[Dict] = None, client_ip: str = "unknown", request_id: Optional[str] = None):
    request_id = request_id or str(uuid.uuid4())
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
    
    norm_greet = user_msg.strip().lower()
    if norm_greet in {"hi", "hello", "hey", "yo"} or len(norm_greet) < 4:
        yield ("Thanks for reaching out. Please tell me your offer issue:\n"
               "- Rewards pending (24–48 hours)\n"
               "- Offer marked expired\n"
               "- App install not tracked\n"
               "- Withdrawal not received")
        return
    
    norm_thanks = norm_greet
    if any(p in norm_thanks for p in ["thanks", "thank you", "appreciated", "resolved", "issue resolved", "clear now"]):
        yield "Thank you. If you need further assistance, reply here or explore other available offers."
        return
    
    try:
        import re as _re
        _norm = _re.sub(r"\s+", " ", user_msg or "").strip().lower()
        _tokens = _re.findall(r"[a-z]+", _norm)
        _verbs = {"connect","escalate","talk","speak","transfer","reach","contact","open","create","submit","file","raise"}
        _targets = {"human","support","customer","care","agent","representative","associate","executive","person","service","team"}
        _has_verb = any(t in _verbs for t in _tokens) or any(any(v in t for v in _verbs) for t in _tokens)
        _has_target = any(t in _targets for t in _tokens) or any(any(trg in t for trg in _targets) for t in _tokens)
        _ticket = ("ticket" in _tokens or "request" in _tokens) and any(t in {"open","create","submit","file","raise"} for t in _tokens)
        if (_has_verb and _has_target) or _ticket:
            yield "One moment please..."
            return
    except Exception:
        pass
    
    if CHAT_MODE == "decision_tree":
        yield "Please use the options above to continue."
        return

    topic = offer_context_mod.detect_topic(user_msg)
    kb_only_topics = {
        "payout",
        "gift_card",
        "referral",
        "app_issue",
        "survey",
        "device_integrity",
        "account_hold",
        "support_contact",
        "refund",
    }

    summary = None
    offer_specific = None
    if topic not in kb_only_topics and OFFER_CONTEXT_ENABLED and offer_context:
        summary = offer_context_mod.summarize_offer_context(offer_context)
        if summary and not offer_id and summary.oid:
            offer_id = summary.oid
        if summary:
            offer_specific = offer_context_mod.offer_aware_response(summary, user_msg)
    
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
    if summary:
        offer_context_query = f"{offer_context_query}\n{offer_context_mod.offer_context_prompt(summary)}".strip()
    
    # 3. Construct Search Query
    # For KB-only topics, avoid polluting retrieval with offer details.
    if topic in kb_only_topics:
        search_query = user_msg.strip()
    else:
        search_query = f"{user_msg} {offer_context_query}".strip()
    
    # 4. Search Knowledge Base
    docs = rag.search_docs(search_query)
    
    # 5. Fallback Logic
    if not docs or len(docs) == 0:
        yield (
            "I didn’t understand that. Please explain in a bit more detail.\n"
            "- What issue are you facing (reward not received / offer expired / withdrawal not received)?"
        )
        return

    # 6. Generate Response with LLM
    def _clean_context(d: str) -> str:
        lines = []
        for ln in (d or "").splitlines():
            if ln.strip().lower().startswith("keywords:"):
                continue
            lines.append(ln)
        return "\n".join(lines).strip()
    context_docs = [ _clean_context(d) for d in docs[:2] ]
    context_str = "\n\n".join(context_docs)

    def _kb_answer_from_context(ctx: str) -> str:
        lines = (ctx or "").splitlines()
        out = []
        in_a = False
        for ln in lines:
            if ln.strip().startswith("A:"):
                in_a = True
                continue
            if in_a and ln.strip().startswith("Q:"):
                break
            if in_a:
                out.append(ln)
        text = "\n".join([l for l in out if l.strip()]).strip()
        if text:
            return text
        filtered = [ln for ln in lines if not ln.strip().startswith("Q:")]
        return "\n".join([ln for ln in filtered if ln.strip()][:6]).strip()

    def _get_best_kb() -> str:
        for c in context_docs:
            txt = _kb_answer_from_context(c)
            if txt:
                return txt
        return _kb_answer_from_context(context_str)

    if topic in kb_only_topics:
        kb_text = _get_best_kb()
        if kb_text:
            yield kb_text
            return

    if offer_specific:
        kb_text = _get_best_kb()
        combined = offer_specific
        if kb_text and kb_text not in offer_specific:
            combined = f"{offer_specific}\n\n{kb_text}"
        yield combined
        return
    
    system_prompt = (
        "You are a helpful offer-support assistant. Use ONLY the provided context to answer. "
        "If the exact answer is not in the context, provide the closest relevant guidance from it. "
        "Respond in the user's language when possible. "
        "Keep answers brief: max 80 words, or 3–5 concise bullets. "
        "Do not repeat sentences, do not invent examples, tables, or stories. "
        "Prefer clear, actionable guidance (e.g., typical verification window is 24–48 hours). "
        "Never include sensitive information or discuss illegal activities. "
        "If asked about sensitive topics, politely decline and suggest contacting support. "
        "Do not mention a website or external portal; if escalation is needed, say to raise a ticket from the app or contact support by email."
    )
    
    offer_block = ""
    if summary:
        offer_block = f"\n\nOffer Context:\n{offer_context_mod.offer_context_prompt(summary)}"
    full_prompt = f"{system_prompt}\n\nContext:\n{context_str}{offer_block}\n\nUser Question: {user_msg}\nAnswer:"

    # Yield chunks from LLM and filter responses
    response_buffer = ""
    llm_start = time.time()
    preview = ""
    stream_started = False
    tail = ""

    def _looks_like_prompt_echo(txt: str) -> bool:
        t = (txt or "").lower()
        return (
            "you are a helpful offer-support assistant" in t
            or "use only the provided context to answer" in t
            or "\ncontext:" in t
            or "user question:" in t
        )

    for chunk in llm.ask_llm(full_prompt):
        if stream_started:
            import re
            candidate = (tail + chunk)
            low = candidate.lower()
            m = re.search(r"(?:^|\n)\s*user question\b", low) or re.search(r"(?:^|\n)\s*answer\s*:?", low)
            if m:
                cut = m.start() - len(tail)
                if cut > 0:
                    out = chunk[:cut]
                    response_buffer += out
                    yield out
                return
            response_buffer += chunk
            tail = candidate[-250:]
            yield chunk
            continue

        preview += chunk
        if len(preview) < 200 and "\n" not in preview:
            continue

        if _looks_like_prompt_echo(preview):
            kb_text = _kb_answer_from_context(context_docs[0] if context_docs else context_str)
            if kb_text:
                yield kb_text
                return
            yield "Please raise a ticket from the app so our support team can help."
            return

        stream_started = True
        response_buffer += preview
        tail = preview[-250:]
        yield preview

    if not stream_started and preview:
        response_buffer += preview
        yield preview
    llm_ms = int((time.time() - llm_start) * 1000)
    
    # Sanitize tone and keep only concise, relevant text
    def _sanitize(text: str) -> str:
        t = text.strip()
        # Drop pleasantries and open-ended follow-ups
        blacklist = [
            r"(?i)\b(i'?m glad|happy to help|would you like|is there anything else|let me know|can i help with|feel free to ask)\b",
            r"(?i)\b(i can guide you|i can assist you)\b",
        ]
        import re
        for pat in blacklist:
            t = re.sub(pat, "", t)
        t = re.sub(r"\s{2,}", " ", t).strip()
        # Keep max 2 sentences or first 5 bullet lines
        bullets = [ln for ln in t.splitlines() if ln.strip().startswith(("*", "-"))]
        if bullets:
            return "\n".join(bullets[:5]).strip()
        # Sentence clamp
        sentences = re.split(r"(?<=[.!?])\s+", t)
        return " ".join(sentences[:2]).strip()

    sanitized = _sanitize(response_buffer)
    def _channelize(text: str) -> str:
        import re
        t = text
        t = re.sub(r"(?i)raise a ticket\s+(?:on|via)\s+(?:our\s+)?website", "raise a ticket from the app", t)
        t = re.sub(r"(?i)click the \"?chat with us\"?\s+button\s+on\s+(?:our\s+)?website", "open the app and use the support option", t)
        t = re.sub(r"(?i)on\s+(?:our\s+)?website", "in the app", t)
        t = re.sub(r"(?i)\[website url\]", "the app", t)
        return re.sub(r"\s{2,}", " ", t).strip()
    sanitized = _channelize(sanitized)
    um = (user_msg or "").lower()
    if (("completed" in um) and any(p in um for p in ["not get", "not received", "not credited", "didn't get", "did not get"])) or \
       (("reward" in um) and ("completed" in um)):
        sanitized = (
            "Your offer is completed but the reward is not credited.\n"
            "- Advertisers typically verify completion within 48–72 hours.\n"
            "- Keep the app/game installed and active during this window.\n"
            "- If it exceeds 72 hours, contact support with screenshots."
        )
    try:
        observability.log_llm(
            request_id=request_id,
            model=os.getenv("MODEL_NAME", ""),
            prompt=full_prompt,
            completion=sanitized,
            duration_ms=llm_ms,
            tokens_prompt=0,
            tokens_completion=0,
            status="ok",
        )
    except Exception:
        pass
    # Final content filtering on complete response (avoid duplicating full reply)
    filtered_response = guard_rails.content_filter.filter_response(sanitized)
    if guard_rails.domain_guard.response_off_topic(filtered_response):
        yield "\nI can help with offer-related support. Please ask an offer-related question."
        return
    if filtered_response != sanitized:
        if filtered_response.startswith(sanitized):
            note = filtered_response[len(sanitized):].strip()
            if note:
                yield "\n" + note
        else:
            yield "\n[Some content was removed due to policy]"
    
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
    offer_context: Optional[Dict] = None

@app.post("/chat")
async def chat(request: ChatRequest, client_request: Request):
    client_ip = client_request.client.host if client_request.client else "unknown"
    request_id = _request_id_from_http(client_request)
    _log_chat_request_safe(request_id, "http", request.message, request.offer_id, client_ip)
    
    async def response_generator():
        buf = []
        status = "ok"
        start = time.time()
        try:
            async for chunk in process_chat(request.message, request.offer_id, request.offer_context, client_ip, request_id=request_id):
                buf.append(chunk)
                yield chunk
        except Exception:
            status = "error"
            raise
        finally:
            _log_chat_response_safe(
                request_id,
                "http",
                "".join(buf),
                int((time.time() - start) * 1000),
                request.offer_id,
                status=status,
            )
            
    return StreamingResponse(response_generator(), media_type="text/plain")

class ChatSyncResponse(BaseModel):
    message_id: str
    text: str
    finish_reason: str = "stop"

@app.post("/v1/chat-sync", response_model=ChatSyncResponse)
async def chat_sync(request: ChatRequest, client_request: Request):
    client_ip = client_request.client.host if client_request.client else "unknown"
    request_id = _request_id_from_http(client_request)
    _log_chat_request_safe(request_id, "chat_sync", request.message, request.offer_id, client_ip)
    buf = []
    status = "ok"
    start = time.time()
    try:
        async for chunk in process_chat(request.message, request.offer_id, request.offer_context, client_ip, request_id=request_id):
            buf.append(chunk)
    except Exception:
        status = "error"
        raise
    finally:
        _log_chat_response_safe(
            request_id,
            "chat_sync",
            "".join(buf),
            int((time.time() - start) * 1000),
            request.offer_id,
            status=status,
        )
    return ChatSyncResponse(message_id=str(uuid.uuid4()), text="".join(buf), finish_reason="stop")

@app.post("/v1/chat-stream")
async def chat_stream(request: ChatRequest, client_request: Request):
    client_ip = client_request.client.host if client_request.client else "unknown"
    request_id = _request_id_from_http(client_request)
    _log_chat_request_safe(request_id, "chat_stream", request.message, request.offer_id, client_ip)
    async def gen():
        start = time.time()
        status = "ok"
        if guard_rails.domain_guard.is_out_of_scope(request.message or ""):
            response_text = "I can help with offer-related support. Please ask an offer-related question."
            yield json.dumps({"delta": response_text}) + "\n"
            _log_chat_response_safe(
                request_id,
                "chat_stream",
                response_text,
                int((time.time() - start) * 1000),
                request.offer_id,
                status=status,
            )
            yield json.dumps({"event": "end"}) + "\n"
            return
        buf = []
        try:
            async for chunk in process_chat(request.message, request.offer_id, request.offer_context, client_ip, request_id=request_id):
                buf.append(chunk)
                yield json.dumps({"delta": chunk}) + "\n"
        except Exception:
            status = "error"
            raise
        finally:
            _log_chat_response_safe(
                request_id,
                "chat_stream",
                "".join(buf),
                int((time.time() - start) * 1000),
                request.offer_id,
                status=status,
            )
        full = "".join(buf).strip()
        # Robust CTA detection
        import re
        norm = re.sub(r"\s+", " ", full).strip().lower()
        inorm = re.sub(r"\s+", " ", request.message or "").strip().lower()
        # Allow minor punctuation/spacing differences around 48 hours + contact support
        trigger_patterns = [
            r"if it exceed[s]?\s*48\s*hour[s]?,?\s*(please )?contact support",
            r"contact support.*48\s*hour[s]?",
            r"contact (?:our\s+)?support (?:team|desk|agent)s?",
            r"reach(?:ing)?\s+out\s+to\s+(?:our\s+)?official\s+channels",
            r"visit(?:ing)?\s+(?:our\s+)?help\s+center",
        ]
        escalate_patterns = [
            r"(let me|i will)?\s*(connect|escalate)\s+you(?:\s+\w+){0,3}\s+to\s+(?:a\s+)?human(?:\s+agent)?",
            r"not\s+able\s+to\s+connect\s+you(?:\s+\w+){0,3}\s+to\s+(?:a\s+)?human(?:\s+agent)?",
            r"talk to (a\s+)?human(\s+agent)?",
            r"not\s+(?:a\s+)?direct\s+contact\s+to\s+(?:a\s+)?human\s+agent[s]?",
        ]
        _tokens = re.findall(r"[a-z]+", inorm)
        _verbs = {"connect","escalate","talk","speak","transfer","reach","contact","open","create","submit","file","raise"}
        _targets = {"human","support","customer","care","agent","representative","associate","executive","person","service","team"}
        has_verb = any(t in _verbs for t in _tokens) or any(any(v in t for v in _verbs) for t in _tokens)
        has_target = any(t in _targets for t in _tokens) or any(any(trg in t for trg in _targets) for t in _tokens)
        ticket_intent = (("ticket" in _tokens or "request" in _tokens) and any(t in {"open","create","submit","file","raise"} for t in _tokens))
        ask_human_input = (has_verb and has_target) or ticket_intent
        should_cta = (
            any(re.search(p, norm) for p in trigger_patterns) or
            any(re.search(p, norm) for p in escalate_patterns) or
            ask_human_input
        )
        if should_cta:
            try:
                observability.ESCALATE_COUNTER.inc()
            except Exception:
                pass
            yield json.dumps({"event": "end", "action": {"type": "escalate_to_agent", "payload": {}}}) + "\n"
        else:
            try:
                observability.CSAT_COUNTER.inc()
            except Exception:
                pass
            yield json.dumps({"event": "end"}) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")

class EndSessionRequest(BaseModel):
    reason: Optional[str] = None

@app.post("/v1/session/end")
async def end_session(_: EndSessionRequest, client_request: Request):
    return {"ok": True}

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
                offer_context = payload.get("offer_context")
                event = payload.get("event")
                request_id = payload.get("request_id") or str(uuid.uuid4())
            except json.JSONDecodeError:
                user_msg = data
                offer_id = None
                offer_context = None
                event = None
                request_id = str(uuid.uuid4())
            
            if event == "clear_chat":
                manager.nudge_enabled[websocket] = True
                await manager.send_message("\n\n", websocket)
                manager.update_activity(websocket)
                continue
            
            if event == "start_typing":
                manager.nudge_enabled[websocket] = True
                manager.update_activity(websocket)
                continue
            
            if event == "end_chat":
                manager.nudge_enabled[websocket] = False
                await manager.send_message("\n\n", websocket)
                manager.update_activity(websocket)
                continue
            
            if not user_msg:
                continue

            _log_chat_request_safe(request_id, "ws", user_msg, offer_id, client_ip)

            # Cancel previous generation for this socket, if any
            prev = client_tasks.get(websocket)
            if prev and not prev.done():
                prev.cancel()
                try:
                    await prev
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            async def stream_to_ws(current_user_msg=user_msg, current_offer_id=offer_id, current_offer_context=offer_context, current_request_id=request_id):
                buf = []
                status = "ok"
                start = time.time()
                try:
                    async for chunk in process_chat(current_user_msg, current_offer_id, current_offer_context, client_ip, request_id=current_request_id):
                        buf.append(chunk)
                        await manager.send_message(chunk, websocket)
                    await manager.send_message("\n\n", websocket)
                except asyncio.CancelledError:
                    status = "cancelled"
                    raise
                except Exception:
                    status = "error"
                    raise
                finally:
                    _log_chat_response_safe(
                        current_request_id,
                        "ws",
                        "".join(buf),
                        int((time.time() - start) * 1000),
                        current_offer_id,
                        status=status,
                    )

            task = asyncio.create_task(stream_to_ws())
            client_tasks[websocket] = task
            # Do not await here; allow next user message to preempt this one
            
            # Update activity again after sending response
            manager.update_activity(websocket)
            
            norm = user_msg.strip().lower()
            if any(p in norm for p in ["thanks", "thank you", "resolved", "clear now", "no more", "that helps", "issue resolved"]):
                manager.nudge_enabled[websocket] = False
            else:
                manager.nudge_enabled[websocket] = True
            
    except WebSocketDisconnect:
        # Cleanup active task on disconnect
        prev = client_tasks.get(websocket)
        if prev and not prev.done():
            prev.cancel()
            try:
                await prev
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        if websocket in client_tasks:
            del client_tasks[websocket]
        manager.disconnect(websocket)
