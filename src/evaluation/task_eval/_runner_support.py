"""runner 的机械判据 / 环境预检 / 归档 IO（从 runner.py 拆出，行为等价）。"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from core.settings import settings
from evaluation.task_eval._runner_record import CaseRecord
from evaluation.task_eval.retrieval_probe import RetrievalProbe

logger = logging.getLogger(__name__)

_GEN_REQUIRED_MARKERS = re.compile(r"题干|题目|标准答案|解析|答案[:：]|选项")
_GRADE_FIELD_RE = re.compile(r"得分|评分|分数|反馈|评语|扣分")

# 环境类错误（额度耗尽 / 鉴权失败 / 依赖不可用）——**不是 case 失败**。
# ★ 必须与 tool_error 区分：把「账号没额度」记成「工具报错」会污染 failure_reason 归因，
#   使 Phase 0 的「主要失败原因」失真（EFFECT_PLAN §2.B.5 只允许修环境/runner bug）。
_ENV_ERROR_MARKERS = (
    "Free quota exhausted",
    "AllocationQuota",
    "PermissionDeniedError",
    "AuthenticationError",
    "insufficient_quota",
    "invalid_api_key",
    # ★ 2026-10-05 实测补充：账号**欠费**（DashScope `code: Arrearage`，
    #   文案 "Access denied... overdue-payment"）。与「免费额度耗尽」是**两回事**：
    #   前者充钱即恢复，后者要改计费模式。但两者都属环境，都不该计入 case 失败。
    "Arrearage",
    "overdue-payment",
    "account is in good standing",
    # ★ 2026-10-06 实测补充：**检索/embedding 服务不可用**（TEI 容器停了）。
    #   缺这一条时，探针 run 会带着「检索全空」继续跑完 —— 实测跑了 12 分钟、
    #   全部 case 被记成 retrieval_miss，把「服务挂了」伪装成「能力不行」。
    #   ⇒ 必须与额度错误同级：**立即中止、不计失败**。
    "502 Bad Gateway",
    "Chroma query failed",
    "embedding failed",
    "embedding 失败",
    "Connection refused",
    "积极拒绝",
    "upstream connect failed",
    "Max retries exceeded",
)


def is_env_error(text: str) -> bool:
    """判断错误文本是否属**环境类**（额度/鉴权），而非 case 级失败。"""
    return any(marker.lower() in (text or "").lower() for marker in _ENV_ERROR_MARKERS)


def ensure_localhost_no_proxy() -> None:
    """把 localhost/127.0.0.1 加入 ``NO_PROXY``，让本机服务（TEI 等）**绕过代理**。

    ★ 为什么必须有（2026-10-06 实测教训）：本机环境设了
      ``HTTP_PROXY=http://127.0.0.1:55466``，于是**连 localhost 也走代理** ——
      代理处理不了 TEI，表现为 `502 Bad Gateway` / `RemoteProtocolError` / `Empty reply`，
      极易误判成「TEI 挂了」。
      ⇒ 只把**本机地址**排除在外；外部 API（DashScope 等）**仍走代理**，不受影响。
    """
    import os

    needed = ("localhost", "127.0.0.1", "::1")
    for key in ("NO_PROXY", "no_proxy"):
        current = os.environ.get(key, "")
        items = [x.strip() for x in current.split(",") if x.strip()]
        for host in needed:
            if host not in items:
                items.append(host)
        os.environ[key] = ",".join(items)


def memory_write_missing(
    *,
    store_enabled: bool,
    grade_calls: int,
    episodes: list[dict[str, Any]],
    read_failed: bool = False,
) -> bool:
    """A 段有批改、Store 开着，却**一条 episode 都没读到** ⇒ 记忆写入证据缺失。

    ★ 为什么必须单独判（2026-10-07 实测）：TEI 的 `/embeddings` 返回 502 而 `/health` 仍 200 时，
      `memory.safe` 只打一行 WARNING「长期记忆写入超时（grade，>1.5s），已忽略」就丢弃写入。
      后果不是「跑失败」而是**跑出错的东西**：画像为空 ⇒ B 段召不回 ⇒ 被记成 Memory 产品失败
      （我们当天刚把这类现象归因给 #22 的 KP 阈值）。⇒ 这种样本不进 Memory 分母。
      ★ 与 `MIN_HITS` 无关：这里看的是**原始 episode 是否落库**，不是画像有没有值。

    ★★ 两条边界（2026-10-08 review C1/I2/I3，都是当初真踩的）：
      ① **本函数不指认原因。** 「没落库」既可能是环境（TEI 挂），也可能是产品
         （缺陷 C：工具拿不到 config ⇒ `record_grade` 被静默跳过 —— 本仓真实发生过）。
         `memory/safe.py` 把写失败压成一行 WARNING、既不计数也不落到 record ⇒ 单凭
         「episode 为空」**无法区分**。环境类判定另有两道：`preflight_check()` 真发一次
         向量请求（㉑a），以及 `is_env_error()` 看真实报错文本。
      ② **只对 memory 任务有意义**，调用点必须在 `case.task == "memory"` 之内 ——
         非 memory 任务走 `run_turns`，它照抓 `grade_scores` 但从不读 Store，
         `episodes` 恒空 ⇒ 放外面等于宣布「所有批改类 case 天生写链断裂」，
         会让 grade/verify/qa 的实跑在第一条就被中止（C1）。
      ③ `read_failed` —— 清理前那次读取自己抛过错 ⇒ 「没读到」是取证通道的故障，
         不能推断写入（I3）。此时返回 False，交给 `episodes_read_failed` 单独披露。
    """
    if read_failed or not store_enabled or grade_calls <= 0:
        return False
    return not episodes


def preflight_check() -> list[str]:
    """运行前预检外部依赖，返回问题列表（空 = 全部就绪）。

    ★ 为什么必须有（2026-10-06 实测教训）：TEI embedding 容器停掉后，
      检索链**不抛异常**，只返回空结果 ⇒ 探针 run 带着「检索全空」跑满 12 分钟，
      把「服务挂了」记成 `retrieval_miss`，伪装成「能力不行」。
      而 `retrieval_error` 是**空的**，事后的文本标记也检测不到。
    ★ 2026-10-07 补：**只探 `/health` 不够** —— 实测 TEI 半死时 `/health` 返 200、
      `/embeddings` 返 502 ⇒ 检索与 Memory 写链都会静默退化。必须真发一次向量请求。
    """
    import httpx

    ensure_localhost_no_proxy()
    problems: list[str] = []
    if not getattr(settings, "USE_FAKE_EMBEDDING", False):
        base = str(getattr(settings, "EMBEDDING_API_BASE", "") or "").rstrip("/")
        if base:
            # ★ `/health` 的抱怨先**攒着**：有些 OpenAI 兼容服务根本没有 `/health` 路由
            #   （实测 404），但 `/embeddings` 完全正常 —— 那种情况下报健康检查失败是**假红**，
            #   会把一个能跑的 TEI 拦在门外（review M7）。判据：只有推理也失败时，
            #   健康检查的抱怨才有资格一起进 `problems`（两条一起指认「服务不可用」）。
            health_problem: str | None = None
            try:
                resp = httpx.get(f"{base}/health", timeout=5.0)
                if resp.status_code >= 400:
                    health_problem = f"embedding 服务异常 HTTP {resp.status_code}：{base}"
            except Exception as exc:  # noqa: BLE001
                hint = ""
                if any(
                    os.environ.get(k)
                    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
                ):
                    hint = "（检测到本机设了 HTTP(S)_PROXY；已自动排除 localhost，若仍失败请检查代理配置）"
                health_problem = f"embedding 服务不可达：{base}（{type(exc).__name__}）{hint}"
            # ★ 关键的一步：health 通过 ≠ 能推理。真发一次 embedding 请求。
            infer_problem: str | None = None
            try:
                from rag.common.embeddings import get_embeddings

                vec = get_embeddings().embed_query("预检")
                if not vec or len(vec) < 8:
                    infer_problem = (
                        f"embedding 返回异常向量（维度={len(vec) if vec else 0}）：{base}"
                    )
            except Exception as exc:  # noqa: BLE001
                infer_problem = (
                    f"embedding **推理**失败（`/health` 可能仍是 200，别只看健康检查）：{base}"
                    f"（{type(exc).__name__}: {str(exc)[:120]}）"
                )
            if infer_problem is not None:
                if health_problem is not None:
                    problems.append(health_problem)
                problems.append(infer_problem)
            elif health_problem is not None:
                logger.info(
                    "预检：%s —— 但推理探针成功，判为无 `/health` 路由的兼容服务，不计为问题",
                    health_problem,
                )
    return problems


def generation_ok(task: str, reply: str, hard_fails: list[str]) -> bool:
    """「有没有产出**合法结果**」—— 与质量无关（§2.B.3 ②）。"""
    if hard_fails or not reply.strip():
        return False
    if task in ("qa", "verify"):
        return True
    if task == "generate":
        return bool(_GEN_REQUIRED_MARKERS.search(reply))
    if task == "grade":
        return bool(_GRADE_FIELD_RE.search(reply))
    if task == "memory":
        return True
    return False


def map_route_failures(failures: list[str], probe_status: str) -> tuple[str, list[str]]:
    """路由侧记下了失败 ⇒ 该 case 的检索层证据等级就是 `error`（B7 消费侧，v1.3）。

    ★ 为什么必须有这一层（实测，非措辞）：异常收敛发生在 `rag.retrieval.routes._safe_to_thread`
      （**按路由逐个**收敛成空结果），**不在探针层** ⇒ 探针永远收不到 exception，
      于是 `probe_retrieval` 把「路由全线故障」写成 `status="ok"`（实测注入 BM25 抛错：
      `status='ok' pack_len=755 evidence=3`）。光让错误**被记录**不足以让 `error` 可达，
      必须有**消费者**把记录读回状态里 —— 规格 v1.3 的 B7-② 两侧缺一不可。

    规则（只升级、不降级）：
    - 空清单 ⇒ 状态**原样**返回（不许把 `ok` 折成 `empty`，也不许凭空造 `error`）；
    - 非空 ∧ `probe_status ∈ {ok, empty}` ⇒ 升为 `error`（「坏了」不是「没查到」）；
    - 非空 ∧ 已是 `error`（或 `""`）⇒ **不降级**、原样返回，清单照样落盘。

    返回 `(状态, 清单副本)`。本函数**纯**（无 IO、无全局读）⇒ 判据 `8j` 直接打它，
    不许在判据里读 manager。清单由调用方落进诊断字段 `route_failure_notes`。
    """
    if not failures:
        return probe_status, []
    if probe_status in ("ok", "empty"):
        return "error", list(failures)
    return probe_status, list(failures)


def mechanical_failures(
    task: str,
    probe: RetrievalProbe,
    reply: str,
    hard_fails: list[str],
    *,
    retrieval_status: str | None = None,
) -> list[str]:
    """只在**机械可判**的范围内收集 failure_reason；生成质量类留给 judge。

    ★ `memory` 豁免检索判据（2026-10-05 修）：Memory 的 query（「我是 2027 考研…」）
      本就不是知识查询，检索返空属**预期**。若照记 `retrieval_miss`，
      Phase 1 会误判「记忆差是因为检索差」—— 归因方向直接错。
      Memory 的判据是三维 `retrieved ∧ used ∧ correct`。

    ★ tier-0 门（Task 8 Step 5）：`retrieval_miss` 只在**探针真的报告 `empty`** 时才记。
      旧实现看 `not probe.ok`，而 `status == "error"` 时 `ok` **同样是 False** ⇒
      一次 BM25 崩溃会同时产出 `tool_error` 与 `retrieval_miss`，后者再被
      `metrics._PRIMARY_PRIORITY` 顶成 `primary_failure` ⇒ 「路由坏了」被写成
      「产品没查到」。判据与重判路径共用 `judge.retrieval_layer_gate_open`（一份规则）。

    ★ `retrieval_status`（B7 v1.3）：调用方传入 `map_route_failures` **升级后**的状态，
      于是「路由记了失败但探针写成 ok」这一类 case 在**新跑**里与**重判路径**
      （`judge.mechanical_reasons_from_record` 读归档的 `retrieval_status`）同口径。
      缺省（None）时退回探针自报状态，语义与旧实现一致。
    """
    from evaluation.task_eval.judge import retrieval_layer_gate_open

    status = probe.status if retrieval_status is None else retrieval_status
    reasons: list[str] = []
    if any("invoke 抛错" in h or "工具" in h for h in hard_fails):
        reasons.append("tool_error")
    if status == "error":
        reasons.append("tool_error")
    if retrieval_layer_gate_open(status, probe.ok, task):
        reasons.append("retrieval_miss")
    if not reply.strip():
        reasons.append("generation_incomplete")
    return reasons


def _all_kp(items) -> list[str]:
    out: list[str] = []
    for it in items:
        out.extend(it.knowledge_points)
    return out


def write_jsonl(path: str | Path, rows: list[dict]) -> Path:
    """整体重写 jsonl（dict 行）。**每行都以 `\\n` 结尾，包括最后一行。**

    ★ 为什么收成一处（2026-10-07）：`cli.py` 的三处写出原先各自用
      `write_text("\\n".join(...))` —— 该写法**不留尾换行**，而 `append_record`
      是 `"a"` 模式追加 `json + "\\n"`。两者相遇时新记录会**粘在末行尾部**，
      拼成一条解析失败的坏行 ⇒ **上一条与这一条同时丢失**（实测：3 条只剩 1 条可读）。
      后果不只丢数据：`load_done_ids` 读不到被粘住的 case_id ⇒ 续跑会**重做**它，
      而那条已经烧过的 token 无从追溯。
      行格式现在只有一份实现，新调用方不可能再漏掉尾换行。
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out


