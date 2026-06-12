"""Check computer_network collection chunk quality"""
import chromadb
from collections import Counter

client = chromadb.PersistentClient(path="c:/Users/26452/Desktop/毕业设计/chroma_db")
col = client.get_collection("computer_network")
count = col.count()
print(f"=== computer_network: {count} chunks ===\n")

# Get all chunks (Chroma max 200 per call, paginate)
all_metas = []
all_docs = []
offset = 0
batch = 200
while offset < count:
    result = col.get(limit=batch, offset=offset, include=["metadatas", "documents"])
    all_metas.extend(result["metadatas"])
    all_docs.extend(result["documents"])
    offset += batch

print(f"Loaded {len(all_metas)} chunks\n")

# Stats
roles = Counter(m.get("section.chunk_role", "?") for m in all_metas)
types = Counter(m.get("section.content_type", "?") for m in all_metas)
sources = Counter(m.get("source_file", m.get("source", "?")) for m in all_metas)

print("## Chunk Roles")
for k, v in roles.most_common():
    print(f"  {k}: {v}")

print("\n## Content Types")
for k, v in types.most_common():
    print(f"  {k}: {v}")

print("\## Sources (file distribution)")
for k, v in sources.most_common():
    print(f"  {k}: {v}")

# merged_qa chunks detail
merged_qa = [(i, m, d) for i, (m, d) in enumerate(zip(all_metas, all_docs)) if m.get("section.chunk_role") == "merged_qa"]
print(f"\n## merged_qa chunks: {len(merged_qa)}")
for idx, m, d in merged_qa[:5]:
    heading = m.get("heading_title", "?")[:50]
    q = m.get("qa.question", "")[:60]
    a = m.get("qa.answer", "")[:60]
    ak = m.get("qa.answer_key", "")
    chars = m.get("char_count", len(d))
    print(f"  [{idx}] heading={heading} | chars={chars} | answer_key={ak}")
    if q:
        print(f"      Q: {q}")
    if a:
        print(f"      A: {a}")

# Chunk length distribution
lengths = [int(m.get("char_count", len(d))) for m, d in zip(all_metas, all_docs)]
lengths.sort()
p50 = lengths[len(lengths)//2] if lengths else 0
p90 = lengths[int(len(lengths)*0.9)] if lengths else 0
short = sum(1 for l in lengths if l < 80)
long_chunks = sum(1 for l in lengths if l > 1600)
print(f"\n## Chunk Length Distribution")
print(f"  min={lengths[0] if lengths else 0}, p50={p50}, p90={p90}, max={lengths[-1] if lengths else 0}")
print(f"  short (<80): {short}, long (>1600): {long_chunks}")

# Incomplete sentence check
incomplete = 0
for d in all_docs:
    s = d.rstrip()
    if s and not s.endswith(("。","！","？",".","!","?",":","：","；",";","…","”","'","\"","```","**",")","）","】","]","}","|",">")):
        incomplete += 1
print(f"  incomplete sentence end: {incomplete}/{len(all_docs)} ({incomplete/len(all_docs)*100:.1f}%)")
