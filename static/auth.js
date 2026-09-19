let mode = "login";

// 凭证在 httpOnly cookie 中，JS 读不到，只能问服务端是否已登录
apiGet(API.me).then((res) => {
  if (res.ok) location.href = "/index.html";
});

const MODE_TEXT = {
  login: { title: "欢迎回来", sub: "登录后继续你的学习", btn: "登录" },
  register: { title: "创建账号", sub: "注册后即可开始学习", btn: "注册" },
};

/** 切换登录/注册：标签选中态、昵称字段显隐、标题与按钮文案 */
function applyMode(next) {
  mode = MODE_TEXT[next] ? next : "login";
  const text = MODE_TEXT[mode];
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("active", tab.dataset.mode === mode);
  });
  document.getElementById("display-name-field").classList.toggle("hidden", mode !== "register");
  document.getElementById("submit-label").textContent = text.btn;
  document.getElementById("auth-title").textContent = text.title;
  document.getElementById("auth-sub").textContent = text.sub;
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => applyMode(tab.dataset.mode);
});

// 密码显隐
const pwInput = document.getElementById("password");
const pwToggle = document.getElementById("toggle-pw");
pwToggle.onclick = () => {
  const show = pwInput.type === "password";
  pwInput.type = show ? "text" : "password";
  pwToggle.textContent = show ? "隐藏" : "显示";
};

document.getElementById("auth-form").onsubmit = async (e) => {
  e.preventDefault();
  const err = document.getElementById("error");
  err.textContent = "";
  const btn = document.getElementById("submit-btn");
  btn.disabled = true;
  btn.classList.add("loading");
  const body = {
    username: document.getElementById("username").value.trim(),
    password: document.getElementById("password").value,
  };
  if (mode === "register") {
    body.display_name = document.getElementById("display-name").value.trim();
  }
  try {
    const path = mode === "register" ? API.register : API.login;
    const res = await apiPost(path, body);
    if (!res.ok) {
      err.textContent = await readApiErrorMessage(res);
      return;
    }
    const data = await res.json();
    // 凭证由服务端写入 httpOnly cookie；localStorage 只存展示用信息
    localStorage.setItem("user", JSON.stringify(data.user));
    location.href = "/index.html";
  } catch {
    err.textContent = "网络错误，请检查后端服务是否启动";
  } finally {
    btn.disabled = false;
    btn.classList.remove("loading");
  }
};
