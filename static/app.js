// 凭证存放在 httpOnly cookie 中（JS 读不到，也不该读），改为向服务端确认会话。
// 同源 fetch 默认携带 cookie，因此后续请求无需再手动附带 Authorization 头。

const messagesEl = document.getElementById("messages");
// 空态 HTML 快照：切换会话 / 新建会话时用它恢复
const EMPTY_HINT_HTML = messagesEl.innerHTML;

let USER_INITIAL = "我";
let sending = false;

/** 生成会话 ID。非安全上下文（如内网 http）没有 crypto.randomUUID，需兜底。 */
function newId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID();
  }
  return "t-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

async function loadUser() {
  const res = await apiGet(API.me);
  if (!res.ok) {
    localStorage.removeItem("user");
    location.href = "/login.html";
    return;
  }
  const u = await res.json();
  localStorage.setItem("user", JSON.stringify(u)); // 仅用于首屏展示，不含凭证
  const name = u.display_name || u.username || "";
  document.getElementById("user-name").textContent = name;
  document.getElementById("user-role").textContent = u.role || "";
  document.getElementById("user-avatar").textContent = name ? name.trim().charAt(0) : "·";
  USER_INITIAL = name ? name.trim().charAt(0) : "我";
}

let threadId = localStorage.getItem("threadId") || newId();
localStorage.setItem("threadId", threadId);

// ── 视图切换 ──
const titles = { chat: "智能问答", practice: "练习与批改" };
document.querySelectorAll(".nav-item").forEach((item) => {
  item.onclick = () => {
    const view = item.dataset.view;
    document.querySelectorAll(".nav-item").forEach((i) => i.classList.toggle("active", i === item));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
    document.getElementById("view-title").textContent = titles[view];
  };
});

document.getElementById("logout").onclick = async () => {
  await apiPost(API.logout).catch(() => {});
  localStorage.removeItem("user");
  location.href = "/login.html";
};

// ── 极简 Markdown 渲染（无外部依赖，先转义再渲染，天然防 XSS） ──
function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// 行内元素：行内代码 → 加粗 → 链接（顺序重要，代码优先避免内部被继续解析）
function renderInline(s) {
  return s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((s) => s.trim());
}

// 判断一行是否为块级元素起点（用于段落的行合并终止条件）
function isBlockStart(line) {
  return (
    /^\s*```/.test(line) ||
    /^\s*#{1,6}\s+/.test(line) ||
    /^\s*>\s?/.test(line) ||
    /^\s*[-*]\s+/.test(line) ||
    /^\s*\d+[.)]\s+/.test(line) ||
    /^\s*\|.*\|\s*$/.test(line)
  );
}

function renderMarkdown(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 代码块
    if (/^\s*```/.test(line)) {
      const code = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        code.push(lines[i]);
        i++;
      }
      i++; // 跳过结束围栏
      out.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }

    // 标题
    const heading = line.match(/^\s*(#{1,6})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      out.push(`<h${level}>${renderInline(escapeHtml(heading[2]))}</h${level}>`);
      i++;
      continue;
    }

    // 引用
    if (/^\s*>\s?/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      out.push(`<blockquote>${renderInline(escapeHtml(items.join(" ")))}</blockquote>`);
      continue;
    }

    // 表格（当前行含 | 且下一行是分隔行）
    if (
      /^\s*\|.*\|\s*$/.test(line) &&
      i + 1 < lines.length &&
      /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) &&
      lines[i + 1].includes("-")
    ) {
      const headers = splitTableRow(line);
      i += 2; // 跳过分隔行
      const rows = [];
      while (i < lines.length && lines[i].includes("|")) {
        rows.push(splitTableRow(lines[i]));
        i++;
      }
      const thead = `<tr>${headers.map((c) => `<th>${renderInline(escapeHtml(c))}</th>`).join("")}</tr>`;
      const tbody = rows
        .map((r) => `<tr>${r.map((c) => `<td>${renderInline(escapeHtml(c))}</td>`).join("")}</tr>`)
        .join("");
      out.push(`<table><thead>${thead}</thead><tbody>${tbody}</tbody></table>`);
      continue;
    }

    // 无序列表
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ""));
        i++;
      }
      out.push(`<ul>${items.map((it) => `<li>${renderInline(escapeHtml(it))}</li>`).join("")}</ul>`);
      continue;
    }

    // 有序列表
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ""));
        i++;
      }
      out.push(`<ol>${items.map((it) => `<li>${renderInline(escapeHtml(it))}</li>`).join("")}</ol>`);
      continue;
    }

    // 空行
    if (line.trim() === "") {
      i++;
      continue;
    }

    // 普通段落：合并连续非空、非块级起始的行
    const para = [];
    while (i < lines.length && lines[i].trim() !== "" && !isBlockStart(lines[i])) {
      para.push(lines[i].trim());
      i++;
    }
    if (para.length) {
      out.push(`<p>${renderInline(escapeHtml(para.join(" ")))}</p>`);
    }
  }

  return out.join("");
}

