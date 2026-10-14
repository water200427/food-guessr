# AI 專用 Chrome 獨立環境說明

本目錄提供專門為 AI（如影像辨識、Google Lens、動態網頁查證）設計的獨立 Chrome 運行環境。

## 🎯 解決的問題
- **完全隔離**：使用獨立的 Profile 目錄（`.ai_chrome_profile/`），**完全不使用**您日常登入的 Chrome 設定檔。
- **不干擾操作**：不會在您常用的瀏覽器跳出「受自動化測試軟體控制」提示條，也不會搶佔您的工作分頁或瀏覽紀錄。
- **安全關閉**：停止腳本僅透過連接埠（Port 9222）精準終止 AI 專用處理程序，絕對不誤關您的日常 Chrome。
- **免除手動設定**：不需要手動在主要瀏覽器開關 Allow remote debugging。

## 🚀 使用方式

你可以選擇使用 **Python** 或 **PowerShell** 腳本：

### 方法 A：使用 Python 工具（推薦，支援跨平台）
```powershell
# 1. 以背景無頭模式啟動（完全靜默、不跳視窗、不干擾日常操作）
python ./scripts/ai_chrome.py start --headless

# 或以獨立視窗模式啟動（若想親眼看網頁加載過程）
python ./scripts/ai_chrome.py start

# 2. 檢查連線狀態
python ./scripts/ai_chrome.py status

# 3. 關閉 AI 專用 Chrome（僅精準關閉 AI 實例，不影響日常 Chrome）
python ./scripts/ai_chrome.py stop
```

### 方法 B：使用 PowerShell 腳本
```powershell
# 背景無頭模式啟動
powershell -ExecutionPolicy Bypass -File ./scripts/start_ai_chrome.ps1 -Headless

# 測試連線
python ./scripts/test_ai_chrome.py

# 安全關閉
powershell -ExecutionPolicy Bypass -File ./scripts/stop_ai_chrome.ps1
```

## ⚙️ 核心設定說明
- **資料目錄**：`../.ai_chrome_profile`（已加入 `.gitignore`，不佔用 git 空間）
- **遠端除錯埠**：`9222`
- **反自動化標記**：預設附帶 `--disable-blink-features=AutomationControlled`，可正常載入 Google Lens 等動態驗證網頁。
