import os
import sys
import asyncio
import discord

# 設定模組搜尋路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DiscordBotConfig
from services.food_detector import FoodDetector
from services.restaurant_identifier import RestaurantIdentifier
from services.tracker import DiscordMessageTracker, DiscordFoodSession

from services.case_manager import CaseManager

config = DiscordBotConfig.load()
food_detector = FoodDetector(api_key=config.gemini_api_key)
restaurant_identifier = RestaurantIdentifier(
    reply_footer=config.reply_footer,
    gemini_api_key=config.gemini_api_key
)
case_manager = CaseManager()

# 暫存目錄
scratch_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch", "discord")
os.makedirs(scratch_dir, exist_ok=True)

# Discord Intents
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

async def set_single_reaction(message: discord.Message, new_emoji: str):
    """
    確保機器人在同一則訊息上永遠只保留 1 個最新狀態的 emoji 反應
    """
    try:
        # 清除自己先前加過的其他表情
        for r in message.reactions:
            if r.me and str(r.emoji) != new_emoji:
                try:
                    await message.remove_reaction(r.emoji, client.user)
                except Exception:
                    pass
        # 加上新的唯一表情
        await message.add_reaction(new_emoji)
    except Exception as e:
        print(f"[貓貓偵探 ⚠️] 更新唯一表情失敗: {e}")

