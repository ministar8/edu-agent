"""模型目录巡检脚本：逐一验证「已配 key 的网关」上的模型真的能调通。

为什么需要它
------------
``settings`` 里 ``GATEWAY_MODELS`` 挂了多网关多模型，「配了 key 但 model ID 写错 /
网关不通」这类错误**只在真实请求时才会炸**，平时静默潜伏。本脚本一次性把
``settings.AVAILABLE_MODELS``（已按配了 key 的网关过滤）里的模型逐个发一个最小
prompt，把配置漂移变成可一键发现的问题。

仿参考项目 agent-service-toolkit 的 ``check_live_models.py``，但复用本项目现成的
``settings.AVAILABLE_MODELS`` 与 ``get_model`` 工厂，不自己遍历 ``GATEWAY_MODELS``。

用法::

    uv run python scripts/check_live_models.py

退出码：0 = 全部通过，1 = 有模型 FAIL，2 = 未配置任何网关。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 允许以脚本方式直接运行（无需 `python -m`），把 src/ 加入导入路径
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _extract_content(raw: object) -> str:
    """把 ChatOpenAI 返回的 AIMessage content 规整成字符串（兼容 list / str 两种形态）。"""
    content = getattr(raw, "content", raw)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    return str(content or "").strip()


async def probe_model(model_ref: str) -> tuple[bool, str]:
    """给单个模型发最小 prompt，返回 ``(是否成功, 说明)``。"""
    from core.llm import get_model

    try:
        model = get_model(model_ref)
        raw = await asyncio.wait_for(model.ainvoke("Reply with exactly one word: OK"), timeout=60.0)
        text = _extract_content(raw)
        if not text:
            return False, "空回复"
        return True, text[:40]
    except TimeoutError:
        return False, "超时"
    except Exception as exc:  # noqa: BLE001 — 巡检要把任何失败都如实报出
        return False, f"{type(exc).__name__}: {exc}"[:80]


async def main() -> int:
    from core.settings import settings
    from schema.models import Gateway

    refs = sorted(settings.AVAILABLE_MODELS)
    rows: list[tuple[str, str, bool, str]] = []

    for ref in refs:
        if settings.gateway_for(ref) is Gateway.FAKE:
            rows.append((ref, "SKIP", False, "fake 网关，不发网络"))
            continue
        ok, note = await probe_model(ref)
        rows.append((ref, "PASS" if ok else "FAIL", not ok, note))

    print(f"{'模型标识':<36}{'状态':<8}说明")
    print("-" * 72)
    for ref, status, _failed, note in rows:
        print(f"{ref:<36}{status:<8}{note}")
    print("-" * 72)

    failed = sum(1 for r in rows if r[2])
    probed = sum(1 for r in rows if r[1] != "SKIP")
    passed = probed - failed
    print(f"结果：{passed}/{probed} 通过" + (f"，{failed} 失败" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        from core.settings import settings  # noqa: F401 — 提前触发单例构造以捕获无网关错误
    except ValueError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        print(
            "请先在 .env 配置至少一个网关的 API key（DASHSCOPE_API_KEY / DEEPSEEK_API_KEY），"
            "或设置 USE_FAKE_MODEL=true。",
            file=sys.stderr,
        )
        sys.exit(2)
    raise SystemExit(asyncio.run(main()))
