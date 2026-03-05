from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListItem, ListFlowable, Table, TableStyle, PageBreak
from reportlab.lib.units import inch
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

def build_prd():
    doc = SimpleDocTemplate(str(PDF_PATH), pagesize=LETTER, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    story = []

    # Title
    story.append(Paragraph("Product Requirements Document (PRD)", styles["H1"]))
    story.append(Paragraph("AI Ticket Responder", styles["H2"]))
    story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles["Small"]))
    story.append(Spacer(1, 10))

    # Overview
    story.append(Paragraph("1. Overview", styles["H2"]))
    story.append(Paragraph(
        "AI Ticket Responder is a lightweight, on-device support assistant that answers offer-related questions using a curated FAQ knowledge base (RAG) and an on-host LLM via Ollama. It exposes a Web UI (and Android WebView) that streams responses over WebSockets from a FastAPI backend.", styles["Body"]))
    story.append(Spacer(1, 6))

    # Problem
    story.append(Paragraph("2. Problem Statement", styles["H2"]))
    story.append(bullets([
        "Manual ticket handling for routine offer queries (rewards/verification/withdrawal) increases support load and response times.",
        "Users need concise, trustworthy answers aligned with app policy and timelines.",
        "Connectivity limits and PII concerns make a self-hosted, domain‑scoped solution preferable to third‑party SaaS."
    ]))

    # Goals & Non-Goals
    story.append(Paragraph("3. Goals", styles["H2"]))
    story.append(bullets([
        "Deflect 60–80% of repetitive offer questions with KB‑anchored answers.",
        "Time‑to‑first‑token (warm) < 3s; total response < 8s for short answers.",
        "Strict domain guard: refuse non‑offer topics (banking/PII/medical/legal/etc.).",
        "Low‑ops deployment on a single VM using Docker Compose."
    ]))
    story.append(Paragraph("Non‑Goals", styles["H2"]))
    story.append(bullets([
        "Human handoff tooling beyond a simple deflection message.",
        "Storing personal chat transcripts or building a ticketing system.",
        "Multilingual support in v1 (EN only)."
    ]))

    # Personas & stories
    story.append(Paragraph("4. Personas & User Stories", styles["H2"]))
    story.append(bullets([
        "End user: ‘I installed the app and finished tasks; when will I be rewarded?’ → receives 24–48h guidance and next steps.",
        "End user: ‘UPI withdrawal not received’ → gets payout processing timeline and self‑checks.",
        "End user: ‘Referral reward not credited’ → gets referral rules and validation checks.",
        "Support lead: wants reduced ticket volume and consistent policy answers."
    ]))

    # Success metrics
    story.append(Paragraph("5. Success Metrics (KPIs)", styles["H2"]))
    story.append(bullets([
        "Deflection rate for top 10 questions ≥ 60%.",
        "Median TTFB (warm) ≤ 3s; P95 total ≤ 8s for short answers.",
        "Off‑topic compliance: ≥ 99% deflections for out‑of‑scope prompts.",
        "0 PII exposure in model outputs (monitored sampling)."
    ]))

    # Scope
    story.append(Paragraph("6. Scope (v1)", styles["H2"]))
    story.append(bullets([
        "Web UI hosted from the backend (and Android WebView).",
        "WebSocket streaming chat endpoint (/ws) and an HTTP fallback (/chat).",
        "RAG over docs in data/faqs.txt with Chroma embeddings (MiniLM).",
        "Guard rails: input validation, rate limiting, content filter, domain guard.",
        "Prod deployment behind Caddy (HTTPS) and Cloudflare DNS."
    ]))
    story.append(Paragraph("Out of Scope", styles["H2"]))
    story.append(bullets([
        "User auth and per‑user history.",
        "Admin UI for KB editing (file‑based updates only in v1)."
    ]))

    # System Overview
    story.append(Paragraph("7. System Overview", styles["H2"]))
    story.append(bullets([
        "Frontend: ui/index.html (single‑page HTML/JS).",
        "Backend: FastAPI (backend/main.py) with WebSocket + HTTP stream.",
        "RAG: backend/rag.py (Chroma, MiniLM), embedding at startup; top‑1 strict retrieval.",
        "LLM: backend/llm.py calling Ollama; model configured via env MODEL_NAME.",
        "Guard Rails: backend/guard_rails.py — InputValidator, RateLimiter, ContentFilter, DomainGuard."
    ]))

    # Functional Requirements
    story.append(Paragraph("8. Functional Requirements", styles["H2"]))
    story.append(bullets([
        "UI displays offer context and a chat area. On send, it streams bot text live.",
        "WS payload: {message, offer_id}; server streams chunks, ends with delimiter.",
        "RAG forms a search query from user message (+ optional offer status cues).",
        "Model prompt: concise, policy‑aligned; no pleasantries; ≤2 sentences or ≤5 bullets.",
        "Out‑of‑scope: immediately return a fixed deflection without invoking the model."
    ]))

    # Data & KB
    story.append(Paragraph("9. Knowledge Base (KB)", styles["H2"]))
    story.append(bullets([
        "Location: data/faqs.txt (Q/A/Keywords blocks; answers formatted with bullets).",
        "Synonym normalization (e.g., payout → withdrawal, referal → referral).",
        "KB reloads on backend restart; future: admin endpoint for hot reload."
    ]))

    # Performance / SLO
    story.append(Paragraph("10. Performance & SLOs", styles["H2"]))
    story.append(bullets([
        "Model warm‑up: keep_alive=10–30m; pre‑warm one token on startup.",
        "TTFB warm ≤ 3s; total ≤ 8s for short answers (P95).",
        "Ollama threads tuned to VM cores; NUM_PARALLEL=1–2."
    ]))

    # Security & Privacy
    story.append(Paragraph("11. Security & Privacy", styles["H2"]))
    story.append(bullets([
        "HTTPS via Caddy; backend bound to 127.0.0.1:8080 behind reverse proxy.",
        "No storage of PII; ContentFilter blocks sensitive outputs; DomainGuard deflects out‑of‑scope.",
        "Avoid logging message bodies in production logs."
    ]))

    # Observability & Ops
    story.append(Paragraph("12. Observability & Operations", styles["H2"]))
    story.append(bullets([
        "Container logs: ai-ticket-backend (Uvicorn) and caddy.",
        "Health: /ui HEAD 200; add /health for container probes.",
        "Deploy: Docker Compose with Ollama + backend (+ Caddy in prod)."
    ]))

    # Deployment
    story.append(Paragraph("13. Deployment", styles["H2"]))
    story.append(bullets([
        "Dev: Cloudflare quick tunnel for temporary HTTPS (wsHost=<tunnel>).",
        "Prod: A record → VM; Caddy terminates TLS; Cloudflare proxy optional.",
        "Android: WebView loads domain or Pages; wsHost = your domain (no https://)."
    ]))

    # Risks
    story.append(Paragraph("14. Risks & Mitigations", styles["H2"]))
    story.append(bullets([
        "Model drift → Sanitizer & domain guard post‑check replace off‑topic replies.",
        "Cold starts → keep_alive + warm‑up call.",
        "Poor recall for synonyms → query normalization + KB bullet formatting.",
    ]))

    # Open Questions
    story.append(Paragraph("15. Open Questions", styles["H2"]))
    story.append(bullets([
        "Do we need chat transcript export for analytics (while preserving privacy)?",
        "Should we persist Chroma to disk for larger KBs?",
        "Named tunnel or Cloud Run for stable public HTTPS without operating Caddy?"
    ]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Generated from repository structure and current implementation.", styles["Small"]))

    doc.build(story)
    print(f"Generated: {PDF_PATH}")

if __name__ == "__main__":
    build_prd()

