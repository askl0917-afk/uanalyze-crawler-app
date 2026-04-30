# UAnalyze Crawler App - Long Run Mode

這是 UAnalyze 產業情報小助理 / 虎八速覽的 Streamlit 長時間爬蟲版。

## 檔案

- `app.py`：主程式
- `requirements.txt`：Python 套件
- `packages.txt`：Streamlit Cloud Linux 系統套件
- `.streamlit/config.toml`：Streamlit 基本設定

## 更新方式

1. 解壓縮 ZIP。
2. 到 GitHub repo：`askl0917-afk/uanalyze-crawler-app`。
3. 上傳 / 覆蓋：
   - `app.py`
   - `requirements.txt`
   - `packages.txt`
   - `README.md`
   - `.streamlit/config.toml`
4. Commit changes。
5. 回 Streamlit App，Manage app → Reboot / Deploy。

## 使用建議

- 手機長時間爬取時，不要切 App、不要鎖螢幕。
- 不建議勾選「保存每個欄位截圖」，會變慢且耗資源。
- 若畫面中途斷線，重新整理後可在「最近完成 / 暫存結果」下載已寫入的結果。


## Enter 修正版

- 股票欄位只輸入數字，例如 3030。
- 切換股票時會輸入股票代號後直接按 Enter。
- 若頁面仍停在其他股票，例如 1101，App 會停止爬蟲並提供診斷 ZIP，避免爬錯公司。
- 若 Streamlit 沒吃到 requirements.txt，App 會嘗試在啟動時自動 pip install playwright。
