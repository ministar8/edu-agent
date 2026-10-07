"""service 层（HTTP 端点）的出题与批改模板。

层级提醒：这两个模板属于**端点直调**，经 `agents.question_core` / `agents.grading_core`
使用，与 `prompts/agents.py` 里聊天专家的 system prompt 是两套东西。
`/api/questions/grade` 走 `GRADE_PROMPT` + `grading_core`，**不经过 grading_agent**，
因此 `GRADING_AGENT_SYSTEM_PROMPT` 在该路径上不生效。
"""

from langchain_core.prompts import ChatPromptTemplate

from core.kp_vocab import SUBJECT_LABELS, prompt_names_by_subject

_KP_RULE_TAIL = (
    "- **不是**题干摘要、**不是**题目内容、**不是**学科名（如「数据结构」太粗，"
    "「已知一棵二叉排序树……」是题干摘要，都不合格）。\n"
    "- 同一考点的不同题应给出**同一个**考点名（便于聚合）；不确定时给最贴切的一个。"
)


def _knowledge_points_block(by_subject: dict[str, list[str]]) -> str:
    """knowledge_points 约束块（2026-10-07 缺陷 E · 方案 A）。

    ★ 为什么从 kp_index 动态读、而不是再写一份示例名：
    缺陷 E 的成因正是「prompt 认的词表」与 `kp_index` **不同源** —— 模型被自由示例
    诱导产出 `图的基本性质` / `堆的定义`，而 canonical 里只有 `图` / `堆`，于是每个
    自造词各成一个 1-hit 桶、`MEMORY_WEAK_MIN_HITS` 永不满足 ⇒ `weak_topics` 恒空
    ⇒ 跨会话召回被系统性抑制。硬编码第二份词表会**重新制造**不同源，故这里只能
    经 `core.kp_vocab` 取（唯一事实源，与 `memory.topics.normalize_topic` 同源）。

    ★ 为什么不注入别名（如 `AVL`）：注入别名会诱导模型输出别名而非规范名，
    归一化仍要依赖别名表兜底，聚合桶照样可能分裂。只给 canonical。

    ★ 降级：kp_index 读不到（容器外无仓库 / 文件缺失）⇒ 词表为空 ⇒ 退回 8 个示例，
    服务不得因此起不来。
    """
    groups = [(SUBJECT_LABELS[s], names) for s, names in by_subject.items() if names]
    if not groups:
        # 退化为缺陷 B 修好的 8 个已核验规范名（不写自由描述，避免再次诱导漂移）。
        return (
            "knowledge_points 字段填写**本题考查的标准知识点名称**（1–3 个）：\n"
            "- 用教材/考纲的**规范考点名**，例如：平衡二叉树、二叉排序树、图、拓扑排序、"
            "TCP 流量控制、进程同步、页面置换算法、Cache 映射方式。\n" + _KP_RULE_TAIL
        )
    # 组内排序：kp_index 的行序变动不该改变 prompt 内容（否则 PROMPT_SET_VERSION
    # 会把「数据文件重排」误报成「提示词变更」，污染归因）。
    listing = "\n".join(f"【{label}】{'、'.join(sorted(names))}" for label, names in groups)
    return (
        "knowledge_points 字段填写**本题考查的标准知识点名称**（1–3 个），"
        "**只能从下列规范考点名中逐字选取**——不得自造、不得扩写、不得加「的定义/的性质」这类后缀：\n"
        + listing
        + "\n"
        + _KP_RULE_TAIL
    )


# 出题：human 一条即可；结构化 system 在 question_gen_agent
# （QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT），此处不重复。
QUESTION_GEN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "human",
            "请生成 {count} 道关于「{topic}」的练习题，难度：{difficulty}。"
            "每题给出题干、标准答案与简明解析。",
        )
    ]
)

# 批改：评分规则进 system；学生答案是**不可信输入**，必须留在 human ——
# 结构上把「指令」与「数据」分开，避免答案内容被当成指令执行。
GRADE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "批改 408 考研题目作答并输出结构化结果。\n"
            "评分 0-100；若学生答错（score<60）需填写 error_analysis 分析错因与改进建议。\n"
            # ★ 2026-10-06（Step 5 实测）：feedback 超长会让整个批改**硬失败**。
            #   `GradingResult.feedback` 此前是 `max_length=800`（Pydantic 强校验），
            #   实测模型输出 >800 字符 ⇒ `ValidationError` ⇒ `call_structured` 返回 None
            #   ⇒ 批改工具回「批改失败」⇒ 既不写 episode 也无分数。
            #   ★ 失败率：Step 5 修复前 ON 组 **5/9 = 55.6%**（分母 = A 段**预期**批改次数；
            #     失败含「分数不可解析」与「完全无落分记录」两种形态。旧记「62.5%=5/8」的
            #     分母 8 无法从归档构造，见 `docs/EXPERIMENTS.md` §20.3）。
            #   已在两处收口：① schema 改为**截断**而非拒绝（见 schema/grading.py）；
            #   ② 此处仍**显式约束长度**，从源头减少超长（200 字 ≪ 800 字符，留足余量）。
            "feedback 与 error_analysis 务必**简明**：feedback 不超过 200 字、"
            "error_analysis 不超过 150 字。\n" + _knowledge_points_block(prompt_names_by_subject()),
            # ★ 2026-10-06 Phase 1.5：knowledge_points 是 Memory 聚合的唯一事实源，
            #   必须输出**标准考点名**而非题干摘要。词表在 import 期从 `core.kp_vocab`
            #   动态取（与 `normalize_topic` 同源）—— 见 `_knowledge_points_block`。
            #   ★ 2026-10-07 缺陷 #8：改用 `prompt_names_by_subject()` —— 按数据字段
            #     `node_kind` 剔掉 4 个课程根节点（本 prompt 的规则尾自己写着「不是学科名」）。
            #     过滤只发生在「提供给模型」这一侧，词表来源仍是同一个 `kp_vocab`。
        ),
        ("human", "题干：{stem}\n标准答案：{standard_answer}\n学生答案：{user_answer}"),
    ]
)
