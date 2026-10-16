# 🐾 「這哪家」Discord 美食偵探機器人 (Food Detective Cat)

專為 Discord 社群設計的美食照片肉搜與猜謎機器人。群友只需上傳食物照片並標註 `@這哪家`，機器人便會出動比對影像特徵、搜尋 Google Lens，並透過本地 Antigravity 深度物證分析，精準找出餐廳名稱與 Google Maps 導航連結！

---

## 🌟 核心特色

1. **直覺零負擔觸發**：
   - **發新照片**：發布照片時在內文提及 `@這哪家`。
   - **回覆歷史照片**：直接引用歷史訊息的照片並提及 `@這哪家`。
2. **Antigravity 全自動獨立對話接軌**：
   - 當照片特徵複雜時，機器人會自動於 `案件/` 建檔。
   - 調用本地 Antigravity 底層 API（`agentapi new-conversation --model=flash`），自動在 IDE 專案彈出全新獨立對話。
   - **0 歷史 Token 負擔**，由 Gemini Flash 極速完成深度物證排查並自動同步結案回傳。
3. **群友搶答與競猜互動**：
   - 群友可在討論串或頻道猜店名，若比機器人更早猜中，機器人會為該訊息加上 **`🎯`** 表情認證。
   - 3 分鐘內命中會發送慶祝回覆，超過 3 分鐘則僅貼表情不打擾聊天。
4. **極簡狀態 Emoji（同一時間永遠單一表情）**：
   - `🔍` **搜尋中**：正在秒查與檢索基礎特徵。
   - `🕵️` **深度調查中**：已進入 Antigravity 微型物證排查。
   - `✅` **成功破案**：發送確定店名與 Google Maps 連結。
   - `❓` **優雅停損**：線索不足或達 30 分鐘停損原則。

---

## 📁 模組結構

```text
discord_bot/
├── bot.py                     # Discord 機器人主程式 (事件監聽、表情控制與結案監控)
├── config.py                  # 設定檔載入模組 (支援 config.json 與環境變數)
├── config.json.example        # 設定檔範本
├── assets/                    # 機器人頭像與視覺素材
├── services/
│   ├── food_detector.py       # 食物圖片偵測與店名提及過濾器 (Gemini 3.5 Flash Lite)
│   ├── restaurant_identifier.py # Google Lens 多模態比對引擎
│   ├── case_manager.py        # 案件自動建檔與 30 分鐘停損管理
│   └── tracker.py             # 訊息會話狀態追蹤與逾時排程
└── tests/
    └── test_discord_flow.py   # 本地單元與整合測試
```

---

## 🚀 安裝與啟動

### 1. 安裝 Python 依賴
```bash
pip install -r ../requirements.txt
```
*(或直接 `pip install discord.py`)*

### 2. 設定憑證與金鑰
本模組支援 **設定檔（`config.json`）** 或 **環境變數（`.env`）** 雙軌配置：

- **方式 A：使用 `config.json`（推薦）**：
  複製範本檔：
  ```bash
  cp config.json.example config.json
  ```
  填入內容：
  ```json
  {
    "bot_token": "YOUR_DISCORD_BOT_TOKEN_HERE",
    "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
    "trigger_timeout_seconds": 180,
    "reply_footer": "(此為貓貓自動偵測回覆)"
  }
  ```
  > [!NOTE]
  > `gemini_api_key` 為選填。填入後可啟用 Google Gemini 3.5 Flash Lite 的進階食物判讀與對話店名意圖分析。

- **方式 B：使用環境變數**：
  ```bash
  export DISCORD_BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN_HERE"
  export GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"
  ```

### 3. 啟動機器人
```bash
python bot.py
```
*(在根目錄執行請輸入：`python discord_bot/bot.py`)*

---

## 🔒 資安與隱私防護

- `discord_bot/config.json` 與所有包含私密 Token 的檔案已預設列入 `.gitignore`，請勿手動解除忽略。
- 程式內路徑全面使用 `os.path.expanduser("~")` 動態獲取家目錄，跨平台通用且不洩漏個人主機資訊。
