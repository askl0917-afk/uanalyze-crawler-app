import io
import zipfile
import subprocess
import sys
from datetime import datetime

import streamlit as st


st.set_page_config(page_title="UAnalyze Crawler App", layout="wide")

st.title("UAnalyze 雲端瀏覽器診斷版")
st.caption("先確認 Streamlit 雲端瀏覽器實際看到 UAnalyze 的什麼畫面。")

company = st.text_input("請輸入公司代號與名稱", value="3030_德律")

test_url = st.text_input(
    "測試網址",
    value="https://pro.uanalyze.com.tw/login-page",
)

wait_seconds = st.slider("進入頁面後等待秒數", 3, 20, 8)

if st.button("開始診斷 UAnalyze 頁面"):
    st.info("開始檢查 Playwright Chromium，這一步可能需要 1～3 分鐘。")

    install = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=240,
    )

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
                test_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(wait_seconds * 1000)

            title = page.title()
            final_url = page.url

            try:
                body_text = page.locator("body").inner_text(timeout=10000)
            except Exception:
                body_text = ""

            html = page.content()
            screenshot_bytes = page.screenshot(full_page=True)

            browser.close()

        status = response.status if response else "無 response"

        st.success("診斷完成。")
        st.write("HTTP 狀態碼：", status)
        st.write("頁面標題：", title)
        st.write("最後網址：", final_url)

        st.subheader("雲端瀏覽器截圖")
        st.image(screenshot_bytes)

        st.subheader("抓到的頁面文字")
        st.text_area("body text", body_text, height=250)

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"{company}_uanalyze_debug_{now}.zip"

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("debug_body_text.txt", body_text)
            z.writestr("debug_page.html", html)
            z.writestr("debug_info.txt", f"status={status}\ntitle={title}\nurl={final_url}\n")
            z.writestr("debug_screenshot.png", screenshot_bytes)

        zip_buffer.seek(0)

        st.download_button(
            label="下載診斷 ZIP",
            data=zip_buffer,
            file_name=zip_name,
            mime="application/zip",
        )

    except Exception as e:
        st.error("診斷失敗。")
        st.exception(e)
