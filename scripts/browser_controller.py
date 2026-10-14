import os
import sys
import json
import time
import base64
import argparse
import urllib.request
import websocket
import subprocess

PORT = 9222

def check_connection(port=PORT):
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return True, data
    except Exception as e:
        return False, str(e)

def get_page_tabs(port=PORT):
    try:
        url = f"http://127.0.0.1:{port}/json/list"
        with urllib.request.urlopen(url, timeout=2) as resp:
            tabs = json.loads(resp.read().decode('utf-8'))
            return [t for t in tabs if t.get('type') == 'page']
    except Exception as e:
        return []

def launch_chrome_if_needed(port=PORT):
    is_running, _ = check_connection(port)
    if is_running:
        return True

    print("[*] 偵測到目前尚未開啟 AI Chrome，正在嘗試啟動...")
    lnk_path = os.path.expandvars(r"%USERPROFILE%\Desktop\Chrome (AI 專用).lnk")
    if os.path.exists(lnk_path):
        subprocess.run(["powershell", "-Command", f'Invoke-Item "{lnk_path}"'], capture_output=True)
    else:
        chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        profile_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome_AI")
        cmd = [
            chrome_exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--remote-allow-origins=*",
            "https://www.google.com"
        ]
        subprocess.Popen(cmd)

    for _ in range(10):
        time.sleep(0.5)
        is_running, _ = check_connection(port)
        if is_running:
            print("[+] Chrome 啟動成功！")
            return True

    print("[!] 無法啟動 Chrome，請手動確認桌面捷徑。")
    return False

def cdp_send(ws, cmd_id, method, params=None):
    payload = {"id": cmd_id, "method": method, "params": params or {}}
    ws.send(json.dumps(payload))
    while True:
        res = json.loads(ws.recv())
        if res.get("id") == cmd_id:
            return res

def navigate_in_place(url, port=PORT, wait_sec=4):
    if not launch_chrome_if_needed(port):
        return False

    tabs = get_page_tabs(port)
    if not tabs:
        print("[!] 找不到可用的網頁分頁。")
        return False

    target_tab = tabs[0]
    tab_id = target_tab['id']
    ws_url = target_tab['webSocketDebuggerUrl']
    print(f"[*] 鎖定現有視窗/分頁 (ID: {tab_id[:8]}..., 標題: {target_tab.get('title')})")
    print(f"[*] 就地導航至: {url}（絕不產生新視窗）")

    ws = websocket.create_connection(ws_url, timeout=15)
    cdp_send(ws, 1, "Page.enable")
    cdp_send(ws, 2, "Page.navigate", {"url": url})
    time.sleep(wait_sec)

    title_res = cdp_send(ws, 3, "Runtime.evaluate", {"expression": "document.title"})
    page_title = title_res.get("result", {}).get("value", "")
    print(f"[+] 導航完成！目前頁面標題: {page_title}")
    ws.close()
    return True

def capture_screenshot(output_path, port=PORT):
    tabs = get_page_tabs(port)
    if not tabs:
        print("[!] 找不到分頁進行截圖。")
        return False

    target_tab = tabs[0]
    ws = websocket.create_connection(target_tab['webSocketDebuggerUrl'], timeout=15)
    cdp_send(ws, 1, "Page.enable")
    shot_res = cdp_send(ws, 2, "Page.captureScreenshot", {"format": "jpeg", "quality": 85})
    b64_data = shot_res.get("result", {}).get("data")
    if b64_data:
        with open(output_path, "wb") as f:
            f.write(base64.b64decode(b64_data))
        print(f"[+] 截圖已儲存至: {output_path}")
    ws.close()
    return True

def main():
    parser = argparse.ArgumentParser(description="AI 瀏覽器控制器（嚴格遵守就地控制，絕不亂彈視窗）")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="檢查目前 Chrome 視窗狀態")

    nav_p = sub.add_parser("goto", help="在現有視窗直接跳轉網址")
    nav_p.add_argument("url", help="目標網址")
    nav_p.add_argument("--wait", type=int, default=4, help="等待載入秒數")

    shot_p = sub.add_parser("screenshot", help="截取現有視窗畫面")
    shot_p.add_argument("output", help="儲存路徑")

    args = parser.parse_args()

    if args.command == "status":
        running, info = check_connection()
        if running:
            print("[+] Chrome 正常運作中 (Port 9222)")
            print(f"    核心版本: {info.get('Browser')}")
            tabs = get_page_tabs()
            print(f"    目前視窗內共有 {len(tabs)} 個網頁分頁:")
            for i, t in enumerate(tabs):
                print(f"      [{i}] {t.get('title')} ({t.get('url')[:60]}...)")
        else:
            print(f"[-] 未偵測到 Chrome 連線: {info}")
    elif args.command == "goto":
        navigate_in_place(args.url, wait_sec=args.wait)
    elif args.command == "screenshot":
        capture_screenshot(args.output)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
