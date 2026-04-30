import io
import zipfile
import subprocess
import sys
from datetime import datetime

import streamlit as st


st.set_page_config(page_title="UAnalyze Email Login Test", layout="wide")

st.title("UAnalyze Email 登入診斷版")
st.caption("測試 Streamlit 雲端瀏覽器是否能用 UAnalyze 原生 Email / 密碼登入。密碼只在當次執行使用，不會寫入 ZIP。")

login_url = st.text_input(
    "UAnalyze 登入頁網址",
    value="https://pro.uanalyze.com.tw/login-page",
)

email = st.text_input("UAnalyze Email")
password = st.text_input("UAnalyze 密碼", type="password")

wait_seconds = st.slider("按下登入後等待秒數", 5, 40, 15)


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

    # 處理「有新版本，請重新整理」
    if try_click_text(page, "重新整理"):
        actions.append("clicked 重新整理")
        page.wait_for_timeout(5000)

    try:
        body = page.locator("body").inner_text(timeout=5000)
        if "系統已有更新" in body or "請重新整理" in body:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            actions.append("page.reload")
    except Exception:
        pass

    # 處理 Cookie
    for t in ["我知道了", "同意", "接受", "接受所有", "OK"]:
        if try_click_text(page, t):
            actions.append(f"clicked cookie/button: {t}")
            page.wait_for_timeout(1500)
            break

    return actions


def fill_login_form(page, email, password):
    """
    針對一般登入表單：
    - 找 visible input
    - type=password 填密碼
    - 其他第一個文字欄位填 email
    """
    result = page.evaluate(
        """
        ({email, password}) => {
            function visible(el) {
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width > 5 &&
                       r.height > 5 &&
                       s.display !== 'none' &&
                       s.visibility !== 'hidden' &&
                       s.opacity !== '0';
            }

            function setValue(el, value) {
                el.focus();
                el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }

            const inputs = Array.from(document.querySelectorAll('input'))
                .filter(visible);

            const passwordInput = inputs.find(i => (i.type || '').toLowerCase() === 'password');

            const emailInput = inputs.find(i => {
                const type = (i.type || '').toLowerCase();
                const ph = (i.placeholder || '').toLowerCase();
                const name = (i.name || '').toLowerCase();
                return type === 'email' ||
                       ph.includes('email') ||
                       name.includes('email') ||
                       (!['password', 'checkbox', 'radio', 'submit', 'button'].includes(type));
            });

            if (emailInput) setValue(emailInput, email);
            if (passwordInput) setValue(passwordInput, password);

            return {
                input_count: inputs.length,
                has_email_input: !!emailInput,
                has_password_input: !!passwordInput,
                email_placeholder: emailInput ? emailInput.placeholder : '',
                password_placeholder: passwordInput ? passwordInput.placeholder : ''
            };
        }
        """,
        {"email": email, "password": password},
    )

    page.wait_for_timeout(1000)
    return result


def click_native_login_button(page):
    # 避免點到 Google / Facebook / Apple 登入，優先點「純登入」按鈕
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
                        len: ((el.innerText || '').trim()).length
                    }))
                    .filter(x => x.text === '登入' || x.text === '登 入');

                if (!nodes.length) return false;

                nodes.sort((a, b) => a.top - b.top || a.len - b.len);
                const target = nodes[nodes.length - 1].el;
                target.scrollIntoView({block: 'center'});
                target.click();
                return true;
            }
            """
        )
        if clicked:
            return "JS clicked native 登入"
    except Exception:
        pass

    try:
        page.get_by_text("登入", exact=True).last.click(timeout=5000)
        return "get_by_text 登入 last"
    except Exception:
        return ""


if st.button("測試 Email / 密碼登入"):
    if not email or not password:
        st.error("請先在上方輸入 Email 和密碼。")
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
                    "--disable-blink-features=AutomationControlled",
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

            response = page.goto(
                login_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(5000)

            blocker_actions = close_blockers(page)
            page.wait_for_timeout(3000)

            before_title = page.title()
            before_url = page.url
            before_text = page.locator("body").inner_text(timeout=10000)
            before_screenshot = page.screenshot(full_page=True)

            fill_result = fill_login_form(page, email, password)
            filled_screenshot = page.screenshot(full_page=True)

            click_method = click_native_login_button(page)

            page.wait_for_timeout(wait_seconds * 1000)

            after_title = page.title()
            after_url = page.url

            try:
                after_text = page.locator("body").inner_text(timeout=10000)
            except Exception:
                after_text = ""

            after_screenshot = page.screenshot(full_page=True)

            browser.close()

        status = response.status if response else "無 response"

        st.subheader("處理結果")
        st.write("HTTP 狀態碼：", status)
        st.write("彈窗 / Cookie 處理動作：", blocker_actions)
        st.write("填表結果：", fill_result)
        st.write("登入按鈕點擊方法：", click_method or "沒有成功點擊")

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

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"uanalyze_email_login_debug_{now}.zip"

        zip_buffer = io.BytesIO()

        # 注意：不寫入 email/password
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("before_body_text.txt", before_text)
            z.writestr("after_body_text.txt", after_text)
            z.writestr(
                "debug_info.txt",
                f"status={status}\n"
                f"blocker_actions={blocker_actions}\n"
                f"before_title={before_title}\n"
                f"before_url={before_url}\n"
                f"fill_result={fill_result}\n"
                f"click_method={click_method}\n"
                f"after_title={after_title}\n"
                f"after_url={after_url}\n"
            )
            z.writestr("before_screenshot.png", before_screenshot)
            z.writestr("filled_screenshot.png", filled_screenshot)
            z.writestr("after_screenshot.png", after_screenshot)

        zip_buffer.seek(0)

        st.download_button(
            label="下載 Email 登入診斷 ZIP",
            data=zip_buffer,
            file_name=zip_name,
            mime="application/zip",
        )

    except Exception as e:
        st.error("Email / 密碼登入流程診斷失敗。")
        st.exception(e)
