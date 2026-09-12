// 凭证存放在 httpOnly cookie 中（JS 读不到，也不该读），改为向服务端确认会话。
// 同源 fetch 默认携带 cookie，因此后续请求无需再手动附带 Authorization 头。
async function loadUser() {
  const res = await fetch("/api/auth/me");
  if (!res.ok) {
    localStorage.removeItem("user");
    location.href = "/login.html";
    return;
  }
  const u = await res.json();
  localStorage.setItem("user", JSON.stringify(u)); // 仅用于首屏展示，不含凭证
  document.getElementById("user-name").textContent = u.display_name || u.username || "";
  document.getElementById("user-role").textContent = u.role || "";
}
loadUser();

/** 从 API 错误响应提取可展示文案（兼容 detail 字符串或 {code,message}）。 */
async function readApiErrorMessage(res) {
  const data = await res.json().catch(() => ({}));
  const detail = data && data.detail;
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  if (typeof detail === "string" && detail) return detail;
  return `请求失败 (${res.status})`;
}

let threadId = localStorage.getItem("threadId") || crypto.randomUUID();
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
  await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
  localStorage.removeItem("user");
  location.href = "/login.html";
};

// ── 聊天（SSE 流式）──
const messagesEl = document.getElementById("messages");
let sending = false;

function addMessage(type, content) {
  const hint = messagesEl.querySelector(".empty-hint");
  if (hint) hint.remove();
  const div = document.createElement("div");
  div.className = `msg ${type}`;
  div.textContent = content;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return div;
}

async function sendMessage(message) {
  if (sending) return;
  sending = true;
  document.getElementById("send-btn").disabled = true;
  addMessage("user", message);
  const aiDiv = addMessage("ai", "");

  try {
    const res = await fetch("/api/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, thread_id: threadId }),
    });
    if (!res.ok || !res.body) {
      aiDiv.textContent = res.status === 401 ? "登录已失效，请重新登录" : `请求失败 (${res.status})`;
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
          aiDiv.textContent += evt.content;
        } else if (evt.type === "message" && evt.content) {
          const m = evt.content;
          if (m.type === "ai" && m.content && aiDiv.textContent === "") {
            aiDiv.textContent = m.content;
          }
        } else if (evt.type === "error") {
          aiDiv.textContent += `\n[错误] ${evt.content}`;
        }
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }
  } catch (e) {
    aiDiv.textContent = `网络错误：${e.message}`;
  } finally {
    sending = false;
    document.getElementById("send-btn").disabled = false;
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

// ── 出题 / 批改 ──
document.getElementById("gen-form").onsubmit = async (e) => {
  e.preventDefault();
  const btn = document.getElementById("gen-btn");
  btn.disabled = true;
  const topic = document.getElementById("topic").value.trim();
  const difficulty = document.getElementById("difficulty").value;
  const container = document.getElementById("questions");
  container.innerHTML = "<p>正在生成题目…</p>";
  try {
    const res = await fetch("/api/questions/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, count: 1, difficulty }),
    });
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
  submit.className = "btn-primary";
  submit.textContent = "提交答案";
  submit.style.marginTop = "10px";

  const result = document.createElement("div");

  submit.onclick = async () => {
    const userAnswer = answer.value.trim();
    if (!userAnswer) {
      alert("请先输入答案");
      return;
    }
    submit.disabled = true;
    result.className = "grade-result";
    result.textContent = "正在批改…";
    try {
      // 只提交这一题的题干与它自己的标准答案 —— 不再把含答案的整页文本传过去
      const res = await fetch("/api/questions/grade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          stem: q.stem,
          standard_answer: q.standard_answer || "",
          user_answer: userAnswer,
        }),
      });
      if (!res.ok) {
        result.textContent = `批改失败 (${res.status})`;
        return;
      }
      const g = await res.json();
      result.innerHTML = "";
      const score = document.createElement("div");
      score.className = "score";
      score.textContent = `得分：${g.score}/100`;
      const feedback = document.createElement("div");
      feedback.textContent = g.feedback;
      result.append(score, feedback);
      if (g.error_analysis) {
        const err = document.createElement("div");
        err.style.marginTop = "8px";
        err.style.color = "#7c3aed";
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
  box.style.marginTop = "10px";
  const summary = document.createElement("summary");
  summary.textContent = "查看参考答案与解析";
  const answerText = document.createElement("div");
  answerText.style.marginTop = "6px";
  answerText.textContent = `参考答案：${q.standard_answer || "（无）"}`;
  const explanation = document.createElement("div");
  explanation.style.marginTop = "4px";
  explanation.textContent = `解析：${q.explanation || "（无）"}`;
  box.append(summary, answerText, explanation);
  return box;
}
