import os
import time
import json
import base64
import urllib.request
from typing import Tuple

class FoodDetector:
    """
    食物圖片判讀與對話店名提及分析器
    """
    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def is_food_image(self, image_path: str) -> Tuple[bool, str]:
        """
        判斷單張圖片是否為食物、飲料、餐廳料理
        """
        if not os.path.exists(image_path):
            return False, "檔案不存在"

        if self.api_key:
            try:
                return self._detect_with_gemini(image_path)
            except Exception as e:
                print(f"[貓貓偵探 🐟] 遠端視覺服務暫時忙碌 ({e})，啟動防呆機制，直接放行進入破案流程！")

        # 預設放行
        return True, "疑似餐飲照片 (啟動預設放行機制)"

    def _detect_with_gemini(self, image_path: str) -> Tuple[bool, str]:
        with open(image_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            "請判斷這張圖片是否主要拍攝的是食物、飲料、餐點或餐廳料理？"
            "請只回傳 JSON 格式：{\"is_food\": true/false, \"reason\": \"一句話理由\"}"
        )

        # 優先使用輕量且穩定不塞車的 3.5-flash-lite，後續備援 3.8-flash 與 flash-latest
        models = ["gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.8-flash"]
        last_err = None

        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_img
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "response_mime_type": "application/json",
                    "temperature": 0.1
                }
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )

            # 最多重試 2 次
            for attempt in range(2):
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        text = data["candidates"][0]["content"]["parts"][0]["text"]
                        res = json.loads(text)
                        return bool(res.get("is_food", False)), res.get("reason", "")
                except Exception as e:
                    last_err = e
                    time.sleep(1)

        raise last_err

    def check_mention_restaurant(self, text: str) -> bool:
        """
        判斷文字訊息是否提及店家名稱或在解答餐廳
        """
        if not text.strip():
            return False

        if self.api_key:
            try:
                return self._check_mention_with_gemini(text)
            except Exception as e:
                print(f"[貓貓偵探 ⚠️] Gemini 判讀店名提及異常 ({e})，使用關鍵字備用策略。")

        # 啟發式關鍵字比對
        keywords = ["這家是", "是在", "店名是", "店名叫", "就是那家", "叫作", "叫做", "在台南的", "在台北的", "在桃園的", "好吃", "那間", "拉麵", "牛肉麵"]
        return any(kw in text for kw in keywords)

    def _check_mention_with_gemini(self, text: str) -> bool:
        prompt = (
            f"群組中有人剛傳了食物照片。請判斷以下這段對話文字是否在解答、提及或討論該餐廳的「店家名稱」或「具體哪一家店」？\n"
            f"對話文字：「{text}」\n"
            f"若該句子包含店名、或者在回答店名（例如：這家是金峰、在阿堂鹹粥、是一蘭拉麵），請回傳 true；若只是普通閒聊（例如：看起來好好吃、肚子餓了、在哪裡？），請回傳 false。\n"
            f"請只回傳 JSON 格式：{{\"mentioned\": true/false}}"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res_text = data["candidates"][0]["content"]["parts"][0]["text"]
            res = json.loads(res_text)
            return bool(res.get("mentioned", False))
