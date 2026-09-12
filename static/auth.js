let mode = "login";

// 凭证在 httpOnly cookie 中，JS 读不到，只能问服务端是否已登录
apiGet(API.me).then((res) => {
  if (res.ok) location.href = "/index.html";
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.onclick = () => {
    mode = tab.dataset.mode;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === tab));
    document.getElementById("display-name").classList.toggle("hidden", mode !== "register");
    document.getElementById("submit-btn").textContent = mode === "login" ? "登录" : "注册";
  };
});

document.getElementById("auth-form").onsubmit = async (e) => {
  e.preventDefault();
  const err = document.getElementById("error");
  err.textContent = "";
  const btn = document.getElementById("submit-btn");
  btn.disabled = true;
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
  } catch (e) {
    err.textContent = "网络错误，请检查后端服务是否启动";
  } finally {
    btn.disabled = false;
  }
};
