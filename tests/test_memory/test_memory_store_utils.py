"""memory 薄件纯函数单测：计量 / 命名空间 / episode 校验与检索兜底排序。

invariants：
- 命名空间是用户隔离的**唯一边界**：int 5 与 str "5" 必须生成同一命名空间；
- store 里**无法解析**的坏文档必须被跳过，不得炸掉整条读取；
- 无向量索引时（pytest-env 环境默认 false）`arecent_episodes` 按 at 兜底降序。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from memory.episodes import arecent_episodes, coerce_episode, episode_search_text
from memory.metering import approx_tokens, meter_text
from memory.namespaces import (
    PROFILE_DOC_KEY,
    episode_key,
    student_episodes_ns,
    student_profile_ns,
)
from memory.schemas import Episode

# ── metering ───────────────────────────────────────────────────────────


def test_approx_tokens_empty_is_zero() -> None:
    assert approx_tokens("") == 0


def test_approx_tokens_cjk_one_char_one_token() -> None:
    assert approx_tokens("你好世界avl") == 4 + max(3 // 4, 1)  # 3 个 ASCII 字符 → 至少 1


def test_approx_tokens_ascii_four_chars_per_token() -> None:
    assert approx_tokens("abcdefgh") == 2
    assert approx_tokens("abc") == 1  # 不足 4 字符也按 1 起算


def test_meter_text_joins_parts_and_labels() -> None:
    m = meter_text("grade", "你好", "", "abc")
    assert m.label == "grade"
    assert m.chars == 5
    assert m.approx_tokens == approx_tokens("你好abc")


def test_meter_text_all_empty() -> None:
    m = meter_text("question", "", "")
    assert (m.label, m.chars, m.approx_tokens) == ("question", 0, 0)


# ── namespaces（用户隔离边界）──────────────────────────────────────────


def test_namespaces_shape() -> None:
    assert student_profile_ns(5) == ("student", "5", "profile")
    assert student_episodes_ns("5") == ("student", "5", "episodes")
    assert PROFILE_DOC_KEY == "profile"


def test_int_and_str_user_ids_share_one_namespace() -> None:
    # 用户隔离关键：pid 侧 int、JWT 侧 str，必须落到同一命名空间
    assert student_episodes_ns(7) == student_episodes_ns("7")
    assert student_profile_ns(7) == student_profile_ns("7")


def test_episode_key_prefix() -> None:
    assert episode_key("abc123") == "ep-abc123"


# ── coerce / search_text ───────────────────────────────────────────────


def test_coerce_episode_passes_through_instances() -> None:
    e = Episode(type="grade", score=1.0)
    assert coerce_episode(e) is e


def test_coerce_episode_validates_dicts() -> None:
    e = coerce_episode({"type": "grade", "score": 99.0, "topic": "图"})
    assert e is not None and e.score == 99.0


def test_coerce_episode_returns_none_on_garbage() -> None:
    assert coerce_episode({"type": "不是合法枚举"}) is None
    assert coerce_episode("string") is None


def test_episode_search_text_joins_nonempty_fields() -> None:
    e = Episode(type="grade", topic="图", stem_excerpt="题", error_analysis="")
    assert episode_search_text(e) == "图 题"


def test_episode_search_text_capped_at_500() -> None:
    # Episode 模型字段有 max_length=200 校验；这里用 model_construct 构造
    # 超长文档测的是函数自身的 500 防御上限（Store 内坏文档场景）
    e = Episode.model_construct(type="grade", topic="图", stem_excerpt="字" * 600)
    out = episode_search_text(e)
    assert len(out) == 500
    assert out.startswith("图 ")


# ── arecent_episodes（Fake store，不碰真库）───────────────────────────


class _FakeStore:
    def __init__(self, values: list[object]) -> None:
        self.values = values
        self.calls: list[tuple[tuple, int]] = []

    async def asearch(self, namespace, limit: int = 10):  # noqa: ANN001 — 形状模拟
        self.calls.append((tuple(namespace), limit))
        return [SimpleNamespace(value=v) for v in self.values]


def _d(at: str, score: float | None = None, *, type_: str = "grade") -> dict:
    d: dict = {"type": type_, "at": at, "topic": "", "score": score}
    return d


@pytest.mark.asyncio
async def test_arecent_episodes_sorts_by_at_desc_and_applies_limit() -> None:
    store = _FakeStore(
        [
            _d("2026-01-01T00:00:00+00:00"),
            _d("2026-03-01T00:00:00+00:00"),
            _d("2026-02-01T00:00:00+00:00"),
            _d("坏的at", "not-a-date"),
        ]
    )
    out = await arecent_episodes(store, 9, limit=2)
    # 检索上限是「每用户 episodes 上限」，排序在内存做：拿全局最新 2 条
    assert [e.at for e in out] == ["2026-03-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"]
    assert store.calls[0][1] == 200  # MEMORY_EPISODE_MAX_PER_USER，而不是 limit


@pytest.mark.asyncio
async def test_arecent_episodes_skips_unparseable_documents() -> None:
    store = _FakeStore([{"type": "非法"}, "纯文本垃圾", _d("2026-01-01T00:00:00+00:00", 60.0)])
    out = await arecent_episodes(store, 9, limit=10)
    assert len(out) == 1
    assert out[0].score == 60.0


@pytest.mark.asyncio
async def test_arecent_episodes_limit_disables_scan() -> None:
    store = _FakeStore([_d("2026-01-01T00:00:00+00:00")])
    out = await arecent_episodes(store, 9, limit=0)
    assert out == []
    assert store.calls == []  # limit<=0 不应发起检索
