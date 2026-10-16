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

    async def test_cancel_when_mentioned_restaurant(self):
        """測試對話中提及店名自動取消倒數"""
        triggered = []

        async def on_search(session: DiscordFoodSession, is_cmd: bool):
            triggered.append(session.session_id)

        detector = FoodDetector()
        tracker = DiscordMessageTracker(
            command_triggers=["!where"],
            default_timeout=1,
            on_trigger_search_async=on_search,
            is_mentioning_restaurant_fn=detector.check_mention_restaurant
        )
        dummy_msg = DummyMessage()
        tracker.add_food_image(channel_id=2, author_id=11, message=dummy_msg, image_path="fake.jpg", timeout=1)

        action = await tracker.handle_text_message(channel_id=2, text="這家是鼎泰豐啦")
        self.assertEqual(action, "CANCELLED_MENTIONED")

        await asyncio.sleep(1.2)
        self.assertEqual(len(triggered), 0, "提及店名後不得觸發搜尋")

    def test_parse_timeout_from_content(self):
        """測試訊息文字中的 timeout 解析"""
        from bot import parse_timeout_from_content
        self.assertEqual(parse_timeout_from_content("@Bot now"), 0)
        self.assertEqual(parse_timeout_from_content("@Bot !where"), 0)
        self.assertEqual(parse_timeout_from_content("@Bot 60s"), 60)
        self.assertEqual(parse_timeout_from_content("@Bot 2m"), 120)
        self.assertEqual(parse_timeout_from_content("@Bot 5分鐘"), 300)
        self.assertEqual(parse_timeout_from_content("@Bot 來找找看", default_seconds=180), 180)

if __name__ == "__main__":
    unittest.main()
