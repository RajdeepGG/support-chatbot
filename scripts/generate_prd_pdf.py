from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListItem, ListFlowable, Preformatted
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
PDF_PATH = DOCS_DIR / "PRD_AI_Ticket_Responder.pdf"

def bullets(items):
    return ListFlowable([ListItem(Paragraph(i, styles["Body"])) for i in items], bulletType="bullet", start="bullet", leftIndent=16)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontSize=20, spaceAfter=10))
styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"], fontSize=14, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#0b2c6a")))
styles.add(ParagraphStyle(name="Body", parent=styles["BodyText"], fontSize=10, leading=14))
styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, textColor=colors.grey))
styles.add(ParagraphStyle(name="Mono", parent=styles["BodyText"], fontName="Courier", fontSize=9, leading=12))

def diagram(text):
    return Preformatted(text, styles["Mono"])

def build_prd():
    doc = SimpleDocTemplate(str(PDF_PATH), pagesize=LETTER, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    story = []

    story.append(Paragraph("Product Requirements Document (PRD)", styles["H1"]))
    story.append(Paragraph("AI Ticket Responder", styles["H2"]))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles["Small"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("1. Overview / Summary", styles["H2"]))
    story.append(Paragraph(
        "AI Ticket Responder is a lightweight support assistant for offer‑related queries. It serves concise, KB‑anchored answers using Retrieval‑Augmented Generation (RAG) with an on‑host LLM. Users interact through a Web UI (and Android WebView). Responses stream over WebSockets from a FastAPI backend deployed behind Caddy (HTTPS).", styles["Body"]))
    story.append(Spacer(1, 6))

    story.append(Paragraph("2. User Flow", styles["H2"]))
    story.append(bullets([
        "User opens Chat Support (WebView or browser).",
        "If an offer is selected: header shows title and status; otherwise, generic Chat Support.",
        "User types a message or selects a guided option.",
        "Backend validates → filters → checks domain scope → retrieves KB → streams answer.",
        "If user chooses to raise a ticket, UI calls Android.openTicket(...) to open the native ticket screen."
    ]))
    story.append(diagram(
"""    +-----------+        wss://              +---------+      +--------+      +-------+
    |  Web UI   |  <---------------------->  | Caddy   | ---> | FastAPI | --> | RAG   |
    | (Browser/ |                            | (HTTPS) |      | Backend |     | Chroma|
    |  WebView) |  https://brudlab.com/ui    +---------+      +--------+      +---+---+
    +-----+-----+                                                        |      +-------+
          | Android.openTicket(JSON)                                     |-->   | LLM   |
          v                                                               |      |Ollama|
    +-----------+                                                         |      +-------+
    | Ticket    | <------------------------------------------------------+               
    | Screen    |                                                                        
    +-----------+                                                                        
"""))

    story.append(Paragraph("3. Technical Architecture", styles["H2"]))
    story.append(bullets([
        "Frontend: Single‑page HTML/JS (ui/index.html) renders chat, suggestions, and streaming bubbles.",
        "Backend: FastAPI (backend/main.py) exposes /ws and /chat; streams text with a delimiter at end.",
        "RAG: backend/rag.py builds embeddings with MiniLM and queries Chroma; strict top‑1 retrieval with synonym normalization.",
        "LLM: backend/llm.py calls Ollama (MODEL_NAME via env); short outputs and low temperature for concise answers.",
        "Guard Rails: backend/guard_rails.py with input validation, rate limiting, content filter, and domain guard.",
        "Deployment: Caddy serves TLS and reverse‑proxies to backend bound on 127.0.0.1:8080; Cloudflare DNS/Proxy optional."
    ]))

    story.append(Paragraph("4. API Specifications", styles["H2"]))
    story.append(Paragraph("4.1 WebSocket: /ws", styles["Body"]))
    story.append(bullets([
        "Connect: wss://<domain>/ws",
        "Client → Server: JSON { message: string, offer_id?: string }",
        "Server → Client: text chunks; final delimiter “\\n\\n” closes the bubble",
        "Events: {event:\"start_typing\"}, {event:\"end_chat\"} for nudges and lifecycle"
    ]))
    story.append(Paragraph("4.2 HTTP streaming: POST /chat", styles["Body"]))
    story.append(bullets([
        "Request: { \"message\": \"...\" }",
        "Response: text/plain streamed in chunks; same delimiter “\\n\\n”"
    ]))
    story.append(Paragraph("4.3 Static UI", styles["Body"]))
    story.append(bullets([
        "GET /ui → HTML UI",
        "GET /icons, /videos"
    ]))

    story.append(Paragraph("5. Database / Data Model", styles["H2"]))
    story.append(bullets([
        "No persistent user DB in v1; stateless per‑session chat.",
        "KB Document format (data/faqs.txt):",
    ]))
    story.append(diagram(
"""Q: <question>
A:
- <bullet line 1>
- <bullet line 2>
Keywords: comma,separated,terms

"""))
    story.append(bullets([
        "Embedding Store: Chroma collection “support_docs”",
        "Fields: id (string), document (text), embedding (vector)",
        "Runtime Session: in‑memory – typing indicators and current bot bubble only"
    ]))

    story.append(Paragraph("6. Functional Requirements", styles["H2"]))
    story.append(bullets([
        "Short, policy‑aligned answers derived strictly from KB context.",
        "Out‑of‑scope messages return a fixed deflection line.",
        "Auto‑suggestions for common states (ongoing/completed/expired).",
        "Ticket handoff: Android.openTicket(JSON) opens the native ticket screen."
    ]))

    story.append(Paragraph("7. Performance & SLOs", styles["H2"]))
    story.append(bullets([
        "TTFB (warm) ≤ 3s; P95 total ≤ 8s for short answers.",
        "Num predict ~64–96; temperature ~0.1–0.2; keep_alive 10–30m.",
        "Parallelism tuned to VM cores; prioritize single‑request latency."
    ]))

    story.append(Paragraph("8. Security & Privacy", styles["H2"]))
    story.append(bullets([
        "TLS at edge via Caddy; backend bound to localhost.",
        "No PII storage; content filter and domain guard prevent sensitive topics.",
        "Minimal logging; avoid message bodies in production logs."
    ]))

    story.append(Paragraph("9. Deployment & Ops", styles["H2"]))
    story.append(bullets([
        "Docker Compose: ollama + backend (+ caddy).",
        "DNS A record → VM; Cloudflare proxy optional; SSL/TLS mode Full/Strict.",
        "Update KB: edit data/faqs.txt and restart backend."
    ]))

    story.append(Paragraph("10. Risks & Mitigations", styles["H2"]))
    story.append(bullets([
        "Model drift → Sanitizer + domain guard replacement.",
        "Cold starts → keep_alive + warmup call.",
        "Synonym miss → query normalization + consistent KB bullets."
    ]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Generated from repository structure and current implementation.", styles["Small"]))

    doc.build(story)
    print(f"Generated: {PDF_PATH}")

if __name__ == "__main__":
    build_prd()
