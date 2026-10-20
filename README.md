# 台股智慧選股｜Streamlit Community Cloud 版

本專案包含 `app.py`、`requirements.txt` 及 Streamlit 設定，可部署到 Streamlit Community Cloud。

## 重要提醒
- 這是研究原型，不構成投資建議。評分規則、財報欄位及新聞題材分類仍需持續驗證。
- 免費行情／FinMind API 可能限流、延遲或調整格式。雲端部署成功不代表每次資料源都必然成功。
- 請勿把 API Token、密碼或任何私密金鑰提交到 GitHub。程式目前提供側邊欄選填 FinMind Token。
- Streamlit Community Cloud 免費服務可能因閒置而休眠，首次喚醒需等待。
- 這個版本支援把網址加入手機主畫面作為快捷入口；它不是完整離線型 PWA，因 Streamlit Community Cloud 不會自動替應用程式設定標準 PWA manifest／service worker。

## 本機測試
```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```
瀏覽器開啟 `http://localhost:8501`。

## 部署到 Streamlit Community Cloud
1. 將本資料夾內所有檔案上傳到 GitHub repository 的根目錄，確保 `app.py` 和 `requirements.txt` 在根目錄，`.streamlit/config.toml` 也要保留。
2. 到 https://share.streamlit.io/ 使用 GitHub 帳號登入。
3. 選 **Create app**，選擇 repository、branch（通常 `main`）、Main file path `app.py`。
4. 在 Advanced settings 選 Python 3.12（若可選），部署後查看 logs。
5. 等待部署完成，複製 `https://你的子網域.streamlit.app` 網址並用無痕視窗測試。
6. 之後更新程式只要把變更推送到 GitHub，Community Cloud 通常會自動重新部署。

## 手機加入主畫面（網址快捷入口）
部署成功後，先在手機瀏覽器開啟 Streamlit app URL。

- **Android / Chrome：** 右上角 ⋮ →「新增至主畫面」或「安裝應用程式」（選項依瀏覽器版本而異）。
- **iPhone / Safari：** 分享 →「加入主畫面」；若有「以網頁 App 開啟」選項可開啟後加入。

此方式會建立主畫面圖示，點擊後仍需網路連線；它不會讓選股資料離線運作，也不等同於完整原生 App。

## 若要真正的 PWA
完整 PWA 通常需要由同源網站正確提供 web app manifest、圖示、service worker 與 HTTPS。Streamlit 的一般 app UI 無法只靠在 GitHub 放一個 `manifest.json` 就保證完成；Streamlit 靜態檔案服務也會把檔案放在 `/app/static/` 路徑，而不是網站根目錄。若一定要符合完整 PWA 安裝條件，建議另建一個靜態 PWA 外殼（例如 Cloudflare Pages）並搭配可控的同源反向代理／前端架構；這比單純 Community Cloud 多一個部署層。
