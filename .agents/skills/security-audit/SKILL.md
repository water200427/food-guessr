---
name: security-audit
description: >-
  執行程式碼推送前的資安審查與開源合規檢查。自動排查硬編碼 API Key/Token、
  本機使用者隱私路徑 (如 C:\Users\ 或 /home/)、過濾作業系統垃圾檔案，並確保具備開源基本配備。
---

# 程式碼資安與開源合規審查技能 (Security Audit Runbook)

當使用者即將推送程式碼至公開或私人遠端倉庫，或要求進行資安審查時，依序執行以下五道檢驗防線：

## 第一道：敏感資訊洩漏掃描 (Secrets & API Keys)
1. 執行 Git 追蹤檔案內容搜尋：
   ```bash
   git grep -i -E "(api_key|token|secret|password|bearer|auth|authorization)"
   ```
2. 驗證所有匹配結果：
   - 確保實際金鑰與 Token 絕未硬編碼在程式中。
   - 必須透過環境變數 (`os.getenv`) 或本機設定檔動態讀取。
   - 確認真實金鑰設定檔已在 `.gitignore` 中明確排除。

## 第二道：個人隱私與本機路徑排查 (Local Path & PII)
1. 搜尋硬編碼路徑與開發者使用者名稱：
   ```bash
   git grep -i -E "(c:\\\\users|/home/|localhost|127\.0\.0\.1)"
   ```
2. 檢查 Windows / Linux / macOS 絕對路徑：
   - 若發現 `C:\Users\username\...`，必須改用動態取得家目錄：
     `os.path.expanduser("~")` 或 `Path.home()`。
   - 確保程式碼具備跨平台通用性，且不洩漏本機使用者帳號。

## 第三道：專案雜訊與垃圾檔案 (Noise & Git Hygiene)
1. 檢查目前已被 Git 追蹤的檔案：
   ```bash
   git ls-files
   ```
2. 確認是否有以下應排除的垃圾：
   - Python 快取：`__pycache__/`, `*.pyc`, `*.pyo`
   - 作業系統雜訊：`.DS_Store`, `Thumbs.db`, `desktop.ini`
   - 編輯器暫存：`.idea/`, `.vscode/`, `*.swp`
   - 本地暫存與記錄檔：`*.tmp`, `*.log`, `scratch/`
3. 檢查 `.gitignore` 是否已包含上述模式，並確保範本檔（如 `.env.example`）不受阻擋：
   `!.env.example`

## 第四道：商業機密與未授權素材 (IP & Commercial Risk)
1. 檢查專案圖檔、字型、音視頻與第三方資源授權狀態。
2. 確保沒有包含未授權的受版權保護資產，或公司內部專利/機密商業邏輯。

## 第五道：開源基本配備健全度 (Open Source Baseline)
檢查專案根目錄是否具備以下 4 大標準開源元件：
1. **LICENSE**：標準開源授權條款（如 MIT, Apache-2.0）。
2. **README.md**：清晰的專案說明、安裝與啟動指引。
3. **依賴清單**：`requirements.txt` (Python) 或 `package.json` (Node)。
4. **環境變數範例**：`.env.example` 或 `config.json.example`，僅包含空值或佔位符說明。

## 報告與修復輸出規範
- 排查後產出包含「五大檢查點」的結構化審查報告。
- 若發現中高風險（如硬編碼路徑或金鑰），立即提供修改後的程式碼片段或執行就地修正。
