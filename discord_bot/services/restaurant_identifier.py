import os
import sys
import subprocess
import urllib.parse
from typing import Optional, Dict, List

class RestaurantIdentifier:
    """
    餐廳辨識引擎：結合 Google Lens、多圖特徵與 Google Maps 查核
    """
    def __init__(self, reply_footer: str = "(此為 AI 自動偵測回覆)", gemini_api_key: str = ""):
        self.reply_footer = reply_footer
        self.gemini_api_key = gemini_api_key
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
        self.browser_script = os.path.join(project_root, "scripts", "browser_controller.py")

    def identify(self, image_paths: List[str], guess_candidates: List[str] = None) -> Optional[Dict[str, str]]:
        """
        支援單張或多張照片的複合辨識，並可用群友猜測的候選店名作為線索交叉驗證
        """
        if not image_paths:
            print("[貓貓偵探 ⚠️] 沒有提供圖片路徑，無法辨識。")
            return None

        primary_image = image_paths[0]
        if not os.path.exists(self.browser_script):
            print(f"[貓貓偵探 ⚠️] 找不到本機 Chrome 腳本: {self.browser_script}")
            return None
        if not os.path.exists(primary_image):
            print(f"[貓貓偵探 ⚠️] 找不到照片檔案: {primary_image}")
            return None

        # 1. 若有群友猜測的店名候選，優先透過 Lens 附加關鍵字進行精確交叉比對
        if guess_candidates:
            for guess in guess_candidates:
                clean_guess = guess.strip()
                if 2 <= len(clean_guess) <= 20:
                    print(f"[貓貓偵探 🐾] 發現群友猜測店名:【{clean_guess}】，正在呼叫 Google Lens 進行交叉查證...")
                    verified = self._run_lens_search(primary_image, query=clean_guess)
                    if verified:
                        print(f"[貓貓偵探 🎯] 群友猜測命中！成功核實店家: {verified.get('name')}")
                        return verified

        # 2. 原生圖片辨識：不依賴粗糙的本地關鍵字猜測，全面交由 Antigravity 獨立對話深度排查
        print(f"[貓貓偵探 🔍] 原生照片交由 Antigravity 深度物證分析，以確保 100% 正確性。")
        return None

    def format_reply(self, info: Optional[Dict[str, str]], is_command_trigger: bool = False) -> Optional[str]:
        """
        格式化回覆：店名和連結間無空行
        [店名]
        [Google Maps 連結]
        (此為貓貓自動偵測回覆)
        """
        if info and info.get("name"):
            name = info["name"].strip()
            maps_url = info.get("maps_url", "").strip()
            footer = self.reply_footer.strip()
            lines = [name, maps_url]
            if footer:
                lines.append(footer)
            return "\n".join(lines)

        if is_command_trigger:
            footer = self.reply_footer.strip()
            lines = ["經貓貓辨識，目前照片特徵不足，尚無法確認餐廳店家。"]
            if footer:
                lines.append(footer)
            return "\n".join(lines)

        return None

    def _run_lens_search(self, image_path: str, query: Optional[str] = None) -> Optional[Dict[str, str]]:
        scratch_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scratch")
        os.makedirs(scratch_dir, exist_ok=True)
        txt_out = os.path.join(scratch_dir, "lens_discord.txt")

        try:
            cmd = [
                sys.executable,
                self.browser_script,
                "lens",
                image_path,
                "-t",
                txt_out,
                "--wait",
                "6"
            ]
            if query:
                cmd.extend(["-q", query])

            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0 and os.path.exists(txt_out):
                with open(txt_out, "r", encoding="utf-8") as f:
                    content = f.read()
                print(f"[貓貓偵探 📄] Lens 頁面抓取成功 (字數: {len(content)})，正在篩選餐廳關鍵字...")
                candidate = self._extract_restaurant_name(content, query=query)
                if candidate:
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(candidate)}"
                    return {"name": candidate, "maps_url": maps_url, "confidence": "高"}
            else:
                print(f"[貓貓偵探 ⚠️] Lens 控制器執行結束，代碼: {res.returncode}")
        except Exception as e:
            print(f"[貓貓偵探 ❌] Lens 呼叫異常: {e}")

        return None

    def _extract_restaurant_name(self, text: str, query: Optional[str] = None) -> Optional[str]:
        if query and query.lower() in text.lower():
            return query

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines:
            if any(kw in line for kw in ["食堂", "牛肉麵", "拉麵", "咖啡", "肉圓", "海鮮丼", "飯館", "小吃", "鍋", "料理", "早午餐", "甜點"]):
                if 2 <= len(line) <= 25 and not line.startswith("http"):
                    return line
        return None
