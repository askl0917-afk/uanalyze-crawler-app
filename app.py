import io
import json
import zipfile
import subprocess
import sys
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(page_title="UAnalyze 虎八速覽爬蟲", layout="wide")

st.title("UAnalyze 虎八速覽爬蟲版")
st.caption("登入後自動開啟虎八速覽，抓取目前頁面文字，並提供一鍵複製與 ZIP 下載。密碼不會寫入檔案。")

login_url = st.text_input(
    "UAnalyze 登入頁網址",
    value="https://pro.uanalyze.com.tw/login-page",
)

email = st.text_input("UAnalyze Email")
password = st.text_input("UAnalyze 密碼", type="password")

wait_seconds = st.slider("登入後等待秒數", 5, 45, 15)


def copy_button(text: str, label: str = "一鍵複製全部資料"):
    safe_text = json.dumps(text or "", ensure_ascii=False)
    safe_label = json.dumps(label, ensure_ascii=False)

    components.html(
        f"""
        <div style="margin: 12px 0;">
            <button
                onclick="copyTextToClipboard()"
                style="
                    background-color:#ff9800;
                    color:#111;
                    border:none;
                    border-radius:10px;
                    padding:14px 18px;
                    font-size:18px;
                    font-weight:700;
                    cursor:pointer;
                    width:100%;
                    max-width:420px;
                "
            >
                📋 {label}
            </button>
            <div id="copy-status" style="margin-top:10px;color:#20c997;font-size:16px;"></div>
        </div>

        <script>
        const textToCopy = {safe_text};

        async function copyTextToClipboard() {{
            const status = document.getElementById("copy-status");

            try {{
                await navigator.clipboard.writeText(textToCopy);
                status.innerText = "已複製到剪貼簿";
            }} catch (err) {{
                const textarea = document.createElement("textarea");
                textarea.value = textToCopy;
                textarea.style.position = "fixed";
                textarea.style.left = "0";
                textarea.style.top = "0";
                textarea.style.width = "1px";
                textarea.style.height = "1px";
                textarea.style.opacity = "0";
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();

                try {{
                    document.execCommand("copy");
                    status.innerText = "已複製到剪貼簿";
                }} catch (fallbackErr) {{
                    status.innerText = "複製失敗，請改用下方文字框手動長按複製";
                }}

                document.body.removeChild(textarea);
            }}
        }}
        </script>
        """,
        height=100,
    )


def install_playwright_chromium():
    return subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=240,
    )


def close_blockers(page):
    actions = []

    try:
        if page.get_by_text("重新整理", exact=False).count() > 0:
            page.get_by_text("重新整理", exact=False).first.click(timeout=4000)
            actions.append("clicked 重新整理")
            page.wait_for_timeout(6000)
    except Exception:
        pass

    try:
        body = page.locator("body").inner_text(timeout=5000)
        if "系統已有更新" in body or "請重新整理" in body:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(7000)
            actions.append("page.reload")
    except Exception:
        pass

    for t in ["我知道了", "同意", "接受", "接受所有", "OK"]:
        try:
            if page.get_by_text(t, exact=False).count() > 0:
                page.get_by_text(t, exact=False).last.click(timeout=4000)
                actions.append(f"clicked {t}")
                page.wait_for_timeout(1500)
                break
        except Exception:
            pass

    return actions


def fill_like_human(page, email, password):
    actions = []

    email_candidates = [
        "input[placeholder*='Email']",
        "input[placeholder*='email']",
        "input[type='email']",
        "input:not([type])",
        "input[type='text']",
    ]

    email_filled = False

    for selector in email_candidates:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.click(timeout=5000)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.keyboard.type(email, delay=60)
                actions.append(f"typed email by {selector}")
                email_filled = True
                break
        except Exception:
            pass

    password_filled = False

    try:
        loc = page.locator("input[type='password']").first
        if loc.count() > 0:
            loc.click(timeout=5000)
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(password, delay=70)
            actions.append("typed password by input[type=password]")
            password_filled = True
    except Exception:
        pass

    page.wait_for_timeout(1500)

    return {
        "email_filled": email_filled,
        "password_filled": password_filled,
        "actions": actions,
    }


