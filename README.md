# UAnalyze 產業情報小助理爬蟲 - longrun enterfix runtime install

這版修正重點：

1. requirements.txt 只保留 streamlit，避免 Streamlit Cloud 在建置階段因 playwright 安裝失敗而整個 App 起不來。
2. Playwright 改成 App 內按下開始後才自動安裝／檢查。
3. 股票代號欄位只需要輸入數字，例如 3030。
4. 切換股票後會檢查目前頁面股票代號，避免又爬到預設 1101。

檔案：
- app.py
- requirements.txt
- packages.txt
- README.md
- .streamlit/config.toml

上傳方式：把這些檔案覆蓋到 GitHub repo 根目錄後 Commit，再到 Streamlit Manage app 重新 Reboot / Deploy。

若仍出現套件安裝問題，請在 Streamlit app settings / Advanced settings 把 Python version 改成 3.12 或 3.11 後重啟。