// ═══════════════════════════════════════════════════════════════
// 消息渲染：头像 + 气泡 + 操作行
// ═══════════════════════════════════════════════════════════════

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/** 复制文本。优先用 Clipboard API，非安全上下文回退到临时 textarea。 */
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* 落到下面的兜底方案 */
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "absolute";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/**
 * 操作行。
 * question 有值时才提供「重新生成」—— 历史记录里的回答没有关联的提问。
 */
function buildActions(rawText, question) {
  const bar = document.createElement("div");
  bar.className = "msg-actions";

  const copy = document.createElement("button");
  copy.type = "button";
  copy.textContent = "复制";
  copy.onclick = async () => {
    const ok = await copyText(rawText);
    copy.textContent = ok ? "已复制" : "复制失败";
    setTimeout(() => { copy.textContent = "复制"; }, 1500);
  };
  bar.appendChild(copy);

  if (question) {
    const regen = document.createElement("button");
    regen.type = "button";
    regen.textContent = "重新生成";
    regen.onclick = () => sendMessage(question);
    bar.appendChild(regen);
  }
  return bar;
}

/**
 * 创建一条消息行，返回 { row, bubble, body }。
 * opts.markdown 为真按 Markdown 渲染；opts.actions 为真在气泡下方挂操作行。
 * 工具消息不占头像位。
 */
function createRow(type, text, opts = {}) {
  const row = document.createElement("div");
  row.className = `msg-row ${type}`;

  const body = document.createElement("div");
  body.className = "msg-body";

  const bubble = document.createElement("div");
  bubble.className = `msg ${type}`;
  if (opts.markdown) bubble.innerHTML = renderMarkdown(text);
  else bubble.textContent = text;
  body.appendChild(bubble);

  if (opts.actions && text) body.appendChild(buildActions(text, opts.question));

  if (type === "tool") {
    row.appendChild(body);
  } else {
    const avatar = document.createElement("div");
    avatar.className = `avatar ${type === "user" ? "user" : "ai"}`;
    avatar.textContent = type === "user" ? USER_INITIAL : "AI";
    row.append(avatar, body);
  }

  return { row, bubble, body };
}

function appendMessage(type, text, opts = {}) {
  const hint = messagesEl.querySelector(".empty-hint");
  if (hint) hint.remove();
  const { row } = createRow(type, text, opts);
  messagesEl.appendChild(row);
  scrollToBottom();
  return row;
}

function showEmptyHint() {
  messagesEl.innerHTML = EMPTY_HINT_HTML;
  const start = document.getElementById("start-btn");
  if (start) start.onclick = () => document.getElementById("chat-input").focus();
}

// ═══════════════════════════════════════════════════════════════
// 会话列表
// ═══════════════════════════════════════════════════════════════

