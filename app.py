import io
import zipfile
import subprocess
import sys
from datetime import datetime

import streamlit as st


st.set_page_config(page_title="UAnalyze Login Diagnostic", layout="wide")

st.title("UAnalyze 登入流程診斷版")
st.caption("這一步只測試雲端瀏覽器點 Google 登入後會看到什麼畫面，不要輸入任何帳號密碼。")

company = st.text_input("請輸入公司代號與名稱", value="3030_德律")

login_url = st.text_input(
    "UAnalyze 登入頁網址",
    value="https://pro.uanalyze.com.tw/login-page",
)

wait_seconds = st.slider("點擊 Google 登入後等待秒數", 5, 30, 10)


def install_playwright_chromium():
    return subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=240,
    )


def click_google_login(page):
    # 方法 1：直接找文字
    try:
        page.get_by_text("Google 登入").click(timeout=5000)
        return "get_by_text Google 登入"
    except Exception:
        pass

    # 方法 2：掃描所有可見元素，找包含 Google 的按鈕或文字
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
            return "JS visible Google element"
    except Exception:
        pass

    return ""


if st.button("測試 Google 登入流程"):
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

            page = browser.new_page(
                viewport={"width": 1440, "height": 1000},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )

            response = page.goto(
                login_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(5000)

            before_title = page.title()
            before_url = page.url
            before_text = page.locator("body").inner_text(timeout=10000)
            before_screenshot = page.screenshot(full_page=True)

            click_method = click_google_login(page)

            if not click_method:
                after_title = page.title()
                after_url = page.url
                after_text = page.locator("body").inner_text(timeout=10000)
                after_screenshot = page.screenshot(full_page=True)
                browser.close()

                st.error("找不到 Google 登入按鈕，或無法點擊。")
                st.write("點擊方法：", "無")
            else:
                page.wait_for_timeout(wait_seconds * 1000)

                after_title = page.title()
                after_url = page.url

                try:
                    after_text = page.locator("body").inner_text(timeout=10000)
                except Exception:
                    after_text = ""

                after_screenshot = page.screenshot(full_page=True)
                browser.close()

                st.success("已點擊 Google 登入，並完成等待。")
                st.write("點擊方法：", click_method)

        status = response.status if response else "無 response"

        st.subheader("登入前狀態")
        st.write("HTTP 狀態碼：", status)
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
        zip_name = f"{company}_google_login_debug_{now}.zip"

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("before_body_text.txt", before_text)
            z.writestr("after_body_text.txt", after_text)
            z.writestr(
                "debug_info.txt",
                f"status={status}\n"
                f"before_title={before_title}\n"
                f"before_url={before_url}\n"
                f"click_method={click_method}\n"
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
