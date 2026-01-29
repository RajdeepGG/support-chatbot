import os
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, ListFlowable, ListItem, PageBreak
from reportlab.lib.units import inch

ROOT = "/Users/rajdeeproy/ai_ticket_responder"
TXT_PATH = os.path.join(ROOT, "Workflow_Overview.txt")
PDF_PATH = os.path.join(ROOT, "Workflow_Overview.pdf")
LOGO_PATHS = [
    os.path.join(ROOT, "assets", "greedygame_logo.png"),
    os.path.join(ROOT, "ui", "greedygame_logo.png"),
]

def build_pdf():
    doc = SimpleDocTemplate(PDF_PATH, pagesize=LETTER, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleXL", fontSize=20, leading=24, spaceAfter=16, textColor=colors.HexColor("#0b2c6a")))
    styles.add(ParagraphStyle(name="H2", fontSize=14, leading=18, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#0b2c6a")))
    styles.add(ParagraphStyle(name="Body", fontSize=10.5, leading=14))
    styles.add(ParagraphStyle(name="Footer", fontSize=9, leading=12, textColor=colors.HexColor("#6a7692")))
    story = []

    # Header with logo or brand text
    logo = None
    for p in LOGO_PATHS:
        if os.path.exists(p):
            logo = p
            break
    if logo:
        img = Image(logo, width=3.2*inch, height=0.7*inch)
        story.append(img)
    else:
        story.append(Paragraph("GREEDYGAME", styles["TitleXL"]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("AI Ticket Responder — Workflow Overview", styles["TitleXL"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Professional summary of architecture, tech stack, and guided user experience.", styles["Body"]))
    story.append(Spacer(1, 18))

    # Helper bullets
    def bullets(items):
        return ListFlowable([ListItem(Paragraph(i, styles["Body"])) for i in items], bulletType="bullet", start="bullet", leftIndent=16)

    # Summary
    story.append(Paragraph("Summary", styles["H2"]))
    story.append(bullets([
        "Guided support for offer-related queries with FAQ-driven answers and guard rails.",
        "Web UI connects via WebSocket to a FastAPI backend; responses stream from a local LLM with RAG context.",
        "Features include status-aware guidance, inactivity nudges, domain guard, input validation, rate limiting, content filtering, and expired-offer recommendations.",
    ]))
    story.append(Spacer(1, 10))

    # Tech Stack
    story.append(Paragraph("Tech Stack", styles["H2"]))
    story.append(bullets([
        "Frontend: HTML/CSS/JavaScript, WebSocket client",
        "Backend: FastAPI (HTTP + WebSocket)",
        "Knowledge: FAQs (data/faqs.txt) embedded with Chroma (rag.py)",
        "LLM: Ollama HTTP API streaming (llm.py), model via env vars",
        "Business logic: offer status handling (offer_logic.py), mock API (mock_offer_api.py)",
        "Guard rails: validation, rate limiting, content filtering, domain guard (guard_rails.py)",
    ]))
    story.append(Spacer(1, 10))

    # Components
    story.append(Paragraph("Core Components", styles["H2"]))
    story.append(bullets([
        "UI: Header with offer title and status badge; message bubbles; contextual suggestion buttons; input row revealed only when user opts to type.",
        "Backend: WebSocket /ws streams bot output; HTTP /chat kept for compatibility; background inactivity monitor sends 30s nudge.",
        "RAG + LLM: rag.search_docs retrieves FAQ context; llm.ask_llm streams text; prompt enforces concise, professional tone.",
        "Offer Logic: Status-aware queries and quick recommendations for expired offers.",
        "Guard Rails: Input validation, per-IP rate limiting, content filtering, and domain guard to avoid off-topic replies.",
    ]))
    story.append(Spacer(1, 10))

    # End-to-End Flow
    story.append(Paragraph("End-to-End Flow (Typed Issue)", styles["H2"]))
    story.append(bullets([
        "User selects offer; header shows title + status badge; status-specific guidance appears.",
        "User chooses “I’d rather type out my issue”; input row appears.",
        "Message is sent over WebSocket with offer_id; UI shows user bubble then creates bot bubble.",
        "process_chat: validation → filtering → rate limiting → domain guard → offer context → RAG → LLM streaming.",
        "UI fills the bot bubble as chunks stream; backend sends a delimiter to close the bubble.",
        "Expired offers append a brief list of quick alternative offers.",
        "If idle for 30s, the backend sends a professional nudge.",
    ]))
    story.append(Spacer(1, 10))

    # Guided Flow
    story.append(Paragraph("Guided Button Flow (No Typing)", styles["H2"]))
    story.append(bullets([
        "Ongoing/Completed: “I’m not able to complete the offer” → Help Options: Watch 2‑min guide (CTA) or Step‑by‑step instructions (bullets); then browse offers or report issue.",
        "Expired: “Check out other available offers” or “Report this issue to us”.",
        "Reporting opens mailto:support@greedygame.com with prefilled subject/body; transcript records selection as user bubble.",
        "Browse other offers displays quick alternatives from the dropdown; selection switches offer context and resets guidance.",
        "End Chat closes the flow with a thank‑you and hides inputs.",
    ]))
    story.append(Spacer(1, 10))

    # Connections
    story.append(Paragraph("Connections Overview", styles["H2"]))
    story.append(bullets([
        "UI ↔ Backend: WebSocket streaming for live replies; HTTP is retained as backup.",
        "Backend ↔ RAG: rag.search_docs uses embedded FAQs; prompt merges retrieved context.",
        "Backend ↔ LLM: llm.ask_llm streams text from Ollama; errors are surfaced as text.",
        "Backend Guard Rails: Pre‑LLM checks gate requests; post‑LLM filtering sanitizes final text.",
    ]))
    story.append(Spacer(1, 10))

    # Ops
    story.append(Paragraph("Operational Notes", styles["H2"]))
    story.append(bullets([
        "Start backend: uvicorn main:app --reload --port 8000 (from backend/ within venv).",
        "Configure LLM: OLLAMA_URL and MODEL_NAME env vars if non‑default.",
        "Update FAQs: edit data/faqs.txt and restart; RAG collection resets on startup.",
        "Security: no secrets in repo; avoid sending PII; domain guard deflects non‑offer topics.",
    ]))
    story.append(Spacer(1, 10))

    # Key Files
    story.append(Paragraph("Key Files", styles["H2"]))
    story.append(bullets([
        f"Backend entry: {ROOT}/backend/main.py",
        f"UI: {ROOT}/ui/index.html",
        f"RAG: {ROOT}/backend/rag.py",
        f"LLM client: {ROOT}/backend/llm.py",
        f"Offer logic: {ROOT}/backend/offer_logic.py",
        f"Mock offers: {ROOT}/backend/mock_offer_api.py",
        f"Guard rails: {ROOT}/backend/guard_rails.py",
        f"FAQs: {ROOT}/data/faqs.txt",
    ]))
    story.append(Spacer(1, 18))
    story.append(Paragraph("© GreedyGame — Internal Presentation Document", styles["Footer"]))

    doc.build(story)
    print(f"Generated: {PDF_PATH}")

if __name__ == "__main__":
    build_pdf()
