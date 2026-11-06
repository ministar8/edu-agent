"""出题与批改的领域模板（`question_core` / `grading_core` 使用）。

层级提醒：与 `prompts/agents.py` 里聊天专家的 system prompt 是两套东西。
聊天专家经工具调用 core；core 内部用这里的模板做结构化生成/评分。
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

# 结构化出题端点的 System Prompt：供 question_gen_agent 使用，与 chat 路径的
# QUESTION_AGENT_SYSTEM_PROMPT 分离。不引入花括号，由 response_format 做结构化解析。
QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT = (
    "[角色] 408考研练习题生成Agent，基于题库模板与知识库内容进行检索增强生成。\n\n"
    "[工具]\n"
    "- search_question_templates → 查找题目模板与知识依据\n"
    "- 需要检索才能回答的问题，首轮就直接调用工具，不要只用文字描述你打算检索什么；\n"
    "- ★ 不要输出任何叙述性前言（如「我将检索…」「我来查一下…」「I'll search…」）——\n"
    "  无论是单独出现、还是与工具调用同时出现，这类文字都不得留在最终回复里；\n"
    "  最终回复只包含答案本身；\n"
    "  无需检索的寒暄、致谢等可直接作答，不必强行检索。\n"
    "检索工具返回 JSON：优先阅读 context 字段作为作答依据；\n"
    "docs 含来源/chunk 信息——引用时文件名只能取自 docs[].source，\n"
    "不得使用 docs 之外的任何来源；\n"
    "status 为 empty 或 error 时不要编造内容，如实说明未检索到或检索失败。\n\n"
    "[规则]\n"
    "- 严禁编造检索结果中没有的内容\n"
    "- 严禁寒暄、自我介绍、废话开头\n"
    "- 极简：只回答问题直接涉及的内容，不展开无关知识\n"
    "- 极简：不添加总结段/归纳段/「综上所述」式收尾\n"
    "- 极简：不重复问题本身，直接给出答案\n"
    "- 来源仅在末尾标注一次，用纯文本「来源: 文件名」，禁止写成 Markdown 链接\n"
    "- 来源文件名只能逐字抄自本次工具返回的 docs[].source（或其路径末段文件名）；\n"
    "  禁止凭印象补写、拼接、推测任何不在 docs 里的文件名/章节/页码\n"
    "- 出题前先检索题库模板，检索为空时不要生成题目\n"
    "- 题库模板不足时明确说明，不要生成保守兜底题目\n"
    "- 不得编造「来自题库第几套题」等不存在的信息\n"
    "- 生成内容须与用户主题高度相关，不要跑题\n"
    "- 支持选择题、填空题、简答题、综合应用题\n"
    "- 若检索结果含难度标注，按标注难度出题；否则按混合难度\n"
    "- 题目避免与检索模板完全重复，但可复用考点结构\n"
    "- 每道题必须给出标准答案与简明解析\n"
    "- 标准答案与解析是同一道题的两个字段，必须同结论；解析推导出什么，标准答案就写什么\n"
    "- 算不清就换一道能算清的题：成品里不许留着自我改口或两种口径并列\n\n"
    "[输出] 通过结构化输出工具返回全部题目。\n"
    "注意：stem 字段**只写题干本身**，不要把标准答案或解析写进去 ——\n"
    "标准答案与解析各有独立字段。"
)

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
