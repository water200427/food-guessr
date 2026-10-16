import os
import sys
import json
import time
import base64
import argparse
import urllib.request
import urllib.parse
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

def lens_search(image_path, query=None, hl="zh-TW", gl="TW", wait_sec=9, screenshot_out=None, text_out=None, port=PORT):
    abs_img = os.path.abspath(image_path)
    if not os.path.exists(abs_img):
        print(f"[!] 找不到圖片檔案: {abs_img}")
        return False

    if not launch_chrome_if_needed(port):
        return False

    with open(abs_img, "rb") as f:
        b64_img = base64.b64encode(f.read()).decode("ascii")

    navigate_in_place(f"https://www.google.com/?hl={hl}&gl={gl}", port=port, wait_sec=3)
    tabs = get_page_tabs(port)
    ws = websocket.create_connection(tabs[0]['webSocketDebuggerUrl'], timeout=20)

    js_open_lens = """
    (function() {
        const btns = document.querySelectorAll('[aria-label*="圖片"], [aria-label*="image"], [aria-label*="Image"], [aria-label*="鏡頭"], [aria-label*="Lens"], [aria-label*="Bild"], div[role="button"]');
        for (const b of btns) {
            const label = (b.getAttribute('aria-label') || b.getAttribute('title') || '').toLowerCase();
            if (label.includes('圖片') || label.includes('image') || label.includes('lens') || label.includes('鏡頭') || label.includes('bild')) {
                b.click();
                return 'clicked: ' + label;
            }
        }
        return 'not found';
    })()
    """
    cdp_send(ws, 10, "Runtime.evaluate", {"expression": js_open_lens})
    time.sleep(1.5)

    js_inject = f"""
    (function() {{
        const b64 = "{b64_img}";
        const byteCharacters = atob(b64);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {{
            byteNumbers[i] = byteCharacters.charCodeAt(i);
        }}
        const byteArray = new Uint8Array(byteNumbers);
        const file = new File([byteArray], "upload.jpg", {{type: "image/jpeg"}});
        const dt = new DataTransfer();
        dt.items.add(file);

        const fileInputs = document.querySelectorAll('input[type="file"]');
        if (fileInputs.length > 0) {{
            const input = fileInputs[fileInputs.length - 1];
            input.files = dt.files;
            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return 'injected into file input';
        }}
        return 'no file input found';
    }})()
    """
    res = cdp_send(ws, 11, "Runtime.evaluate", {"expression": js_inject})
    print(f"[*] Google Lens 圖片注入狀態: {res.get('result', {}).get('value')}")
    time.sleep(wait_sec)

    if query:
        url_res = cdp_send(ws, 12, "Runtime.evaluate", {"expression": "window.location.href"})
        base_url = url_res.get("result", {}).get("value", "")
        if "vsrid=" in base_url:
            q_url = base_url + "&q=" + urllib.parse.quote(query)
            print(f"[*] 附加多模態關鍵字搜尋: {query}")
            cdp_send(ws, 13, "Page.navigate", {"url": q_url})
            time.sleep(wait_sec - 2)

    if text_out:
        txt_res = cdp_send(ws, 14, "Runtime.evaluate", {"expression": "document.body.innerText"})
        body_text = txt_res.get("result", {}).get("value", "")
        with open(text_out, "w", encoding="utf-8") as f:
            f.write(body_text)
        print(f"[+] 頁面文字已儲存至: {text_out}")

    ws.close()
    if screenshot_out:
        capture_screenshot(screenshot_out, port=port)
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

    lens_p = sub.add_parser("lens", help="使用 Google Lens 進行以圖搜尋或圖文多模態搜尋")
    lens_p.add_argument("image", help="要上傳的本地圖片路徑")
    lens_p.add_argument("--query", "-q", help="選填：附加搜尋關鍵字")
    lens_p.add_argument("--hl", default="zh-TW", help="介面語言 (預設 zh-TW)")
    lens_p.add_argument("--gl", default="TW", help="地區代碼 (預設 TW)")
    lens_p.add_argument("--wait", type=int, default=9, help="等待秒數")
    lens_p.add_argument("--screenshot", "-s", help="選填：儲存結果截圖路徑")
    lens_p.add_argument("--text", "-t", help="選填：儲存結果純文字路徑")

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
    elif args.command == "lens":
        lens_search(
            args.image,
            query=args.query,
            hl=args.hl,
            gl=args.gl,
            wait_sec=args.wait,
            screenshot_out=args.screenshot,
            text_out=args.text
        )
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