async def on_trigger_search_callback(session: DiscordFoodSession, is_command: bool):
    """
    執行餐廳辨識：
    1. 收集頻道內群友發言中的猜測店名作為交叉驗證線索
    2. 調用 Lens / 辨識引擎
    3. 辨識完成後核對是否有群友答對：
       - 若答對時間差 > 3 分鐘：只按 🎯 表情，不發文字打擾
       - 若答對時間差 <= 3 分鐘：按 🎯 表情並發布確認回覆
       - 若無人答對：發布店名與 Google Maps 連結 (店名與連結間無空行)
    """
    import time
    print(f"[Bot] 收到照片，立即啟動辨識！照片列表: {session.image_paths}")
    
    # 先收集自發圖以來，群友發言中可能提到的店名候選 (排除機器人自己的發言)
    guess_candidates = []
    try:
        async for history_msg in session.first_message.channel.history(after=session.first_message, limit=30):
            if not history_msg.author.bot and history_msg.content:
                text = history_msg.content.strip()
                # 簡單排除純指令或太長的句子
                if not text.startswith("!") and 2 <= len(text) <= 25:
                    guess_candidates.append(text)
    except Exception as e:
        print(f"[Bot] 抓取猜測線索失敗: {e}")

    # 在非同步執行緒中執行 Lens 辨識 (並帶入群友猜測作為候選比對)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        restaurant_identifier.identify,
        session.image_paths,
        guess_candidates
    )
    
    ai_found_time = time.time()

    if result and result.get("name"):
        target_name = result["name"].strip()
        maps_url = result.get("maps_url", "").strip()
        footer = config.reply_footer.strip()

        print(f"[貓貓偵探 🎯] 成功鎖定店家：【{target_name}】！正在檢查是否有群友搶先猜對...")

        # 核心店名關鍵字提取 (例如 "一蘭拉麵 台北本店" 包含 "一蘭")
        core_keywords = [target_name]
        parts = target_name.split()
        if len(parts) > 1 and len(parts[0]) >= 2:
            core_keywords.append(parts[0])

        correct_msg = None
        try:
            async for history_msg in session.first_message.channel.history(after=session.first_message, limit=50):
                if history_msg.author.bot:
                    continue
                text_lower = history_msg.content.lower()
                if any(kw.lower() in text_lower for kw in core_keywords):
                    correct_msg = history_msg
                    break
        except Exception as e:
            print(f"[貓貓偵探 ⚠️] 檢查頻道發言歷史失敗: {e}")

        # 若有人答對
        if correct_msg:
            try:
                await correct_msg.add_reaction("🎯")
                print(f"[貓貓偵探 👏] 群友【{correct_msg.author}】答對了！已為其訊息加上 🎯 表情。")
            except Exception:
                pass

            msg_timestamp = correct_msg.created_at.timestamp()
            time_diff = ai_found_time - msg_timestamp

            # 若答對到找到時間超過 3 分鐘 (180 秒)，只按表情，不發文字！
            if time_diff > 180:
                print(f"[貓貓偵探 🤫] 群友答對已超過 3 分鐘 (差 {time_diff:.1f} 秒)，依照規則只按表情，不發文字打擾。")
                return

            # 若在 3 分鐘以內答對，發送確認回覆
            reply_lines = [
                f"🎉 已被 {correct_msg.author.mention} 搶先答對囉！",
                target_name,
                maps_url
            ]
        else:
            print(f"[貓貓偵探 📢] 無人答對，準備在頻道直接公布解答！")
            reply_lines = [
                target_name,
                maps_url
            ]

        if footer:
            reply_lines.append(footer)

        reply_text = "\n".join(reply_lines)
        try:
            await session.first_message.reply(reply_text, mention_author=False)
            await set_single_reaction(session.first_message, "✅")
            print(f"[貓貓偵探 ✅] 已成功引用回覆解答至 Discord！")
        except Exception as e:
            print(f"[貓貓偵探 ❌] 回覆發送失敗: {e}")
            await session.first_message.channel.send(reply_text)
    else:
        # 秒查未能確定店家，啟動「雙軌疑難案件接力」
        print(f"[貓貓偵探 🐾] 視覺特徵不足以秒查，啟動 Antigravity 深度物證接力...")
        await set_single_reaction(session.first_message, "🕵️")

        case_id = case_manager.create_case_from_discord(
            image_path=session.image_paths[0],
            channel_id=session.channel_id,
            message_id=session.first_message.id,
            author_name=str(session.first_message.author),
            guess_candidates=guess_candidates
        )
        print(f"[貓貓偵探 📋] 疑難案件已立案 (案件-{case_id})！Discord 已標註 🕵️ 表情，等待深度排查。")

        # 全自動在 Antigravity 專案開啟全新獨立對話 (New Conversation)，模型指定為 Flash
        try:
            agentapi_bat = r"C:\Users\water\.gemini\antigravity\bin\agentapi.bat"
            if os.path.exists(agentapi_bat):
                import subprocess
                investigate_prompt = (
                    f"請調查最新案件【案件-{case_id}】。\n"
                    f"1. 請讀取 案件/案件-{case_id}-Discord照片.jpg 並觀察照片可見物證。\n"
                    f"2. 依專案規範透過本機 Chrome 9222 執行 scripts/browser_controller.py 進行 Google Lens 多模態比對。\n"
                    f"3. 確認店家與營業狀態後，更新 案件/案件-{case_id}.json（填寫 leading_candidate, status: 'resolved', resolved: true）與 案件/案件-{case_id}-Discord照片.md 結案。"
                )
                cmd = [
                    agentapi_bat,
                    "new-conversation",
                    "--model=flash",
                    f"--title=案件-{case_id} 食物照片辨識",
                    investigate_prompt
                ]
                subprocess.Popen(
                    cmd,
                    cwd=case_manager.project_root,
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print(f"[貓貓偵探 🚀] 已全自動在 Antigravity 專案開啟全新獨立對話 (案件-{case_id})，由 Flash 展開調查！")
        except Exception as e:
            print(f"[貓貓偵探 ⚠️] 自動啟動 Antigravity 新對話失敗: {e}")

async def watch_case_resolutions():
    """
    背景輪詢監聽：
    1. 執行 30 分鐘停損檢查 (超時自動標記為尚無法確認)
    2. 當 Antigravity 在本地結案時，自動回傳 Discord 或標註表情！
    """
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            case_manager.check_and_apply_timeout_cutoff(max_seconds=1800)
            resolved_cases = case_manager.get_resolved_unnotified_cases()
            for json_path, case_data in resolved_cases:
                meta = case_data.get("discord_meta", {})
                channel_id = meta.get("channel_id")
                message_id = meta.get("message_id")
                lead = case_data.get("leading_candidate", {}) or {}
                name = lead.get("name", "").strip()
                maps_url = lead.get("google_maps_url", "").strip()
                status = case_data.get("status")

                if channel_id and message_id:
                    channel = client.get_channel(channel_id)
                    if channel:
                        try:
                            msg = await channel.fetch_message(message_id)
                            # 情況 A: 30 分鐘停損
                            if status == "unconfirmed" or case_data.get("timeout_cutoff"):
                                await set_single_reaction(msg, "❓")
                                print(f"[貓貓偵探 ❓] 案件-{case_data.get('case_id')} 達 30 分鐘停損，已在 Discord 標註 ❓ 表情。")

                            # 情況 B: 成功破案結案
                            elif name:
                                reply_lines = [name, maps_url]
                                if config.reply_footer:
                                    reply_lines.append(config.reply_footer)
                                await msg.reply("\n".join(reply_lines), mention_author=False)
                                await set_single_reaction(msg, "✅")
                                print(f"[貓貓偵探 🎉] 案件-{case_data.get('case_id')} 深度破案，已成功回傳 Discord！")
                        except Exception as e:
                            print(f"[貓貓偵探 ❌] 案件回報 Discord 失敗: {e}")
                case_manager.mark_case_notified(json_path, case_data)
        except Exception as e:
            print(f"[貓貓偵探 ⚠️] 監聽案件結案異常: {e}")
        await asyncio.sleep(5)

tracker = DiscordMessageTracker(
    default_timeout=config.trigger_timeout_seconds,
    on_trigger_search_async=on_trigger_search_callback,
    is_mentioning_restaurant_fn=food_detector.check_mention_restaurant
)

@client.event
async def on_ready():
    print("=" * 55)
    print(f"[+] 這哪家小貓偵探機器人已成功上線！🐾")
    print(f"[+] 機器人帳號: {client.user} (ID: {client.user.id})")
    print(f"[+] 觸發模式: 發圖標註 @這哪家 或 回覆照片 @這哪家")
    print(f"[+] 運作架構: 雙軌制（Lens 秒查 + Antigravity 深度物證接力）")
    print("=" * 55)
    client.loop.create_task(watch_case_resolutions())

def parse_timeout_from_content(content: str, default_seconds: int = 180) -> int:
    """
    從訊息文字解析逾時秒數：
    支援：
    - now, !where -> 0 (立即辨識)
    - 60, 60s, 60秒 -> 60
    - 3m, 3分, 3分鐘 -> 180
    - 預設 -> default_seconds
    """
    import re
    text = content.lower().strip()
    if any(k in text for k in ["now", "即時", "馬上", "立刻", "!where", "這哪家"]):
        return 0

    match_m = re.search(r'(\d+)\s*(m|分|分鐘)', text)
    if match_m:
        return int(match_m.group(1)) * 60

    match_s = re.search(r'(\d+)\s*(s|秒)?', text)
    if match_s and match_s.group(1):
        val = int(match_s.group(1))
        # 避免純數字過小或過大造成誤解
        if 5 <= val <= 3600:
            return val

    return default_seconds

@client.event
async def on_message(message: discord.Message):
    # 忽略自己或其它機器人的發言
    if message.author.bot:
        return

    is_mentioned = client.user in message.mentions
    image_attachments = [
        att for att in message.attachments
        if att.content_type and att.content_type.startswith("image/")
    ]

    # 1. 情境 A: 使用者上傳照片同時 @機器人
    if image_attachments and is_mentioned:
        # 依使用者最新需求：預設直接找 (timeout=0)，除非文字有特別指定倒數秒數
        timeout_sec = parse_timeout_from_content(message.content, default_seconds=0)
        
        # 標註狀態表情 (確保只有單一表情)
        await set_single_reaction(message, "🔍" if timeout_sec == 0 else "⏱️")

        print(f"[貓貓偵探 📸] 收到來自【{message.author}】上傳的 {len(image_attachments)} 張照片！")
        for att in image_attachments:
            local_filename = f"{message.id}_{att.filename}"
            save_path = os.path.join(scratch_dir, local_filename)
            await att.save(save_path)
            print(f"[貓貓偵探 💾] 照片已下載暫存: {save_path} (大小: {att.size} bytes)")

            is_food, reason = food_detector.is_food_image(save_path)
            if is_food:
                print(f"[貓貓偵探 🐟] 判定為美食照片 ({reason})！啟動找餐廳流程。")
                tracker.add_food_image(
                    channel_id=message.channel.id,
                    author_id=message.author.id,
                    message=message,
                    image_path=save_path,
                    timeout=timeout_sec
                )
            else:
                print(f"[貓貓偵探 🐾] 判定非美食照片 ({reason})，略過處理。")
        return

    # 2. 情境 B: 使用者回覆某則圖片訊息並 @機器人
    if is_mentioned and message.reference:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            ref_images = [
                att for att in ref_msg.attachments
                if att.content_type and att.content_type.startswith("image/")
            ]
            if ref_images:
                timeout_sec = parse_timeout_from_content(message.content, default_seconds=0)
                await set_single_reaction(message, "🔍" if timeout_sec == 0 else "⏱️")

                print(f"[貓貓偵探 📜] 抓取到被引用訊息【{ref_msg.id}】中的 {len(ref_images)} 張歷史照片！")
                for att in ref_images:
                    local_filename = f"{ref_msg.id}_{att.filename}"
                    save_path = os.path.join(scratch_dir, local_filename)
                    if not os.path.exists(save_path):
                        await att.save(save_path)

                    is_food, reason = food_detector.is_food_image(save_path)
                    if is_food:
                        print(f"[貓貓偵探 🐟] 引用照片判定為美食 ({reason})！啟動找餐廳流程。")
                        tracker.add_food_image(
                            channel_id=message.channel.id,
                            author_id=message.author.id,
                            message=ref_msg,
                            image_path=save_path,
                            timeout=timeout_sec
                        )
                return
        except Exception as e:
            print(f"[貓貓偵探 ⚠️] 解析引用歷史訊息失敗: {e}")

    # 3. 處理狀態查詢指令 (!status 或 @這哪家 status)
    if message.content:
        clean_content = message.content.strip().lower()
        if "!status" in clean_content or (is_mentioned and "status" in clean_content):
            active_cases = case_manager.get_investigating_cases()
            if active_cases:
                cases_str = "、".join([f"案件-{c.get('case_id')}" for c in active_cases])
                await message.reply(f"📋 目前共有 {len(active_cases)} 個疑難案件正在由 Antigravity 進行深度微型物證排查中：\n`{cases_str}`", mention_author=False)
            else:
                await message.reply("✨ 目前沒有任何排查中的案件，所有照片皆已結案！", mention_author=False)
            return

    # 4. 一般對話文字不再中斷搜尋，讓群友自由討論猜謎

def main():
    if not config.bot_token or config.bot_token == "YOUR_DISCORD_BOT_TOKEN":
        print("[!] 尚未在 config.json 或環境變數中設定 DISCORD_BOT_TOKEN！")
        print("[*] 請先前往 https://discord.com/developers/applications 建立 Bot 並取得 Token。")
        print("[*] 建立後填入 discord_bot/config.json 即可啟動。")
        return

    client.run(config.bot_token)

if __name__ == "__main__":
    main()