def click_login(page):
    methods = []

    try:
        buttons = page.locator("button").filter(has_text="登入")
        if buttons.count() > 0:
            buttons.last.click(timeout=5000)
            methods.append("clicked button has_text 登入")
            return methods
    except Exception:
        pass

    try:
        clicked = page.evaluate(
            """
            () => {
                function visible(el) {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 5 &&
                           r.height > 5 &&
                           s.display !== 'none' &&
                           s.visibility !== 'hidden' &&
                           s.opacity !== '0';
                }

                const nodes = Array.from(document.querySelectorAll('button, div, span, a'))
                    .filter(visible)
                    .map(el => ({
                        el,
                        text: (el.innerText || '').trim(),
                        top: el.getBoundingClientRect().top,
                    }))
                    .filter(x =>
                        (x.text === '登入' || x.text === '登 入') &&
                        !x.text.includes('Google') &&
                        !x.text.includes('Facebook') &&
                        !x.text.includes('Apple')
                    )
                    .sort((a, b) => a.top - b.top);

                if (!nodes.length) return false;

                nodes[nodes.length - 1].el.scrollIntoView({block: 'center'});
                nodes[nodes.length - 1].el.click();
                return true;
            }
            """
        )

        if clicked:
            methods.append("JS clicked native login")
            return methods
    except Exception:
        pass

    try:
        page.locator("input[type='password']").first.click(timeout=5000)
        page.keyboard.press("Enter")
        methods.append("pressed Enter in password field")
        return methods
    except Exception:
        pass

    return methods


def click_huba_quick_view(page):
    actions = []

    page.wait_for_timeout(3000)

    try:
        if page.get_by_text("虎八速覽", exact=False).count() > 0:
            page.get_by_text("虎八速覽", exact=False).first.click(timeout=5000)
            actions.append("clicked text 虎八速覽")
            page.wait_for_timeout(8000)
            return actions
    except Exception:
        pass

    try:
        hamburger_clicked = page.evaluate(
            """
            () => {
                function visible(el) {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 5 &&
                           r.height > 5 &&
                           s.display !== 'none' &&
                           s.visibility !== 'hidden' &&
                           s.opacity !== '0';
                }

                const nodes = Array.from(document.querySelectorAll('button, div, span'))
                    .filter(visible)
                    .filter(el => {
                        const text = (el.innerText || '').trim();
                        const cls = String(el.className || '').toLowerCase();
                        return text === '☰' || cls.includes('menu') || cls.includes('hamburger');
                    });

                if (!nodes.length) return false;
                nodes[0].click();
                return true;
            }
            """
        )

        if hamburger_clicked:
            actions.append("clicked possible menu/hamburger")
            page.wait_for_timeout(3000)
    except Exception:
        pass

    try:
        if page.get_by_text("虎八速覽", exact=False).count() > 0:
            page.get_by_text("虎八速覽", exact=False).first.click(timeout=5000)
            actions.append("clicked text 虎八速覽 after menu")
            page.wait_for_timeout(8000)
            return actions
    except Exception:
        pass

    try:
        clicked = page.evaluate(
            """
            () => {
                function visible(el) {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 5 &&
                           r.height > 5 &&
                           s.display !== 'none' &&
                           s.visibility !== 'hidden' &&
                           s.opacity !== '0';
                }

                const nodes = Array.from(document.querySelectorAll('button, a, div, span, li'))
                    .filter(visible)
                    .map(el => ({
                        el,
                        text: (el.innerText || '').trim(),
                        top: el.getBoundingClientRect().top,
                        left: el.getBoundingClientRect().left,
                        len: ((el.innerText || '').trim()).length
                    }))
                    .filter(x => x.text.includes('虎八速覽'))
                    .sort((a, b) => a.len - b.len || a.left - b.left || a.top - b.top);

                if (!nodes.length) return false;

                nodes[0].el.scrollIntoView({block: 'center'});
                nodes[0].el.click();
                return true;
            }
            """
        )

        if clicked:
            actions.append("JS clicked visible 虎八速覽")
            page.wait_for_timeout(8000)
            return actions
    except Exception:
        pass

    actions.append("failed to click 虎八速覽")
    return actions


