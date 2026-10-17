"""前端体检动态实测（第二轮）：二次生成清空缺陷 / 批改错误态 / 聊天错误路径 / 移动端。"""

import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = os.path.join(os.environ["TEMP"], "edu_audit_shots")

console_msgs = []
page_errors = []


def shot(pg, name):
    pg.screenshot(path=os.path.join(SHOTS, name), full_page=True)
    print("shot:", name, flush=True)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    pg = ctx.new_page()
    pg.on("console", lambda m: console_msgs.append({"type": m.type, "text": m.text[:220]}))
    pg.on("pageerror", lambda e: page_errors.append(str(e)[:300]))

    pg.goto(f"{BASE}/login.html", wait_until="networkidle")
    pg.fill("#username", "audit_20261017")
    pg.fill("#password", "auditpass123")
    pg.click("#submit-btn")
    pg.wait_for_url("**/index.html", timeout=20000)
    pg.wait_for_load_state("networkidle")

    # A. 首题 + 填入答案（不提交）
    pg.click('button[data-view="practice"]')
    pg.fill("#topic", "进程死锁")
    pg.click("#gen-btn")
    pg.wait_for_selector(".question-card", timeout=120000)
    pg.locator(".answer-input").first.fill("这是第一题的作答内容，用于验证二次生成是否清空。")
    shot(pg, "12_practice_q1_answered.png")

    # B. 生成第二题 —— 缺陷验证：第一题连同作答应当被清空
    pg.fill("#topic", "图的最短路径")
    pg.click("#gen-btn")
    time.sleep(40)
    cards = pg.locator(".question-card").count()
    answers = pg.locator(".answer-input").count()
    print(f"[wipe-check] question-cards={cards} answer-inputs={answers}", flush=True)
    shot(pg, "13_practice_second_gen_wipe.png")

    # C. 对剩余题目提交批改（预期 500 错误态）
    pg.locator(".answer-input").first.fill(
        "Dijkstra 算法适用于非负权图，Bellman-Ford 可以处理负权边。"
    )
    pg.locator(".question-submit").first.click()
    time.sleep(20)
    result_text = ""
    try:
        result_text = pg.locator(".grade-result").first.inner_text()[:150]
    except Exception as e:
        result_text = f"(no .grade-result: {e})"
    print(f"[grade-error-state] {result_text}", flush=True)
    shot(pg, "14_practice_grade_error.png")

    # D. 聊天错误路径（LLM 欠费）
    pg.click('button[data-view="chat"]')
    pg.fill("#chat-input", "什么是进程死锁？")
    pg.click("#send-btn")
    time.sleep(35)
    shot(pg, "15_chat_error_path.png")

    # E. 移动端
    ctx2 = b.new_context(
        viewport={"width": 375, "height": 812}, locale="zh-CN", is_mobile=True, has_touch=True
    )
    pg2 = ctx2.new_page()
    pg2.on(
        "console",
        lambda m: console_msgs.append({"type": m.type, "text": "[mobile] " + m.text[:200]}),
    )
    pg2.on("pageerror", lambda e: page_errors.append("[mobile] " + str(e)[:300]))
    pg2.goto(f"{BASE}/login.html", wait_until="networkidle")
    shot(pg2, "16_login_mobile.png")
    pg2.fill("#username", "audit_20261017")
    pg2.fill("#password", "auditpass123")
    pg2.click("#submit-btn")
    pg2.wait_for_url("**/index.html", timeout=20000)
    pg2.wait_for_load_state("networkidle")
    time.sleep(0.5)
    shot(pg2, "17_main_mobile.png")
    pg2.click('button[data-view="practice"]')
    time.sleep(0.4)
    shot(pg2, "18_practice_mobile.png")

    b.close()

result = {"console": console_msgs, "page_errors": page_errors}
with open(os.path.join(SHOTS, "audit_result2.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print("=== DONE ===")
print(json.dumps(result, ensure_ascii=False, indent=1)[:4000])
