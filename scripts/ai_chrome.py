import os
import sys
import time
import json
import argparse
import subprocess
import urllib.request

DEFAULT_PORT = 9222
DEFAULT_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

def get_project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_profile_dir():
    profile = os.path.join(get_project_root(), ".ai_chrome_profile")
    os.makedirs(profile, exist_ok=True)
    return profile

def find_chrome():
    for p in DEFAULT_CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None

def check_status(port=DEFAULT_PORT):
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return True, data
    except Exception as e:
        return False, str(e)

def start_chrome(port=DEFAULT_PORT, headless=False):
    is_running, info = check_status(port)
    if is_running:
        print(f"[*] AI 專用 Chrome 已經在連接埠 {port} 上運行中。")
        print(f"    瀏覽器: {info.get('Browser')}")
        return True

    chrome = find_chrome()
    if not chrome:
        print("[!] 找不到 Chrome 執行檔，請確認系統已安裝 Google Chrome。")
        return False

    profile = get_profile_dir()
    cmd = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--password-store=basic"
    ]

    if headless:
        cmd.extend(["--headless=new", "--disable-gpu"])

    print(f"[*] 正在啟動 AI 專用獨立 Chrome...")
    print(f"    連接埠: {port}")
    print(f"    獨立設定檔目錄: {profile}")
    print(f"    模式: {'背景無頭模式 (Headless)' if headless else '獨立視窗模式'}")

    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(15):
        time.sleep(0.5)
        is_running, info = check_status(port)
        if is_running:
            print(f"[+] AI 專用 Chrome 啟動成功！(Port: {port})")
            print(f"    版本: {info.get('Browser')}")
            print(f"    WebSocket: {info.get('webSocketDebuggerUrl')}")
            return True

    print("[!] 啟動逾時，請檢查端口佔用情況。")
    return False

def stop_chrome(port=DEFAULT_PORT):
    is_running, info = check_status(port)
    if not is_running:
        print(f"[*] 連接埠 {port} 上沒有執行中的 AI 專用 Chrome。")
        return True

    # 查詢佔用該端口的 PID 並終止
    try:
        import psutil
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == 'LISTEN':
                pid = conn.pid
                p = psutil.Process(pid)
                print(f"[*] 正在關閉 AI Chrome 處理程序 (PID: {pid})...")
                p.terminate()
                p.wait(timeout=3)
                print("[+] AI 專用 Chrome 已安全關閉。您的日常 Chrome 未受影響。")
                return True
    except ImportError:
        # 使用 Windows 內建 netstat & taskkill
        res = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        target_pid = None
        for line in res.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.strip().split()
                target_pid = parts[-1]
                break
        if target_pid:
            print(f"[*] 正在關閉 AI Chrome 處理程序 (PID: {target_pid})...")
            subprocess.run(["taskkill", "/PID", target_pid, "/F", "/T"], capture_output=True)
            print("[+] AI 專用 Chrome 已安全關閉。您的日常 Chrome 未受影響。")
            return True
        else:
            print("[!] 找不到對應的 PID。")
            return False

def main():
    parser = argparse.ArgumentParser(description="AI 專用 Chrome 管理工具")
    subparsers = parser.add_subparsers(dest="command", help="子指令: start, stop, status")

    start_p = subparsers.add_parser("start", help="啟動 AI 專用 Chrome")
    start_p.add_argument("--port", type=int, default=DEFAULT_PORT, help="除錯連接埠 (預設 9222)")
    start_p.add_argument("--headless", action="store_true", help="以背景無頭模式執行 (不跳出視窗)")

    stop_p = subparsers.add_parser("stop", help="安全停止 AI 專用 Chrome")
    stop_p.add_argument("--port", type=int, default=DEFAULT_PORT, help="除錯連接埠 (預設 9222)")

    status_p = subparsers.add_parser("status", help="檢查 AI 專用 Chrome 狀態")
    status_p.add_argument("--port", type=int, default=DEFAULT_PORT, help="除錯連接埠 (預設 9222)")

    args = parser.parse_args()

    if args.command == "start":
        start_chrome(port=args.port, headless=args.headless)
    elif args.command == "stop":
        stop_chrome(port=args.port)
    elif args.command == "status":
        running, info = check_status(port=args.port)
        if running:
            print(f"[+] AI 專用 Chrome 正在運行中 (Port: {args.port})")
            print(f"    版本: {info.get('Browser')}")
        else:
            print(f"[-] AI 專用 Chrome 未在運行 (Port: {args.port})")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
