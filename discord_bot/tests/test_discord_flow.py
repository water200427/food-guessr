import os
import sys
import asyncio
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.tracker import DiscordMessageTracker, DiscordFoodSession
from services.restaurant_identifier import RestaurantIdentifier
from services.food_detector import FoodDetector

class DummyMessage:
    def __init__(self, msg_id=1001, channel_id=2001):
        self.id = msg_id
        self.channel_id = channel_id
        self.replies = []

    async def reply(self, content, mention_author=False):
        self.replies.append(content)

class TestDiscordBotLogic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.identifier = RestaurantIdentifier(reply_footer="(此為 AI 自動偵測回覆)")

    def test_reply_formatting_found(self):
        """測試找到餐廳時的回覆格式"""
        info = {
            "name": "一蘭拉麵 台灣台北本店",
            "maps_url": "https://www.google.com/maps/search/?api=1&query=%E4%B8%80%E8%98%AD%E6%8B%89%E9%BA%B5"
        }
        res = self.identifier.format_reply(info, is_command_trigger=False)
        lines = res.split("\n")
        self.assertEqual(lines[0], "一蘭拉麵 台灣台北本店")
        self.assertEqual(lines[1], "https://www.google.com/maps/search/?api=1&query=%E4%B8%80%E8%98%AD%E6%8B%89%E9%BA%B5")
        self.assertEqual(lines[2], "(此為 AI 自動偵測回覆)")

    def test_reply_formatting_not_found_command(self):
        """測試指令觸發但找不到餐廳時的回覆"""
        res = self.identifier.format_reply(None, is_command_trigger=True)
        self.assertIn("經貓貓辨識，目前照片特徵不足", res)
        self.assertIn("(此為 AI 自動偵測回覆)", res)

    def test_reply_formatting_not_found_timeout(self):
        """測試 3 分鐘逾時但找不到時保持沈默 (回傳 None)"""
        res = self.identifier.format_reply(None, is_command_trigger=False)
        self.assertIsNone(res)

    async def test_immediate_command_trigger(self):
        """測試 !where 立即觸發"""
        triggered = []

        async def on_search(session: DiscordFoodSession, is_cmd: bool):
            triggered.append((session.session_id, is_cmd))

        tracker = DiscordMessageTracker(
            command_triggers=["!where"],
            default_timeout=5,
            on_trigger_search_async=on_search
        )
        dummy_msg = DummyMessage()
        tracker.add_food_image(channel_id=1, author_id=10, message=dummy_msg, image_path="fake.jpg", timeout=5)

        action = await tracker.handle_text_message(channel_id=1, text="!where")
        self.assertEqual(action, "TRIGGERED_CMD")
        self.assertEqual(len(triggered), 1)
        self.assertTrue(triggered[0][1], "必須標記為指令觸發")

    def test_case_manager_per_case_folder_structure(self):
        """測試案件管理器正確建立一案一目錄 (案件-00X/) 架構"""
        import tempfile
        from services.case_manager import CaseManager
        test_dir = tempfile.mkdtemp()
        try:
            cm = CaseManager(cases_dir=test_dir)
            img_path = os.path.join(test_dir, "sample.jpg")
            with open(img_path, "wb") as f:
                f.write(b"sample_img_content_999")

            cid = cm.create_case_from_discord(
                image_path=img_path,
                channel_id=12345,
                message_id=67890,
                author_name="userA"
            )
            self.assertEqual(cid, "001")

            # 驗證子資料夾與檔案存在
            case_subfolder = os.path.join(test_dir, f"案件-{cid}")
            self.assertTrue(os.path.isdir(case_subfolder), "必須生成 案件-001 專屬子資料夾")
            self.assertTrue(os.path.exists(os.path.join(case_subfolder, f"案件-{cid}.json")))
            self.assertTrue(os.path.exists(os.path.join(case_subfolder, f"案件-{cid}-Discord照片.md")))
            self.assertTrue(os.path.exists(os.path.join(case_subfolder, f"案件-{cid}-Discord照片.jpg")))

            # 驗證下一號案件計算
            next_cid = cm.get_next_case_id()
            self.assertEqual(next_cid, "002")

            # 驗證查詢
            found = cm.find_case_by_message(67890)
            self.assertIsNotNone(found)
            self.assertEqual(found.get("case_id"), "001")
        finally:
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_identifier_never_falsely_accepts_guesses(self):
        """
        [問題 2 核心防禦] 測試辨識引擎絕不在機器人側憑猜測字串宣布命中，
        一律回傳 None 確保交由本地 Antigravity 深度物證分析，杜絕「澎拜」被誤判為真！
        """
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"fake_image_bytes")
            tmp_img = f.name
        try:
            # 即使群友傳入「澎拜」等猜測
            res = self.identifier.identify([tmp_img], guess_candidates=["澎拜", "澎湃豆花"])
            self.assertIsNone(res, "機器人側絕不應自行宣布群友猜測命中，必須回傳 None 交由本地權威物證排查")
        finally:
            if os.path.exists(tmp_img):
                os.remove(tmp_img)

    def test_case_manager_deduplication(self):
        """
        [問題 1 核心防禦] 測試案件管理員去重機制：
        同一 message_id 或相同圖片重複發起時，不重複建立新案件
        """
        import tempfile
        from services.case_manager import CaseManager
        test_dir = tempfile.mkdtemp()
        try:
            cm = CaseManager(cases_dir=test_dir)
            img_path = os.path.join(test_dir, "test_food.jpg")
            with open(img_path, "wb") as f:
                f.write(b"dummy_food_image_content_12345")

            # 第一次立案
            cid1 = cm.create_case_from_discord(
                image_path=img_path,
                channel_id=738757200780066839,
                message_id=999888777,
                author_name="tester"
            )
            self.assertEqual(cid1, "001")

            # 同一 message_id 重複立案
            cid2 = cm.create_case_from_discord(
                image_path=img_path,
                channel_id=738757200780066839,
                message_id=999888777,
                author_name="tester"
            )
            self.assertEqual(cid2, "001", "相同訊息 ID 必須沿用既有案件編號")

            # 不同 message_id 但照片內容完全一致
            cid3 = cm.create_case_from_discord(
                image_path=img_path,
                channel_id=738757200780066839,
                message_id=111222333,
                author_name="another_user"
            )
            self.assertEqual(cid3, "001", "相同圖片特徵必須沿用既有案件編號，防止重複建案")
        finally:
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)


    def test_price_estimation_formatting_enabled(self):
        """測試開啟菜單計價選配時，正確排版品項清單與預估總價"""
        from bot import format_price_estimation, config
        orig = config.enable_price_estimation
        try:
            config.enable_price_estimation = True
            case_data = {
                "price_estimation": {
                    "currency": "TWD",
                    "menu_date": "2026-07",
                    "items": [
                        {"name": "鮮蝦蒸餃", "spec": "一籠8顆", "quantity": 1, "unit_price": 150, "subtotal": 150},
                        {"name": "酸辣湯", "quantity": 2, "unit_price": 45, "subtotal": 90}
                    ],
                    "total_price": 240,
                    "notes": "免服務費"
                }
            }
            lines = format_price_estimation(case_data)
            self.assertTrue(any("2026-07 最新菜單" in l for l in lines))
            self.assertTrue(any("鮮蝦蒸餃（一籠8顆）：$150" in l for l in lines))
            self.assertTrue(any("酸辣湯 × 2：$90" in l for l in lines))
            self.assertTrue(any("預估總計：約 NT$ 240" in l and "(免服務費)" in l for l in lines))
        finally:
            config.enable_price_estimation = orig

    def test_price_estimation_formatting_disabled(self):
        """測試關閉菜單計價選配時，回傳空列表（不干擾回覆）"""
        from bot import format_price_estimation, config
        orig = config.enable_price_estimation
        try:
            config.enable_price_estimation = False
            case_data = {
                "price_estimation": {
                    "items": [{"name": "牛肉麵", "subtotal": 180}],
                    "total_price": 180
                }
            }
            lines = format_price_estimation(case_data)
            self.assertEqual(lines, [], "關閉選配時必須回傳空列表")
        finally:
            config.enable_price_estimation = orig

    def test_price_estimation_backward_compatibility(self):
        """測試向下相容舊案件 (只有 leading_candidate.dish 與 estimated_total)"""
        from bot import format_price_estimation, config
        orig = config.enable_price_estimation
        try:
            config.enable_price_estimation = True
            case_data = {
                "leading_candidate": {
                    "name": "某餐廳",
                    "dish": "招牌乾麵",
                    "estimated_total": "NT$ 60"
                }
            }
            lines = format_price_estimation(case_data)
            self.assertTrue(any("招牌乾麵" in l for l in lines))
            self.assertTrue(any("預估總計：約 NT$ 60" in l for l in lines))
        finally:
            config.enable_price_estimation = orig


    def test_case_manager_markdown_and_json_schema(self):
        """測試新建立的案件檔案包含最新餐點與價位試算骨架與標準 JSON 欄位"""
        import tempfile
        import json
        from services.case_manager import CaseManager
        test_dir = tempfile.mkdtemp()
        try:
            cm = CaseManager(cases_dir=test_dir)
            img_path = os.path.join(test_dir, "test.jpg")
            with open(img_path, "wb") as f:
                f.write(b"dummy")

            cid = cm.create_case_from_discord(img_path, 111, 222, "tester")
            case_folder = os.path.join(test_dir, f"案件-{cid}")
            md_path = os.path.join(case_folder, f"案件-{cid}-Discord照片.md")
            json_path = os.path.join(case_folder, f"案件-{cid}.json")

            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()
            self.assertIn("### 餐點品項與價位試算", md_text)
            self.assertIn("預估總金額", md_text)

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("price_estimation", data)
            self.assertIn("leading_candidate", data)
            self.assertIn("resolved", data)
            self.assertFalse(data["resolved"])
            self.assertEqual(data["status"], "investigating")
        finally:
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