def build_markdown(title, url, text):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f"""# UAnalyze 虎八速覽爬蟲結果

- 擷取時間：{now}
- 頁面標題：{title}
- 頁面網址：{url}

---

{text}
"""


if st.button("登入並開啟虎八速覽"):
    if not email or not password:
        st.error("請先輸入 Email 和密碼。")
        st.stop()

    st.info("開始檢查 Playwright Chromium，這一步可能需要 1～3 分鐘。")

    install = install_playwright_chromium()

    if install.returncode != 0:
        st.error("Playwright Chromium 安裝失敗。")
        st.code(install.stdout + "\n" + install.stderr)
        st.stop()

    st.success("Playwright Chromium 安裝 / 檢查完成。")

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )

            page = context.new_page()

            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)

            blocker_actions = close_blockers(page)
            page.wait_for_timeout(3000)

            fill_result = fill_like_human(page, email, password)
            filled_screenshot = page.screenshot(full_page=True)

            login_methods = click_login(page)

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(wait_seconds * 1000)

            login_title = page.title()
            login_url_after = page.url
            login_text = page.locator("body").inner_text(timeout=10000)
            login_screenshot = page.screenshot(full_page=True)

            huba_actions = click_huba_quick_view(page)

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(5000)

            huba_title = page.title()
            huba_url = page.url

            try:
                huba_text = page.locator("body").inner_text(timeout=10000)
            except Exception:
                huba_text = ""

            huba_screenshot = page.screenshot(full_page=True)

            browser.close()

        result_markdown = build_markdown(huba_title, huba_url, huba_text)

        st.subheader("登入結果")
        st.write("彈窗 / Cookie 處理動作：", blocker_actions)
        st.write("填表結果：", fill_result)
        st.write("登入點擊方法：", login_methods)
        st.write("登入後標題：", login_title)
        st.write("登入後網址：", login_url_after)

        st.image(filled_screenshot, caption="填入 Email / 密碼後截圖")
        st.image(login_screenshot, caption="登入後截圖")

        st.subheader("虎八速覽開啟結果")
        st.write("虎八速覽點擊動作：", huba_actions)
        st.write("目前頁面標題：", huba_title)
        st.write("目前頁面網址：", huba_url)

        st.image(huba_screenshot, caption="虎八速覽頁面截圖")

        st.subheader("目前頁面文字")

        copy_button(result_markdown, "一鍵複製虎八速覽全部文字")

        st.text_area("page text", result_markdown, height=400)

        success_hint = "虎八速覽" in huba_text or "速覽" in huba_text

        if success_hint:
            st.success("看起來已經成功進入虎八速覽。")
        else:
            st.warning("可能尚未成功進入虎八速覽，請看截圖與頁面文字。")

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"uanalyze_huba_quick_view_{now}.zip"

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("_ALL_CONTENT.md", result_markdown)
            z.writestr("huba_body_text.txt", huba_text)
            z.writestr(
                "debug_info.txt",
                f"blocker_actions={blocker_actions}\n"
                f"fill_result={fill_result}\n"
                f"login_methods={login_methods}\n"
                f"login_title={login_title}\n"
                f"login_url_after={login_url_after}\n"
                f"huba_actions={huba_actions}\n"
                f"huba_title={huba_title}\n"
                f"huba_url={huba_url}\n"
            )
            z.writestr("filled_screenshot.png", filled_screenshot)
            z.writestr("login_screenshot.png", login_screenshot)
            z.writestr("huba_screenshot.png", huba_screenshot)

        zip_buffer.seek(0)

        st.download_button(
            label="下載虎八速覽 ZIP",
            data=zip_buffer,
            file_name=zip_name,
            mime="application/zip",
        )

        st.download_button(
            label="下載 Markdown",
            data=result_markdown.encode("utf-8"),
            file_name=f"uanalyze_huba_quick_view_{now}.md",
            mime="text/markdown",
        )

    except Exception as e:
        st.error("開啟虎八速覽流程失敗。")
        st.exception(e)
