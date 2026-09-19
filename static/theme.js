/**
 * 主题（浅色 / 深色）。
 *
 * **必须在 `<head>` 中同步加载**：主题要在首次绘制前落到 `<html data-theme>` 上，
 * 否则页面会先闪一下浅色再切深色（FOUC）。本脚本只改一个属性、不依赖 DOM，
 * 所以放在 head 里是安全的。
 *
 * 优先级：用户显式选择（localStorage）> 系统偏好（`prefers-color-scheme`）。
 * 用户一旦点过切换按钮，就以他的选择为准，不再跟随系统。
 */
(function () {
  var KEY = "edu-theme";
  var root = document.documentElement;

  function readSaved() {
    try {
      return localStorage.getItem(KEY);
    } catch (e) {
      return null; // 隐私模式下 localStorage 可能不可用
    }
  }

  function save(value) {
    try {
      localStorage.setItem(KEY, value);
    } catch (e) {
      /* 写不了就算了，本次会话内仍然生效 */
    }
  }

  function preferred() {
    var saved = readSaved();
    if (saved === "light" || saved === "dark") return saved;
    try {
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch (e) {
      return "light";
    }
  }

  root.dataset.theme = preferred();

  function bindToggle() {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    var sync = function () {
      var dark = root.dataset.theme === "dark";
      btn.textContent = dark ? "浅色" : "深色";
      btn.title = dark ? "切换到浅色模式" : "切换到深色模式";
      btn.setAttribute("aria-label", btn.title);
    };
    sync();
    btn.onclick = function () {
      var next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      save(next);
      sync();
    };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindToggle);
  } else {
    bindToggle();
  }
})();
