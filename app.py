import io
import zipfile
import subprocess
import sys
from datetime import datetime

import streamlit as st


st.set_page_config(page_title="UAnalyze Crawler App", layout="wide")

st.title("UAnalyze 產業資料爬蟲測試版")
st.caption("第一階段：測試手機可以產生 ZIP；第二階段：測試 Streamlit 雲端能不能啟動 Playwright 瀏覽器。")

company = st.text_input("請輸入公司代號與名稱", value="3030_德律")

sample_text = st.text_area(
    "測試內容",
    value="這裡之後會放 UAnalyze 爬下來的內容。",
    height=200,
)

st.divider()

st.subheader("1. 產生 ZIP 測試")

if st.button("產生 ZIP"):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{company}_{now}"

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{folder_name}/_ALL_CONTENT.md", sample_text)
        z.writestr(f"{folder_name}/近況發展.md", sample_text)

    zip_buffer.seek(0)

    st.success("ZIP 已產生，可以下載。")

    st.download_button(
        label="下載 ZIP",
        data=zip_buffer,
        file_name=f"{folder_name}.zip",
        mime="application/zip",
    )

st.divider()

st.subheader("2. Playwright 雲端瀏覽器測試")

test_url = st.text_input("測試網址", value="https://example.com")

if st.button("測試 Playwright 是否能啟動"):
    st.info("開始安裝 / 檢查 Playwright Chromium，這一步可能需要 1～3 分鐘。")

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
                ],
            )
            page = browser.new_page()
            page.goto(test_url, wait_until="domcontentloaded", timeout=30000)

            title = page.title()
            body_text = page.locator("body").inner_text(timeout=10000)

            browser.close()

        st.success("Playwright 啟動成功。")
        st.write("頁面標題：", title)
        st.text_area("抓到的頁面文字", body_text, height=250)

    except Exception as e:
        st.error("Playwright 啟動或抓取失敗。")
        st.exception(e)
