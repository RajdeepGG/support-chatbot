from sentence_transformers import SentenceTransformer
import chromadb

client = chromadb.Client()
collection = client.get_or_create_collection("support_docs")

model = SentenceTransformer("all-MiniLM-L6-v2")

def load_docs():
    with open("../data/faqs.txt") as f:
        text = f.read()

    chunks = text.split("\n\n")
    for i, chunk in enumerate(chunks):
        embedding = model.encode(chunk).tolist()
        collection.add(
            documents=[chunk],
            embeddings=[embedding],
            ids=[str(i)]
        )

# def search_docs(query):
#     embedding = model.encode(query).tolist()
#     results = collection.query(
#         query_embeddings=[embedding],
#         n_results=3
#     )
#     return results["documents"][0]

def search_docs(query, offer_name=None):
    search_text = query
    if offer_name:
        search_text = f"[OFFER: {offer_name}] {query}"

    embedding = model.encode(search_text).tolist()
    results = collection.query(
        query_embeddings=[embedding],
        n_results=3
    )
    return results["documents"][0]