function groupLabel(iso) {
  if (!iso) return "更早";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "更早";
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86400000;
  const t = d.getTime();
  if (t >= startOfToday) return "今天";
  if (t >= startOfToday - day) return "昨天";
  if (t >= startOfToday - 7 * day) return "7 天内";
  return "更早";
}

function markActiveThread() {
  document.querySelectorAll(".thread-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.threadId === threadId);
  });
}

function renderThreads(list) {
  const el = document.getElementById("thread-list");
  el.innerHTML = "";
  if (!list.length) {
    const empty = document.createElement("div");
    empty.className = "thread-empty";
    empty.textContent = "暂无历史会话";
    el.appendChild(empty);
    return;
  }
  let lastGroup = null;
  for (const t of list) {
    const group = groupLabel(t.updated_at);
    if (group !== lastGroup) {
      const head = document.createElement("div");
      head.className = "thread-group";
      head.textContent = group;
      el.appendChild(head);
      lastGroup = group;
    }
    const title = t.title || "（新会话）";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "thread-item";
    btn.dataset.threadId = t.thread_id;
    btn.textContent = title;
    btn.title = title;
    btn.onclick = () => switchThread(t.thread_id);
    el.appendChild(btn);
  }
  markActiveThread();
}

async function loadThreads() {
  try {
    const res = await apiGet(`${API.threads}?limit=30`);
    if (!res.ok) return;
    const data = await res.json();
    renderThreads(data.threads || []);
  } catch {
    /* 会话列表失败不应影响主流程 */
  }
}

async function loadHistory() {
  let list = [];
  try {
    const res = await apiPost(API.history, { thread_id: threadId });
    if (res.ok) list = (await res.json()).messages || [];
  } catch {
    list = [];
  }
  // 请求期间用户可能已开始发送 —— 放弃渲染，避免把新消息冲掉
  if (sending) return;

  messagesEl.innerHTML = "";
  const visible = list.filter(
    (m) => m && (m.type === "human" || m.type === "ai" || m.type === "tool")
  );
  if (!visible.length) {
    showEmptyHint();
    return;
  }
  for (const m of visible) {
    if (m.type === "human") appendMessage("user", m.content);
    else if (m.type === "ai") appendMessage("ai", m.content, { markdown: true, actions: true });
    else appendMessage("tool", m.content);
  }
  scrollToBottom();
}

async function switchThread(id) {
  if (!id || id === threadId) return;
  threadId = id;
  localStorage.setItem("threadId", threadId);
  markActiveThread();
  await loadHistory();
}

function newThread() {
  threadId = newId();
  localStorage.setItem("threadId", threadId);
  showEmptyHint();
  markActiveThread();
  document.getElementById("chat-input").focus();
}

// ═══════════════════════════════════════════════════════════════
// 聊天（SSE 流式）
// ═══════════════════════════════════════════════════════════════

