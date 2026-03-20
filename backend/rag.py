from sentence_transformers import SentenceTransformer
import chromadb
import os
import re

client = chromadb.Client()
collection = client.get_or_create_collection("support_docs")

model = SentenceTransformer("all-MiniLM-L6-v2")

def load_docs():
    # Use absolute path relative to this file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(base_dir, "../data/faqs.txt")
    
    with open(data_path) as f:
        text = f.read()

    # Reset collection to avoid duplicates on reload
    try:
        client.delete_collection("support_docs")
    except Exception:
        pass
    global collection
    collection = client.get_or_create_collection("support_docs")

    chunks = text.split("\n\n")
    for i, chunk in enumerate(chunks):
        embedding = model.encode(chunk).tolist()
        collection.add(
            documents=[chunk],
            embeddings=[embedding],
            ids=[str(i)]
        )

def search_docs(query, offer_name=None):
    # Normalize common synonyms/misspellings to improve recall
    norm = query.lower()
    if not norm or len(norm.strip()) < 4:
        return []
    if re.fullmatch(r"\b(hi|hello|hey|yo|hola)\b", norm.strip()):
        return []
    # Common offer-support keywords to relax matching
    support_keywords = [
        "reward", "rewards", "wallet", "coin", "payout", "withdraw", "withdrawal",
        "verification", "pending", "completed", "expired", "status", "offer", "credit"
    ]
    replacements = {
        "payout": "withdrawal",
        "cashout": "withdrawal",
        "cash out": "withdrawal",
        "upi payout": "upi withdrawal",
        "referal": "referral",
        "referrel": "referral",
        "giftcard": "gift card",
    }
    for k, v in replacements.items():
        norm = norm.replace(k, v)
    search_text = norm
    embedding = model.encode(search_text).tolist()
    try:
        results = collection.query(
            query_embeddings=[embedding],
            n_results=5,
            include=["documents", "distances"]
        )
        docs = results.get("documents", [[]])[0] or []
        dists = results.get("distances", [[]])[0] or [None] * len(docs)
        # Dynamic threshold: relax for longer queries or known keywords
        has_keywords = any(k in norm for k in support_keywords)
        threshold = 0.25
        if len(norm) >= 12 or has_keywords:
            threshold = 0.45
        filtered = [doc for doc, dist in zip(docs, dists) if dist is None or dist <= threshold]
        # Controlled fallback: only for sufficiently informative queries
        if not filtered and docs and (len(norm) >= 12 or has_keywords):
            filtered = [docs[0]]
        return filtered[:1]
    except Exception:
        # Fallback: return empty to trigger graceful handling
        return []
