import json
import urllib.request
import sys

def test_connection(port=9222):
    url = f"http://127.0.0.1:{port}/json/version"
    print(f"正在測試連線到 AI 專用 Chrome (連接埠: {port})...")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print("連線成功！取得 Chrome 資訊：")
            print(f"  - 瀏覽器版本: {data.get('Browser')}")
            print(f"  - 通訊協定版本: {data.get('Protocol-Version')}")
            print(f"  - 使用者代理: {data.get('User-Agent')}")
            print(f"  - WebSocket 網址: {data.get('webSocketDebuggerUrl')}")
            return True
    except Exception as e:
        print(f"連線失敗: {e}")
        print("提示：請先執行 scripts/start_ai_chrome.ps1 啟動 AI 專用 Chrome。")
        return False

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9222
    success = test_connection(port)
    sys.exit(0 if success else 1)