async function sendMessage(message) {
  if (sending) return;
  sending = true;
  const sendBtn = document.getElementById("send-btn");
  sendBtn.disabled = true;

  appendMessage("user", message);

  const hint = messagesEl.querySelector(".empty-hint");
  if (hint) hint.remove();
  const { row: aiRow, bubble, body } = createRow("ai", "");
  messagesEl.appendChild(aiRow);
  scrollToBottom();

  // 后端未下发检索阶段信号，首个 token 到达前统一显示「检索中」+ 已用时长。
  // 用首个 token 作为「检索结束、开始生成」的真实分界，不假装知道具体阶段。
  const t0 = Date.now();
  const renderThinking = () => {
    const s = ((Date.now() - t0) / 1000).toFixed(1);
    bubble.innerHTML = `<span class="thinking"><i></i>正在检索知识库… ${s}s</span>`;
  };
  renderThinking();
  const timer = setInterval(renderThinking, 100);

  let streamStarted = false;
  let failed = false;
  const stopThinking = () => {
    if (streamStarted) return;
    streamStarted = true;
    clearInterval(timer);
  };

  // expertRaw：专家整条回答（message 事件）；tokenRaw：supervisor 回复（token 流）。
  // 有专家回答时优先展示专家，supervisor 的收尾转述不再叠加，避免重复。
  let expertRaw = "";
  let tokenRaw = "";

  try {
    const res = await apiPost(API.stream, { message, thread_id: threadId });
    if (!res.ok || !res.body) {
      stopThinking();
      failed = true;
      bubble.textContent = res.status === 401 ? "登录已失效，请重新登录" : `请求失败 (${res.status})`;
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop();
      for (const chunk of chunks) {
        if (!chunk.startsWith("data: ")) continue;
        const data = chunk.slice(6);
        if (data === "[DONE]") continue;
        let evt;
        try { evt = JSON.parse(data); } catch { continue; }
        if (evt.type === "token") {
          tokenRaw += evt.content;
          stopThinking();
          bubble.textContent = expertRaw || tokenRaw;
        } else if (evt.type === "message" && evt.content) {
          const m = evt.content;
          if (m.type === "ai" && m.content) {
            expertRaw = m.content;
            stopThinking();
            bubble.textContent = expertRaw || tokenRaw;
          }
        } else if (evt.type === "error") {
          tokenRaw += `\n[错误] ${evt.content}`;
          stopThinking();
          bubble.textContent = expertRaw || tokenRaw;
        }
        scrollToBottom();
      }
    }
  } catch (e) {
    stopThinking();
    failed = true;
    bubble.textContent = `网络错误：${e.message}`;
  } finally {
    clearInterval(timer);
    const finalText = expertRaw || tokenRaw;
    if (finalText) {
      bubble.innerHTML = renderMarkdown(finalText);
      body.appendChild(buildActions(finalText, message));
    } else if (!failed) {
      bubble.textContent = "（没有收到回复，请重试）";
    }
    sending = false;
    sendBtn.disabled = false;
    loadThreads(); // 会话标题 / 排序可能变化
    scrollToBottom();
  }
}

document.getElementById("chat-form").onsubmit = (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const v = input.value.trim();
  if (!v) return;
  input.value = "";
  sendMessage(v);
};

document.getElementById("start-btn").onclick = () => document.getElementById("chat-input").focus();
document.getElementById("new-thread").onclick = newThread;

// ═══════════════════════════════════════════════════════════════
// 出题 / 批改
// ═══════════════════════════════════════════════════════════════

document.getElementById("gen-form").onsubmit = async (e) => {
  e.preventDefault();
  const btn = document.getElementById("gen-btn");
  btn.disabled = true;
  const topic = document.getElementById("topic").value.trim();
  const difficulty = document.getElementById("difficulty").value;
  const container = document.getElementById("questions");
  container.innerHTML = "<p>正在生成题目…</p>";
  try {
    const res = await apiPost(API.questionsGenerate, { topic, count: 1, difficulty });
    if (!res.ok) {
      container.innerHTML = `<p class="error">${await readApiErrorMessage(res)}</p>`;
      return;
    }
    renderQuestions(container, await res.json());
  } catch (e) {
    container.innerHTML = `<p class="error">网络错误：${e.message}</p>`;
  } finally {
    btn.disabled = false;
  }
};

const TYPE_LABELS = {
  choice: "选择",
  fill: "填空",
  short_answer: "简答",
  comprehensive: "综合应用",
};
const DIFFICULTY_LABELS = { basic: "基础", medium: "中等", hard: "困难" };

function renderQuestions(container, data) {
  container.innerHTML = "";
  const questions = data.questions || [];
  if (!questions.length) {
    container.innerHTML = '<p class="error">未生成题目</p>';
    return;
  }
  questions.forEach((q, i) => container.appendChild(buildQuestionCard(q, i)));
}

