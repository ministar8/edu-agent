"""RAGAS judge 模型选型探针：只测「能否 n>1」（answer_relevancy 的硬约束）。

每个候选 model_ref 调 1 次，带超时；不做生成、不跑 RAGAS。
"""

from __future__ import annotations

import concurrent.futures as cf
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langchain_openai import ChatOpenAI  # noqa: E402

from core.settings import settings  # noqa: E402
from schema.models import parse_model_ref  # noqa: E402

CANDIDATES = [
    "dashscope:qwen3.7-flash",
    "dashscope:qwen3.8-27b",
    "deepseek:deepseek-v4-flash",
    "dashscope:deepseek-v4-flash",
    "dashscope:qwen3.8-max-0902",
    "dashscope:qwen3.8-max",
]


def _call(ref: str, n: int, extra_body: dict | None):
    _, model_id = parse_model_ref(ref)
    kwargs: dict = dict(
        api_key=settings.api_key_for_model(ref),
        base_url=settings.api_base_for_model(ref),
        model=model_id,
        temperature=0.0,
        model_kwargs={"n": n},
        request_timeout=45,
        max_retries=0,
    )
    if extra_body:
        kwargs["extra_body"] = extra_body
    llm = ChatOpenAI(**kwargs)
    return llm.invoke("Reply with one short sentence.")


def probe(ref: str, n: int, extra_body: dict | None) -> str:
    try:
        with cf.ThreadPoolExecutor(max_workers=1) as ex:
            r = ex.submit(_call, ref, n, extra_body).result(timeout=60)
        return f"OK   ({len(r.content or '')} chars)"
    except Exception as e:
        msg = str(e).replace("\n", " ")
        tag = "n>1 被拒" if "n parameter" in msg else type(e).__name__
        return f"FAIL [{tag}] {msg[:90]}"


def main() -> int:
    print(f"{'model_ref':<32}{'n=1':<26}{'n=2(默认配置)':<34}{'n=2(thinking=False)'}")
    print("-" * 118)
    for ref in CANDIDATES:
        a = probe(ref, 1, None)
        b = probe(ref, 2, None)
        c = probe(ref, 2, {"enable_thinking": False})
        print(f"{ref:<32}{a:<26}{b:<34}{c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
