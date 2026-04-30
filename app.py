import io
import zipfile
from datetime import datetime

import streamlit as st


st.set_page_config(page_title="UAnalyze Crawler App", layout="wide")

st.title("UAnalyze 產業資料爬蟲測試版")

company = st.text_input("請輸入公司代號與名稱", value="3030_德律")

sample_text = st.text_area(
    "測試內容",
    value="這裡之後會放 UAnalyze 爬下來的內容。",
    height=200,
)

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