/** 评分可视化：大号数值 + 档位标签 + 进度条。分数越界时钳到 0–100。 */
function buildScore(raw) {
  const value = Math.max(0, Math.min(100, Number(raw) || 0));
  const level = value >= 85 ? "high" : value >= 60 ? "mid" : "low";
  const levelText = { high: "掌握良好", mid: "基本掌握", low: "需要加强" }[level];

  const wrap = document.createElement("div");
  wrap.className = "score-block";

  const head = document.createElement("div");
  head.className = "score-head";
  const num = document.createElement("span");
  num.className = "score-value";
  num.textContent = String(Math.round(value));
  const unit = document.createElement("span");
  unit.className = "score-unit";
  unit.textContent = "/ 100";
  const tag = document.createElement("span");
  tag.className = "score-level";
  tag.dataset.level = level;
  tag.textContent = levelText;
  head.append(num, unit, tag);

  const bar = document.createElement("div");
  bar.className = "score-bar";
  const fill = document.createElement("div");
  fill.className = "score-fill";
  fill.dataset.level = level;
  fill.style.width = `${value}%`;
  bar.appendChild(fill);

  wrap.append(head, bar);
  return wrap;
}

function buildQuestionCard(q, index) {
  const card = document.createElement("div");
  card.className = "question-card";

  const meta = document.createElement("div");
  meta.className = "question-meta";
  const type = TYPE_LABELS[q.question_type] || q.question_type || "";
  const level = DIFFICULTY_LABELS[q.difficulty] || q.difficulty || "";
  meta.textContent = `第 ${index + 1} 题 · ${type} · ${level}`;

  const stem = document.createElement("div");
  stem.className = "question-stem";
  stem.textContent = q.stem || "（无题干）";

  const answer = document.createElement("textarea");
  answer.className = "answer-input";
  answer.placeholder = "在此输入你的答案…";

  const submit = document.createElement("button");
  submit.className = "btn-primary question-submit";
  submit.textContent = "提交答案";

  const result = document.createElement("div");

  submit.onclick = async () => {
    const userAnswer = answer.value.trim();
    if (!userAnswer) {
      result.className = "grade-result";
      result.textContent = "请先输入答案";
      return;
    }
    submit.disabled = true;
    result.className = "grade-result";
    result.textContent = "正在批改…";
    try {
      // 只提交这一题的题干与它自己的标准答案 —— 不再把含答案的整页文本传过去
      const res = await apiPost(API.questionsGrade, {
        stem: q.stem,
        standard_answer: q.standard_answer || "",
        user_answer: userAnswer,
      });
      if (!res.ok) {
        result.textContent = await readApiErrorMessage(res);
        return;
      }
      const g = await res.json();
      result.innerHTML = "";
      result.appendChild(buildScore(g.score));
      const feedback = document.createElement("div");
      feedback.textContent = g.feedback;
      result.appendChild(feedback);
      if (g.error_analysis) {
        const err = document.createElement("div");
        err.className = "error-analysis";
        err.textContent = `错因分析：${g.error_analysis}`;
        result.appendChild(err);
      }
      result.appendChild(buildReference(q));
    } catch (e) {
      result.textContent = `网络错误：${e.message}`;
    } finally {
      submit.disabled = false;
    }
  };

  card.append(meta, stem, answer, submit, result);
  return card;
}

function buildReference(q) {
  const box = document.createElement("details");
  box.className = "reference-box";
  const summary = document.createElement("summary");
  summary.textContent = "查看参考答案与解析";
  const answerText = document.createElement("div");
  answerText.textContent = `参考答案：${q.standard_answer || "（无）"}`;
  const explanation = document.createElement("div");
  explanation.textContent = `解析：${q.explanation || "（无）"}`;
  box.append(summary, answerText, explanation);
  return box;
}

// ── 启动：先确认用户（决定头像首字），再拉会话列表与当前会话历史 ──
(async () => {
  await loadUser();
  loadThreads();
  await loadHistory();
})();
