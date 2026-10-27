import os
import sys
import json
import shutil
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

    def test_price_estimation_fixed_enabled(self):
        """測試價錢顯示改為固定開啟（無法透過指令或變數關閉，即使外部屬性變動仍固定輸出價錢）"""
        from bot import format_price_estimation, config
        orig = getattr(config, "enable_price_estimation", True)
        try:
            config.enable_price_estimation = False
            case_data = {
                "price_estimation": {
                    "items": [{"name": "牛肉麵", "subtotal": 180}],
                    "total_price": 180
                }
            }
            lines = format_price_estimation(case_data)
            self.assertTrue(any("牛肉麵" in l for l in lines), "價錢顯示固定開啟，必須正常輸出品項")
            self.assertTrue(any("180" in l for l in lines), "必須輸出金額")
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


    def test_case_manager_multi_image_handling(self):
        """測試案件管理器支援多張照片合併為同一案件 (案件-00X-Discord照片-1.jpg, 2.jpg)"""
        import tempfile
        import json
        from services.case_manager import CaseManager
        test_dir = tempfile.mkdtemp()
        try:
            cm = CaseManager(cases_dir=test_dir)
            img1 = os.path.join(test_dir, "view1.jpg")
            img2 = os.path.join(test_dir, "view2.jpg")
            with open(img1, "wb") as f:
                f.write(b"food_photo_angle_1")
            with open(img2, "wb") as f:
                f.write(b"menu_photo_angle_2")

            # 建立多圖案件
            cid = cm.create_case_from_discord(
                image_paths=[img1, img2],
                channel_id=888,
                message_id=999,
                author_name="multi_user"
            )
            self.assertEqual(cid, "001")

            case_subfolder = os.path.join(test_dir, f"案件-{cid}")
            self.assertTrue(os.path.exists(os.path.join(case_subfolder, f"案件-{cid}-Discord照片-1.jpg")))
            self.assertTrue(os.path.exists(os.path.join(case_subfolder, f"案件-{cid}-Discord照片-2.jpg")))
            self.assertTrue(os.path.exists(os.path.join(case_subfolder, f"案件-{cid}-Discord照片.jpg")))

            # 驗證 Markdown 內容包含所有照片
            md_path = os.path.join(case_subfolder, f"案件-{cid}-Discord照片.md")
            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()
            self.assertIn(f"案件-{cid}-Discord照片-1.jpg", md_text)
            self.assertIn(f"案件-{cid}-Discord照片-2.jpg", md_text)
            self.assertIn("共 2 張", md_text)

            # 驗證 JSON 包含 images 清單
            json_path = os.path.join(case_subfolder, f"案件-{cid}.json")
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data.get("images", [])), 2)

            # 驗證多圖特徵去重 (傳入包含 img2 的新請求)
            cid_dup = cm.create_case_from_discord(
                image_paths=[img2],
                channel_id=888,
                message_id=1000,
                author_name="another_user"
            )
            self.assertEqual(cid_dup, "001", "多圖中若任一照片吻合既有案件，必須自動去重沿用既有案件編號")
        finally:
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)


    def test_crop_tool_functionality(self):
        """測試物證裁切工具 (crop_tool.py) 支援百分比裁切與高品質放大"""
        import tempfile
        from PIL import Image
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))
        from crop_tool import crop_image

        test_dir = tempfile.mkdtemp()
        try:
            # 建立 200x200 測試圖
            src_path = os.path.join(test_dir, "test_crop_src.jpg")
            img = Image.new("RGB", (200, 200), color="blue")
            img.save(src_path)

            # 測試百分比裁切 (0.25, 0.25, 0.75, 0.75 -> 100x100) 並放大 2 倍 -> 200x200
            dst_path = os.path.join(test_dir, "cropped.jpg")
            out = crop_image(
                input_path=src_path,
                output_path=dst_path,
                percent=[0.25, 0.25, 0.75, 0.75],
                zoom=2.0
            )
            self.assertTrue(os.path.exists(dst_path))
            with Image.open(dst_path) as res_im:
                self.assertEqual(res_im.size, (200, 200), "裁切後放大 2 倍尺寸應吻合")
        finally:
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)


    def test_homemade_cooking_no_maps_url(self):
        """測試手作自煮料理 (is_homemade=True 或店名含手作/自煮) 絕對不產生 Google 地點連結"""
        from bot import extract_maps_url
        lead1 = {
            "name": "這是自己手作的料理",
            "is_homemade": True,
            "google_maps_url": "https://maps.app.goo.gl/dummy"
        }
        self.assertEqual(extract_maps_url(lead1), "", "手作料理絕不應產生 Maps 連結")

        lead2 = {
            "name": "自製家常炒飯",
            "address": "台北市某住家",
            "maps_url": ""
        }
        self.assertEqual(extract_maps_url(lead2), "", "含有自製關鍵字且無明確店名時絕不產生 Maps 連結")

    def test_homemade_cooking_price_estimation_format(self):
        """測試手作自煮料理的價格資訊排版為自家愛心無價"""
        from bot import format_price_estimation
        case_data = {
            "leading_candidate": {
                "name": "自己手作的牛排",
                "is_homemade": True
            }
        }
        lines = format_price_estimation(case_data)
        self.assertTrue(any("自家用心烹飪，愛心無價" in l for l in lines))


    def test_real_restaurant_with_shouzuo_or_jiachang_not_misidentified(self):
        """[核心防禦] 測試店名包含『手作』或『家常』的真實餐廳絕不被誤判為自煮料理！"""
        from bot import is_homemade_meal, extract_maps_url, format_price_estimation

        # 案例 1: 實體店名包含「手作」
        real_shop1 = {
            "name": "初魚 手作鐵板燒",
            "google_maps_url": "https://maps.app.goo.gl/chuyu123",
            "is_restaurant": True
        }
        self.assertFalse(is_homemade_meal(real_shop1), "初魚手作鐵板燒不得被判定為手作自煮料理")
        self.assertEqual(extract_maps_url(real_shop1), "https://maps.app.goo.gl/chuyu123", "必須完整保留 Maps 網址")

        # 驗證菜單價格試算不會被誤判為自煮愛心無價
        case1 = {
            "leading_candidate": real_shop1,
            "price_estimation": {
                "items": [{"name": "無菜單套餐", "unit_price": 1800, "subtotal": 1800}],
                "total_price": 1800
            }
        }
        lines1 = format_price_estimation(case1)
        self.assertTrue(any("無菜單套餐" in l for l in lines1), "實體手作餐廳必須正常列出菜單價格")
        self.assertFalse(any("愛心無價" in l for l in lines1), "實體手作餐廳絕不能顯示自煮愛心無價")

        # 案例 2: 實體店名包含「家常」
        real_shop2 = {
            "name": "小川家常菜",
            "address": "台北市大安區和平東路"
        }
        self.assertFalse(is_homemade_meal(real_shop2), "小川家常菜不得被判定為自煮料理")
        url2 = extract_maps_url(real_shop2)
        self.assertTrue(url2.startswith("https://maps.google.com/?q="), "必須正常產生導航連結")
        self.assertIn("和平東路", url2)

    def test_genuine_homemade_cooking_identified(self):
        """測試真正的自煮料理 (包含自己手作、is_homemade 等) 精準識別"""
        from bot import is_homemade_meal, extract_maps_url, format_price_estimation

        home1 = {
            "name": "自己手作的法式千層蛋糕",
            "is_homemade": True
        }
        self.assertTrue(is_homemade_meal(home1), "明確標註 is_homemade 必須判定為自煮手作")
        self.assertEqual(extract_maps_url(home1), "", "自煮料理絕不產生 Maps 網址")

        home2 = {
            "name": "自己煮的家常牛肉麵"
        }
        self.assertTrue(is_homemade_meal(home2), "店名含『自己煮』必須判定為自煮手作")

    def test_convenience_store_takeout_price_estimation_not_misidentified_as_homemade(self):
        """[核心防禦] 測試超商/零售外帶食品（如 7-Eleven 布丁＋優格）絕不被誤判為自煮愛心無價，必須完整列出品項與價格！"""
        from bot import is_homemade_meal, extract_maps_url, format_price_estimation

        store_item = {
            "name": "日本 7-Eleven 超商點心（布丁＋優格，於飯店客房內食用）",
            "is_restaurant": False,
            "is_retail": True,
            "is_homemade": False
        }
        self.assertFalse(is_homemade_meal(store_item), "超商零售外帶絕不能判定為自煮手作料理")
        self.assertEqual(extract_maps_url(store_item), "", "超商外帶不產生特定單一門市 Maps 連結")

        case = {
            "leading_candidate": store_item,
            "price_estimation": {
                "currency": "JPY",
                "items": [
                    {"name": "セブン-イレブン カスタードプリン（布丁）", "subtotal": 289},
                    {"name": "セブンプレミアム のむヨーグルト ブルーベリー（藍莓優格飲）", "subtotal": 183}
                ],
                "total_price": 472
            }
        }
        lines = format_price_estimation(case)
        self.assertFalse(any("愛心無價" in l for l in lines), "超商外帶點心絕不能顯示自家用心烹飪")
        self.assertTrue(any("布丁" in l for l in lines), "必須包含布丁品項")
        self.assertTrue(any("藍莓優格飲" in l for l in lines), "必須包含藍莓優格飲品項")
        self.assertTrue(any("472" in l for l in lines), "必須包含總金額試算")

    def test_pending_price_requests_management(self):
        """測試待通知價格請求 (Pending Price Requests) 的新增、查詢、防重複與提取清空 (Pop)"""
        import tempfile
        from services.case_manager import CaseManager
        test_dir = tempfile.mkdtemp()
        try:
            cm = CaseManager(cases_dir=test_dir)
            # 使用獨立的暫存 pending_price_requests 檔案
            cm.pending_price_requests_file = os.path.join(test_dir, "pending_price_requests.json")

            # 1. 登記請求
            res1 = cm.add_pending_price_request(case_id="035", channel_id=111, message_id=222, user_id=333)
            self.assertTrue(res1, "首次登記必須成功")

            # 2. 防重複登記
            res2 = cm.add_pending_price_request(case_id="035", channel_id=111, message_id=222, user_id=333)
            self.assertFalse(res2, "重複 message_id 登記必須回傳 False")

            # 3. 登記另一個請求
            res3 = cm.add_pending_price_request(case_id="035", channel_id=111, message_id=223, user_id=444)
            self.assertTrue(res3)

            # 4. 登記其他案件
            cm.add_pending_price_request(case_id="036", channel_id=111, message_id=224, user_id=555)

            # 5. 查詢
            reqs_035 = cm.get_pending_price_requests("035")
            self.assertEqual(len(reqs_035), 2)
            self.assertEqual(len(cm.get_pending_price_requests()), 3)

            # 6. Pop 取出 035 (應移出佇列)
            popped = cm.pop_pending_price_requests("035")
            self.assertEqual(len(popped), 2)
            # 檢查 035 是否已清空，036 依然存在
            self.assertEqual(len(cm.get_pending_price_requests("035")), 0)
            self.assertEqual(len(cm.get_pending_price_requests("036")), 1)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_find_case_by_query_with_investigating(self):
        """測試 find_case_by_query 支援 allow_investigating=True，涵蓋調查中與已結案案件"""
        import tempfile
        import json
        from services.case_manager import CaseManager
        test_dir = tempfile.mkdtemp()
        try:
            cm = CaseManager(cases_dir=test_dir)
            # 建立已結案 001
            c1_dir = os.path.join(test_dir, "案件-001")
            os.makedirs(c1_dir, exist_ok=True)
            with open(os.path.join(c1_dir, "案件-001.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "case_id": "001",
                    "status": "resolved",
                    "resolved": True,
                    "leading_candidate": {"name": "老張牛肉麵"}
                }, f)

            # 建立調查中 002
            c2_dir = os.path.join(test_dir, "案件-002")
            os.makedirs(c2_dir, exist_ok=True)
            with open(os.path.join(c2_dir, "案件-002.json"), "w", encoding="utf-8") as f:
                json.dump({
                    "case_id": "002",
                    "status": "investigating",
                    "resolved": False,
                    "leading_candidate": {}
                }, f)

            # 當 allow_investigating=False (預設 !report 邏輯)：查不到 002，無參數時回傳 001
            res_report = cm.find_case_by_query("", allow_investigating=False)
            self.assertEqual(res_report.get("case_id"), "001")
            self.assertIsNone(cm.find_case_by_query("002", allow_investigating=False))

            # 當 allow_investigating=True (!price 邏輯)：無參數時回傳最新的 002
            res_price_latest = cm.find_case_by_query("", allow_investigating=True)
            self.assertEqual(res_price_latest.get("case_id"), "002")

            # 指定編號查 002 (調查中) 也能成功找到
            res_price_002 = cm.find_case_by_query("002", allow_investigating=True)
            self.assertEqual(res_price_002.get("case_id"), "002")

            # 指定編號查 001 (已結案) 也正常
            res_price_001 = cm.find_case_by_query("001", allow_investigating=True)
            self.assertEqual(res_price_001.get("case_id"), "001")
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_build_price_reply(self):
        """測試 build_price_reply 對各種案件型態之訊息排版格式"""
        from bot import build_price_reply

        # 案例 A: 正常已結案餐廳
        case_resolved = {
            "case_id": "034",
            "leading_candidate": {"name": "勝烈亭 新市街本店"},
            "price_estimation": {
                "currency": "JPY",
                "items": [{"name": "海老とひれかつ膳", "price": 2420}],
                "total_estimated_price": 2420
            }
        }
        res_a = build_price_reply(case_resolved, is_deferred=False)
        self.assertIn("💰 **【案件-034 菜單價格資訊】**", res_a)
        self.assertIn("勝烈亭 新市街本店", res_a)
        self.assertIn("2420", res_a)
        self.assertIn("!report 034", res_a)

        # 案例 B: 非同步延遲回報出爐 (is_deferred=True)
        res_b = build_price_reply(case_resolved, is_deferred=True)
        self.assertIn("💰 **【案件-034 價錢出爐囉！】**", res_b)

        # 案例 C: 自煮手作料理
        case_home = {
            "case_id": "025",
            "leading_candidate": {"name": "自己煮的家常牛肉麵", "is_homemade": True}
        }
        res_c = build_price_reply(case_home)
        self.assertIn("自家用心烹飪，愛心無價 ❤️", res_c)

    async def test_price_command_end_to_end_flow(self):
        """測試 !price 指令端到端非同步流程：包含已結案即時回傳、調查中先登記暫時回覆、查無案件推薦"""
        import bot
        from bot import client

        class MockAuthor:
            def __init__(self, uid=888, is_bot=False):
                self.id = uid
                self.bot = is_bot
                self.mention = f"<@{uid}>"

        class MockChannel:
            def __init__(self, cid=777):
                self.id = cid
                self.name = "test-channel"
                self.sent_messages = []

            async def send(self, content=None, file=None):
                self.sent_messages.append(content)

        class MockDiscordMessage:
            def __init__(self, content, msg_id=999, author=None, channel=None):
                self.id = msg_id
                self.content = content
                self.author = author or MockAuthor()
                self.channel = channel or MockChannel()
                self.reference = None
                self.guild = None
                self.mentions = []
                self.attachments = []
                self.replies = []

            async def reply(self, content, mention_author=False, file=None):
                self.replies.append(content)

        # 1. 測試指定已結案之案件 (例如 案件-034 勝烈亭)
        msg_34 = MockDiscordMessage("!price 034")
        await client.on_message(msg_34)
        self.assertEqual(len(msg_34.replies), 1)
        self.assertIn("勝烈亭", msg_34.replies[0])
        self.assertIn("2420", msg_34.replies[0])

        # 2. 測試查無案件提示 (例如 99999)
        msg_none = MockDiscordMessage("!price 99999")
        await client.on_message(msg_none)
        self.assertEqual(len(msg_none.replies), 1)
        self.assertIn("找不到與「99999」相關的案件價格資訊", msg_none.replies[0])
        self.assertIn("最近可查詢價格的案件有", msg_none.replies[0])

        # 3. 測試調查中案件：先回覆「正在找」並登記，結案時自動回覆價格
        from bot import case_manager, build_price_reply
        import tempfile
        test_dir = tempfile.mkdtemp()
        orig_cases_dir = case_manager.cases_dir
        orig_reqs_file = case_manager.pending_price_requests_file
        try:
            case_manager.cases_dir = test_dir
            case_manager.pending_price_requests_file = os.path.join(test_dir, "pending_price_requests.json")

            # 建立調查中 099
            c_dir = os.path.join(test_dir, "案件-099")
            os.makedirs(c_dir, exist_ok=True)
            c_json = os.path.join(c_dir, "案件-099.json")
            with open(c_json, "w", encoding="utf-8") as f:
                json.dump({
                    "case_id": "099",
                    "status": "investigating",
                    "resolved": False,
                    "leading_candidate": {}
                }, f)

            # 發送 !price 099
            msg_inv = MockDiscordMessage("!price 099", msg_id=777888)
            await client.on_message(msg_inv)
            self.assertEqual(len(msg_inv.replies), 1)
            self.assertIn("貓貓偵探仍在全力偵辦中", msg_inv.replies[0])
            self.assertIn("已為您登記價格通知", msg_inv.replies[0])

            # 檢查登記紀錄
            pending = case_manager.get_pending_price_requests("099")
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["message_id"], 777888)

            # 模擬案件結案
            with open(c_json, "w", encoding="utf-8") as f:
                json.dump({
                    "case_id": "099",
                    "status": "resolved",
                    "resolved": True,
                    "leading_candidate": {"name": "美味拉麵店"},
                    "price_estimation": {
                        "currency": "NT$",
                        "items": [{"name": "豚骨拉麵", "price": 200}],
                        "total_price": 200
                    }
                }, f)

            # 提取待回覆請求並產生回覆
            popped = case_manager.pop_pending_price_requests("099")
            self.assertEqual(len(popped), 1)
            with open(c_json, "r", encoding="utf-8") as f:
                c_data = json.load(f)
            deferred_reply = build_price_reply(c_data, is_deferred=True)
            self.assertIn("💰 **【案件-099 價錢出爐囉！】**", deferred_reply)
            self.assertIn("美味拉麵店", deferred_reply)
            self.assertIn("200", deferred_reply)
        finally:
            case_manager.cases_dir = orig_cases_dir
            case_manager.pending_price_requests_file = orig_reqs_file
            shutil.rmtree(test_dir, ignore_errors=True)

    async def test_restart_command_permissions(self):
        """測試 !restart 指令管理員權限防禦機制"""
        from bot import client

        class MockPermissions:
            def __init__(self, admin=False):
                self.administrator = admin

        class MockAuthor:
            def __init__(self, uid=888, is_bot=False, admin=False):
                self.id = uid
                self.bot = is_bot
                self.mention = f"<@{uid}>"
                self.guild_permissions = MockPermissions(admin=admin)

        class MockGuild:
            def __init__(self):
                self.id = 111

        class MockChannel:
            def __init__(self):
                self.id = 222

        class MockDiscordMessage:
            def __init__(self, content, author=None, guild=None):
                self.id = 999
                self.content = content
                self.author = author or MockAuthor()
                self.channel = MockChannel()
                self.reference = None
                self.guild = guild
                self.mentions = []
                self.attachments = []
                self.replies = []

            async def reply(self, content, mention_author=False, file=None):
                self.replies.append(content)

        # 1. 一般無管理員權限使用者嘗試重啟
        non_admin_msg = MockDiscordMessage("!restart", author=MockAuthor(admin=False), guild=MockGuild())
        await client.on_message(non_admin_msg)
        self.assertEqual(len(non_admin_msg.replies), 1)
        self.assertIn("權限不足", non_admin_msg.replies[0])

        # 2. 伺服器管理員嘗試重啟 (Mock 掉 subprocess.Popen 防止單元測試觸發真實重啟)
        import unittest.mock as mock
        admin_author = MockAuthor(admin=True)
        admin_msg = MockDiscordMessage("!restart", author=admin_author, guild=MockGuild())
        with mock.patch("subprocess.Popen") as mock_popen:
            await client.on_message(admin_msg)
            self.assertEqual(len(admin_msg.replies), 1)
            self.assertIn("收到重啟指令", admin_msg.replies[0])
            self.assertTrue(mock_popen.called, "管理員觸發重啟時必須呼叫 subprocess.Popen")

if __name__ == "__main__":
    unittest.main()
