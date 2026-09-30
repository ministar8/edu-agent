"""区分 real/on 上的 cat 级代价：是 Step 3 遗留，还是 Step 4 新引入。"""

from __future__ import annotations

import json
import re

BASELINE = r"C:\Users\26452\Desktop\edu-agent\evals\retrieval_baseline_real_rerank.json"
S3 = r"C:\Users\26452\AppData\Local\Temp\edu_step3\gate\g5_real_on.log"
S4 = r"C:\Users\26452\AppData\Local\Temp\edu_step4\gate\s5_real_on.log"

KEYS = (
    "category_hit_at_1",
    "category_mrr",
    "category_precision",
    "kp_hit_at_k",
    "kp_mrr",
    "mean_evidence_count",
)


def from_log(path: str) -> dict[str, float]:
    text = open(path, encoding="utf-8", errors="replace").read()
    out: dict[str, float] = {}
    for k in KEYS:
        m = re.search(rf"^{k}\s+([\d.]+)", text, re.M)
        if m:
            out[k] = float(m.group(1))
    return out


base = json.load(open(BASELINE, encoding="utf-8"))["metrics"]
s3 = from_log(S3)
s4 = from_log(S4)

print(f"{'指标':24s} {'基线(S2后)':>11s} {'S3后':>9s} {'S4后':>9s} {'S3→S4':>9s} {'基线→S4':>9s}")
for k in KEYS:
    b, a, c = base.get(k), s3.get(k), s4.get(k)
    print(f"{k:24s} {b:>11.4f} {a:>9.4f} {c:>9.4f} {c - a:>+9.4f} {c - b:>+9.4f}")
