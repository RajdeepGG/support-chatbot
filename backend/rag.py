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
    results = collection.query(
        query_embeddings=[embedding],
        n_results=3
    )
    return results["documents"][0]