def _needs_newline_pad(path: Path) -> bool:
    """文件存在、非空、且末字节不是 `\\n` ⇒ True（需要补分隔符才能安全追加）。"""
    try:
        size = path.stat().st_size
        if not size:
            return False
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            return f.read(1) != b"\n"
    except OSError:
        return False


def dump_records(records: list[CaseRecord], path: str | Path) -> Path:
    """把 record 列表落盘为 jsonl（供报告与论文复算）。"""
    out = write_jsonl(path, [r.to_dict() for r in records])
    logger.info("写入 %d 条 record → %s", len(records), out)
    return out


def append_record(record: CaseRecord, path: str | Path) -> None:
    """**逐条追加**一条 record 并立即 flush。

    ★ 为什么必须有（2026-10-05 实测教训）：原实现只在整轮结束时 `dump_records`，
      于是一次跑满 15 分钟、发出 **165 次 LLM 调用**的 run 被中止后，
      **一条记录都没落盘** —— 配额全白烧。逐条追加让「跑一半被中止」不再丢数据，
      配合 `load_done_ids` 可**续跑**。
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if _needs_newline_pad(out):
        # 见 `write_jsonl` 的说明：末行缺尾换行时直接 append 会把两条粘成一条坏行。
        logger.warning("目标 jsonl 末行无换行，追加前先补一个 —— %s", out)
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n")
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        f.flush()


def load_done_ids(path: str | Path) -> set[str]:
    """读出**真正完成**的 case_id（用于续跑时跳过）。

    ★ 环境错误的记录**不算完成**（2026-10-05 修）：欠费/额度耗尽时写下的 record
      是「没跑成」，若也计入 done，续跑会把它**永久跳过** —— 实测 mem-006
      因欠费失败后被误判「已完成」，补跑时被跳过。
      故这里只认「非环境错误」的记录，让环境恢复后能自动补跑。
    """
    out = Path(path)
    if not out.exists():
        return set()
    done: set[str] = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # 被中断写坏的最后一行：忽略即可，续跑会重做该 case
        text = " ".join(obj.get("hard_fails") or []) + " " + str(obj.get("retrieval_error") or "")
        if is_env_error(text):
            continue  # 环境错误 → 视为未完成，允许重试
        case_id = str(obj.get("case_id") or "")
        if case_id:
            done.add(case_id)
    return done
