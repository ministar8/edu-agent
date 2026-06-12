"""Re-index computer_network collection: delete old, re-ingest all CN markdown files."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))

from pathlib import Path
from app.rag.cleaner import clean_documents
from app.rag.enhancer import enhance_documents
from app.rag.knowledge_tagger import tag_chunks_with_knowledge_points
from app.rag.loader import load_single_file
from app.rag.splitter import split_documents
from app.rag.vectorstore import get_vector_store_manager

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "computer_network"
CATEGORY = "computer_network"

# 1. Delete existing collection
vsm = get_vector_store_manager()
print(f"Deleting old collection '{CATEGORY}'...")
vsm.delete_collection(CATEGORY)
print("Deleted.")

# 2. Find all .md files
md_files = sorted(KNOWLEDGE_DIR.glob("*.md"))
print(f"Found {len(md_files)} markdown files:")
for f in md_files:
    print(f"  {f.name}")

# 3. Ingest each file
total_chunks = 0
for f in md_files:
    print(f"\n--- Processing {f.name} ---")
    documents = load_single_file(str(f))
    documents = clean_documents(documents)
    chunks = split_documents(documents)
    chunks = enhance_documents(chunks)

    for chunk in chunks:
        chunk.metadata["category"] = CATEGORY

    chunks = tag_chunks_with_knowledge_points(chunks, fallback_category=CATEGORY)

    # Count merged_qa
    merged_qa = sum(1 for c in chunks if c.metadata.get("section.chunk_role") == "merged_qa")
    detail = len(chunks) - merged_qa

    vsm.add_documents(chunks, collection_name=CATEGORY)
    total_chunks += len(chunks)
    print(f"  {len(chunks)} chunks (detail={detail}, merged_qa={merged_qa})")

print(f"\n=== Done: {total_chunks} total chunks in '{CATEGORY}' ===")

# 4. Verify
col = vsm.client.get_collection(CATEGORY)
print(f"Verified: {col.count()} chunks in ChromaDB")

# 5. Quick quality check
result = col.get(limit=col.count(), include=["metadatas"])
from collections import Counter
roles = Counter(m.get("section.chunk_role", "?") for m in result["metadatas"])
types = Counter(m.get("section.content_type", "?") for m in result["metadatas"])
sources = Counter(m.get("source_file", m.get("source", "?")) for m in result["metadatas"])
print(f"\nRoles: {dict(roles)}")
print(f"Types: {dict(types)}")
print(f"Sources:")
for k, v in sources.most_common():
    print(f"  {k}: {v}")
