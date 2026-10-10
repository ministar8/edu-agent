"""门禁共享常量：路径 / 学科类目映射 / GATE_K / env 开关。"""

from __future__ import annotations

import os

SUBJECT_TO_CATEGORY: dict[str, str] = {
    "ds": "data_structure",
    "co": "computer_organization",
    "os": "operating_system",
    "network": "computer_network",
}


_CODE_CATEGORY_TO_SUBJECT = {
    "code_ds": "data_structure",
    "code_co": "computer_organization",
    "code_os": "operating_system",
    "code_cn": "computer_network",
}


def _effective_category(meta: dict) -> str:
    """把 `code_<科>` / `exams/<科>.md` 的 chunk 归入对应学科类目。

    新语料含非四科类目（`exams` / `code_*`），但它们是**相关证据**（该科的真题/代码）；
    原样当 category 会让 `category_hit` 把「相关命中」判成「非学科」。能从类目或 source
    路径推出学科的即映射；推不出的（如按年整卷 `exams/YYYY/`）保持原样、如实计入。
    """
    cat = str(meta.get("category", ""))
    if cat in _CODE_CATEGORY_TO_SUBJECT:
        return _CODE_CATEGORY_TO_SUBJECT[cat]
    if cat == "exams":
        src = str(meta.get("source", "")).replace("\\", "/").lower()
        for subj_cat in _CODE_CATEGORY_TO_SUBJECT.values():
            if src.endswith(f"/{subj_cat}.md"):
                return subj_cat
    return cat


QUESTIONS_CATEGORY = "exams"


DEFAULT_GOLDEN_PATH = "evals/datasets/golden/sample_408.jsonl"


DEFAULT_BASELINE_PATH = "evals/baselines/retrieval_baseline.json"


RERANK_BASELINE_PATH = "evals/baselines/retrieval_baseline_rerank.json"


REAL_EMBED_BASELINE_PATH = "evals/baselines/retrieval_baseline_real_embed.json"


RERANK_DISABLED_BASELINE_PATH = "evals/baselines/retrieval_baseline_fake_disabled.json"


REAL_EMBED_RERANK_DISABLED_BASELINE_PATH = "evals/baselines/retrieval_baseline_real_disabled.json"


REAL_EMBED_RERANK_BASELINE_PATH = "evals/baselines/retrieval_baseline_real_rerank.json"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


GATE_K = 5
