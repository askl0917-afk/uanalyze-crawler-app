# UAnalyze 產業情報小助理爬蟲

## 本版重點

- 股票輸入欄位只需要股票代號，例如 `3030`
- 如果你輸入 `3030_德律`，程式會自動轉成 `3030`
- 爬蟲會先切換股票，再檢查頁面實際股票代號
- 如果頁面仍停在 `1101 台泥`，預設會停止，避免抓錯公司
- 支援長等待時間，不需要分批爬
- 結果支援一鍵複製、下載 ZIP

## Streamlit Cloud 部署

上傳 / 覆蓋以下檔案：

- app.py
- requirements.txt
- packages.txt
- README.md

`.streamlit/config.toml` 是外觀設定，手機可能看不到隱藏資料夾，不影響核心爬蟲。

## 使用方式

1. 打開 Streamlit app
2. 輸入 UAnalyze Email / 密碼
3. 股票代號輸入 `3030`
4. 選擇要爬的欄位
5. 點擊「開始爬取產業情報欄位」
6. 成功後按「一鍵複製」或下載 ZIP

## 注意

如果切換股票失敗，App 會停止，這是刻意設計，避免把錯的公司資料存成目標公司。


## v3 修正

如果 Streamlit Cloud 沒有正確讀到 requirements.txt，畫面會出現：
`No module named playwright`

本版在 app.py 內加入保險機制，啟動時會自動補裝 playwright。
但 GitHub 根目錄仍建議保留正確檔名：`requirements.txt`。
