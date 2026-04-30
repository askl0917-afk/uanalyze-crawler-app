import io
import zipfile
import subprocess
import sys
from datetime import datetime

import streamlit as st


st.set_page_config(page_title="UAnalyze Login Diagnostic", layout="wide")

st.title("UAnalyze 登入流程診斷版 v2")
st.caption("會先處理重新整理彈窗與 Cookie，再測試 Google 登入是否跳轉。")

company = st.text_input("請輸入公司代號與名稱", value="3030_德律")

login_url = st.text_input(
    "UAnalyze 登入頁網址",
    value="https://pro.uanalyze.com.tw/login-page",
)

wait_seconds = st.slider("點擊 Google 登入後等待秒數", 5, 30, 12)


def install_playwright_chromium():
    return subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=240,
    )


def try_click_text(page, text, exact=False):
    try:
        page.get_by_text(text, exact=exact).click(timeout=4000)
        return True
    except Exception:
        return False


def close_blockers(page):
    actions = []

    # 先處理「有新版本，請重新整理」彈窗
    if try_click_text(page, "重新整理"):
        actions.append("clicked 重新整理")
        page.wait_for_timeout(5000)

    # 有些情況點重新整理後頁面沒有真正 reload，再補一次 reload
    try:
        body = page.locator("body").inner_text(timeout=5000)
        if "系統已有更新" in body or "請重新整理" in body:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            actions.append("page.reload")
    except Exception:
        pass

    # 處理 Cookie 同意按鈕
    cookie_candidates = [
        "我知道了",
        "同意",
        "接受",
        "接受所有",
        "OK",
    ]

    for t in cookie_candidates:
        if try_click_text(page, t):
            actions.append(f"clicked cookie/button: {t}")
            page.wait_for_timeout(1500)
            break

    return actions


def click_google_login(page):
    # 方法 1：直接找「Google 登入」
    try:
        page.get_by_text("Google 登入", exact=False).click(timeout=6000)
        return "get_by_text Google 登入"
    except Exception:
        pass

    # 方法 2：找包含 Google 的可見元素
    try:
        ok = page.evaluate(
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

                const nodes = Array.from(document.querySelectorAll(
                    'button, a, div, span, p'
                ));

                const matches = nodes
                    .filter(el => visible(el))
                    .filter(el => (el.innerText || '').includes('Google'))
                    .map(el => ({
                        el,
                        text: (el.innerText || '').trim(),
                        len: ((el.innerText || '').trim()).length,
                        top: el.getBoundingClientRect().top
                    }))
                    .sort((a, b) => a.len - b.len || a.top - b.top);

                if (!matches.length) return false;

                matches[0].el.scrollIntoView({block: 'center'});
                matches[0].el.click();
                return true;
            }
            """
        )
        if ok:
            return "JS clicked visible Google element"
    except Exception:
        pass

    return ""


if st.button("測試 Google 登入流程 v2"):
    st.info("開始檢查 Playwright Chromium，這一步可能需要 1～3 分鐘。")

    install = install_playwright_chromium()

    if install.returncode != 0:
        st.error("Playwright Chromium 安裝失敗。")
        st.code(install.stdout + "\n" + install.stderr)
        st.stop()

    st.success("Playwright Chromium 安裝 / 檢查完成。")

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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

            click_method = ""

            # 先假設 Google 可能開新視窗
            try:
                with page.expect_popup(timeout=8000) as popup_info:
                    click_method = click_google_login(page)

                popup = popup_info.value
                popup.wait_for_load_state("domcontentloaded", timeout=30000)
                popup.wait_for_timeout(wait_seconds * 1000)
                target_page = popup
                target_type = "popup"

            except PlaywrightTimeoutError:
                # 沒有新視窗，就看原頁有沒有跳轉
                if not click_method:
                    click_method = click_google_login(page)

                page.wait_for_timeout(wait_seconds * 1000)
                target_page = page
                target_type = "same_page"

            after_title = target_page.title()
            after_url = target_page.url

            try:
                after_text = target_page.locator("body").inner_text(timeout=10000)
            except Exception:
                after_text = ""

            after_screenshot = target_page.screenshot(full_page=True)

            browser.close()

        status = response.status if response else "無 response"

        st.subheader("處理結果")
        st.write("HTTP 狀態碼：", status)
        st.write("彈窗 / Cookie 處理動作：", blocker_actions)
        st.write("Google 點擊方法：", click_method or "沒有成功點擊")
        st.write("跳轉型態：", target_type)

        st.subheader("登入前狀態")
        st.write("登入前標題：", before_title)
        st.write("登入前網址：", before_url)
        st.image(before_screenshot, caption="登入前截圖")

        st.subheader("點擊 Google 登入後狀態")
        st.write("登入後標題：", after_title)
        st.write("登入後網址：", after_url)
        st.image(after_screenshot, caption="點擊 Google 登入後截圖")

        st.subheader("登入後頁面文字")
        st.text_area("after body text", after_text, height=300)

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"{company}_google_login_debug_v2_{now}.zip"

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("before_body_text.txt", before_text)
            z.writestr("after_body_text.txt", after_text)
            z.writestr(
                "debug_info.txt",
                f"status={status}\n"
                f"blocker_actions={blocker_actions}\n"
                f"before_title={before_title}\n"
                f"before_url={before_url}\n"
                f"click_method={click_method}\n"
                f"target_type={target_type}\n"
                f"after_title={after_title}\n"
                f"after_url={after_url}\n"
            )
            z.writestr("before_screenshot.png", before_screenshot)
            z.writestr("after_screenshot.png", after_screenshot)

        zip_buffer.seek(0)

        st.download_button(
            label="下載 Google 登入診斷 ZIP",
            data=zip_buffer,
            file_name=zip_name,
            mime="application/zip",
        )

    except Exception as e:
        st.error("Google 登入流程診斷失敗。")
        st.exception(e)
