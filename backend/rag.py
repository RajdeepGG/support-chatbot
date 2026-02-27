from sentence_transformers import SentenceTransformer
import chromadb
import os

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
    search_text = query
    embedding = model.encode(search_text).tolist()
    try:
        results = collection.query(
            query_embeddings=[embedding],
            n_results=5,
            include=["documents", "distances"]
        )
        docs = results.get("documents", [[]])[0] or []
        dists = results.get("distances", [[]])[0] or [None] * len(docs)
        # Keep only close matches; fall back to top-1 if none pass threshold
        threshold = 0.35
        filtered = [doc for doc, dist in zip(docs, dists) if dist is None or dist <= threshold]
        if not filtered and docs:
            filtered = [docs[0]]
        # Return top 2 for concise prompting
        return filtered[:2]
    except Exception:
        # Fallback: return empty to trigger graceful handling
        return []
