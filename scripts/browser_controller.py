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

def lens_search(image_path, query=None, hl="en", gl="us", wait_sec=8, screenshot_out=None, text_out=None, port=PORT):
    abs_img = os.path.abspath(image_path)
    if not os.path.exists(abs_img):
        print(f"[!] 找不到圖片檔案: {abs_img}")
        return False

    if not launch_chrome_if_needed(port):
        return False

    navigate_in_place(f"https://images.google.com/?hl={hl}&gl={gl}", port=port, wait_sec=3)
    tabs = get_page_tabs(port)
    ws = websocket.create_connection(tabs[0]['webSocketDebuggerUrl'], timeout=30)

    click_js = """
    (() => {
        const btn = document.querySelector('div[aria-label*="image"]') ||
                    document.querySelector('div[aria-label*="圖"]') ||
                    document.querySelector('.nDcEnd');
        if (btn) { btn.click(); return 'clicked lens button'; }
        return 'lens button not found';
    })()
    """
    r1 = cdp_send(ws, 10, "Runtime.evaluate", {"expression": click_js, "returnByValue": True})
    print(f"[*] 開啟 Lens 對話框: {r1.get('result', {}).get('result', {}).get('value')}")
    time.sleep(2)

    cdp_send(ws, 11, "DOM.enable")
    doc = cdp_send(ws, 12, "DOM.getDocument", {"depth": -1})
    root_id = doc['result']['root']['nodeId']
    node = cdp_send(ws, 13, "DOM.querySelector", {"nodeId": root_id, "selector": "input[type='file']"})
    node_id = node.get('result', {}).get('nodeId', 0)

    if node_id != 0:
        cdp_send(ws, 14, "DOM.setFileInputFiles", {"files": [abs_img], "nodeId": node_id})
        print(f"[*] 已上傳圖片至 Google Lens: {abs_img}")
        time.sleep(wait_sec)

        if query:
            print(f"[*] 附加多模態關鍵字搜尋: {query}")
            focus_js = """
            (() => {
                const el = document.querySelector('textarea[name="q"], input[name="q"], [role="combobox"]');
                if (el) {
                    el.focus();
                    el.value = '';
                    return true;
                }
                return false;
            })()
            """
            cdp_send(ws, 15, "Runtime.evaluate", {"expression": focus_js, "returnByValue": True})
            time.sleep(0.5)
            cdp_send(ws, 16, "Input.insertText", {"text": query})
            time.sleep(0.5)
            cdp_send(ws, 17, "Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 13, "key": "Enter", "code": "Enter"})
            cdp_send(ws, 18, "Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13, "key": "Enter", "code": "Enter"})
            time.sleep(wait_sec - 1)

        if text_out:
            txt_res = cdp_send(ws, 19, "Runtime.evaluate", {"expression": "document.body.innerText", "returnByValue": True})
            body_text = txt_res.get("result", {}).get("result", {}).get("value", "")
            with open(text_out, "w", encoding="utf-8") as f:
                f.write(body_text)
            print(f"[+] 頁面文字已儲存至: {text_out}")
    else:
        print("[!] 找不到 input[type='file'] 節點")

    ws.close()
    if screenshot_out:
        capture_screenshot(screenshot_out, port=port)
    return True

def get_maps_share_link(port=PORT):
    tabs = get_page_tabs(port)
    if not tabs:
        print("[!] 找不到分頁。")
        return None

    target_tab = None
    for t in tabs:
        if "google.com/maps" in t.get("url", ""):
            target_tab = t
            break
    if not target_tab:
        target_tab = tabs[0]

    ws = websocket.create_connection(target_tab['webSocketDebuggerUrl'], timeout=15)
    # 授權剪貼簿存取
    cdp_send(ws, 1, "Browser.grantPermissions", {"permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"]})

    # 點擊分享按鈕
    click_share_js = """
    (() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const shareBtn = btns.find(b => {
            const al = b.getAttribute('aria-label') || '';
            const text = b.innerText || '';
            const dv = b.getAttribute('data-value') || '';
            return al.includes('分享') || al.includes('Share') || text.includes('分享') || dv.includes('分享');
        });
        if (shareBtn) {
            shareBtn.click();
            return 'clicked_share';
        }
        return 'share_btn_not_found';
    })()
    """
    res1 = cdp_send(ws, 2, "Runtime.evaluate", {"expression": click_share_js, "returnByValue": True})
    status1 = res1.get("result", {}).get("result", {}).get("value")
    if status1 != 'clicked_share':
        # 如果已經在分享彈窗中，直接嘗試點 Copy
        pass
    time.sleep(1.5)

    # 點擊 Copy Link 按鈕
    click_copy_js = """
    (() => {
        const el = Array.from(document.querySelectorAll('div.r3L9Lb')).find(d => d.innerText.includes('Copy Link') || d.innerText.includes('複製連結'));
        if (el) {
            let target = el;
            while (target && target.tagName !== 'BUTTON' && !target.getAttribute('role')?.includes('button') && target.parentElement) {
                target = target.parentElement;
            }
            target.click();
            return 'clicked_copy';
        }
        return 'copy_btn_not_found';
    })()
    """
    res2 = cdp_send(ws, 3, "Runtime.evaluate", {"expression": click_copy_js, "returnByValue": True})
    time.sleep(1.0)

    # 讀取剪貼簿內容
    read_js = """
    (async () => {
        try {
            return await navigator.clipboard.readText();
        } catch(e) {
            return '';
        }
    })()
    """
    res3 = cdp_send(ws, 4, "Runtime.evaluate", {"expression": read_js, "awaitPromise": True, "returnByValue": True})
    url = res3.get("result", {}).get("result", {}).get("value", "")

    # 關閉分享彈出視窗
    close_js = """
    (() => {
        const closeBtn = document.querySelector('div[role="dialog"] button[aria-label="Close"], div[role="dialog"] button[aria-label="關閉"]');
        if (closeBtn) closeBtn.click();
    })()
    """
    cdp_send(ws, 5, "Runtime.evaluate", {"expression": close_js})
    ws.close()

    if url and ("maps.app.goo.gl" in url or "goo.gl/maps" in url):
        print(f"[+] 成功取得 Google Maps 官方短網址: {url}")
        return url
    else:
        print(f"[-] 未能取得短網址 (剪貼簿: {url})")
        return None

def main():
    parser = argparse.ArgumentParser(description="AI 瀏覽器控制器（嚴格遵守就地控制，絕不亂彈視窗）")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="檢查目前 Chrome 視窗狀態")
    sub.add_parser("share", help="在當前 Google Maps 商家頁面點擊分享並取得官方短網址 (maps.app.goo.gl)")

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
    elif args.command == "share":
        get_maps_share_link()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
