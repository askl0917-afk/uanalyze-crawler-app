import io
import zipfile
import subprocess
import sys
from datetime import datetime

import streamlit as st


st.set_page_config(page_title="UAnalyze Email Login Test v2", layout="wide")

st.title("UAnalyze Email 登入診斷版 v2")
st.caption("這版會用真人鍵盤輸入方式測試 Email / 密碼登入。密碼不會寫入檔案。")

login_url = st.text_input(
    "UAnalyze 登入頁網址",
    value="https://pro.uanalyze.com.tw/login-page",
)

email = st.text_input("UAnalyze Email")
password = st.text_input("UAnalyze 密碼", type="password")

wait_seconds = st.slider("按下登入後等待秒數", 5, 45, 20)


def install_playwright_chromium():
    return subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=240,
    )


def try_click_text(page, text):
    try:
        page.get_by_text(text, exact=False).click(timeout=4000)
        return True
    except Exception:
        return False


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

    # 找 Email 欄位
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

    # 找密碼欄位
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

    # 方法 1：找 button 裡面文字剛好是登入
    try:
        buttons = page.locator("button").filter(has_text="登入")
        if buttons.count() > 0:
            buttons.last.click(timeout=5000)
            methods.append("clicked button has_text 登入")
            return methods
    except Exception:
        pass

    # 方法 2：找任意可見元素，排除 Google/Facebook/Apple
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

    # 方法 3：密碼欄位 Enter
    try:
        page.locator("input[type='password']").first.click(timeout=5000)
        page.keyboard.press("Enter")
        methods.append("pressed Enter in password field")
        return methods
    except Exception:
        pass

    return methods


if st.button("測試 Email 登入 v2"):
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

            before_title = page.title()
            before_url = page.url
            before_text = page.locator("body").inner_text(timeout=10000)
            before_screenshot = page.screenshot(full_page=True)

            fill_result = fill_like_human(page, email, password)
            filled_screenshot = page.screenshot(full_page=True)

            login_methods = click_login(page)

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(wait_seconds * 1000)

            after_title = page.title()
            after_url = page.url

            try:
                after_text = page.locator("body").inner_text(timeout=10000)
            except Exception:
                after_text = ""

            after_screenshot = page.screenshot(full_page=True)

            browser.close()

        st.subheader("處理結果")
        st.write("彈窗 / Cookie 處理動作：", blocker_actions)
        st.write("填表結果：", fill_result)
        st.write("登入點擊方法：", login_methods)

        st.subheader("登入前狀態")
        st.write("登入前標題：", before_title)
        st.write("登入前網址：", before_url)
        st.image(before_screenshot, caption="登入前截圖")

        st.subheader("填入 Email / 密碼後截圖")
        st.image(filled_screenshot, caption="填入後截圖")

        st.subheader("點擊登入後狀態")
        st.write("登入後標題：", after_title)
        st.write("登入後網址：", after_url)
        st.image(after_screenshot, caption="登入後截圖")

        st.subheader("登入後頁面文字")
        st.text_area("after body text", after_text, height=300)

        success_hint = (
            "login-page" not in after_url
            and "Google 登入" not in after_text
            and "Facebook 登入" not in after_text
            and "Apple 登入" not in after_text
        )

        if success_hint:
            st.success("看起來可能已經登入成功。")
        else:
            st.warning("看起來仍停在登入頁，這次尚未成功登入。")

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"uanalyze_email_login_v2_debug_{now}.zip"

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("before_body_text.txt", before_text)
            z.writestr("after_body_text.txt", after_text)
            z.writestr(
                "debug_info.txt",
                f"blocker_actions={blocker_actions}\n"
                f"before_title={before_title}\n"
                f"before_url={before_url}\n"
                f"fill_result={fill_result}\n"
                f"login_methods={login_methods}\n"
                f"after_title={after_title}\n"
                f"after_url={after_url}\n"
            )
            z.writestr("before_screenshot.png", before_screenshot)
            z.writestr("filled_screenshot.png", filled_screenshot)
            z.writestr("after_screenshot.png", after_screenshot)

        zip_buffer.seek(0)

        st.download_button(
            label="下載 Email 登入 v2 診斷 ZIP",
            data=zip_buffer,
            file_name=zip_name,
            mime="application/zip",
        )

    except Exception as e:
        st.error("Email 登入 v2 診斷失敗。")
        st.exception(e)
