/**
 * 前端 API 基址与错误文案 —— 路径只在这里维护。
 * 与后端 service 路由对齐；改后端路径时先改这里。
 */
const API = {
  me: "/api/auth/me",
  login: "/api/auth/login",
  register: "/api/auth/register",
  logout: "/api/auth/logout",
  stream: "/api/stream",
  questionsGenerate: "/api/questions/generate",
  questionsGrade: "/api/questions/grade",
};

/** 从 API 错误响应提取可展示文案（兼容 detail 字符串或 {code,message}）。 */
async function readApiErrorMessage(res) {
  const data = await res.json().catch(() => ({}));
  const detail = data && data.detail;
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  if (typeof detail === "string" && detail) return detail;
  return `请求失败 (${res.status})`;
}

/** JSON POST，凭证走同源 cookie。 */
async function apiPost(path, body) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

/** JSON GET，凭证走同源 cookie。 */
async function apiGet(path) {
  return fetch(path);
}
