import os
import sys
import socket
import asyncio
import subprocess
import traceback
import builtins
from datetime import datetime

# 單一實例保證（防止多重開機或重複回覆）
_lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _lock_socket.bind(("127.0.0.1", 58421))
except socket.error:
    print("[💥 啟動終止] 偵測到已有其他 Discord 機器人實例正在運行中 (Port 58421 被佔用)！為避免重複回覆，此實例自動退出。")
    sys.exit(0)

# 強制 stdout / stderr 行緩衝即時輸出 (Unbuffered)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# 設定專屬日誌檔案 (scratch/bot.log)
LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scratch", "bot.log")
_orig_print = builtins.print

def bot_print(*args, **kwargs):
    kwargs["flush"] = True
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = " ".join(str(a) for a in args)
    formatted = f"[{now_str}] {msg}"
    try:
        _orig_print(formatted, **kwargs)
    except Exception:
        pass
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

builtins.print = bot_print

def global_excepthook(exc_type, exc_value, exc_traceback):
    err_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"[💥 未捕獲致命錯誤]\n{err_text}")

sys.excepthook = global_excepthook

# 設定模組搜尋路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import discord
from config import DiscordBotConfig
from services.food_detector import FoodDetector
from services.case_manager import CaseManager

config = DiscordBotConfig.load()
food_detector = FoodDetector(api_key=config.gemini_api_key)
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
        for r in message.reactions:
            if r.me and str(r.emoji) != new_emoji:
                try:
                    await message.remove_reaction(r.emoji, client.user)
                except Exception:
                    pass
        await message.add_reaction(new_emoji)
    except Exception as e:
        print(f"[貓貓偵探 ⚠️] 更新唯一表情失敗: {e}")

async def start_investigation(message: discord.Message, image_path: str):
    """
    極速立案並觸發 Antigravity 自動開啟獨立調查新對話（不倒數、直接秒啟動）
    """
    await set_single_reaction(message, "🕵️")

    case_id = case_manager.create_case_from_discord(
        image_path=image_path,
        channel_id=message.channel.id,
        message_id=message.id,
        author_name=str(message.author)
    )
    print(f"[貓貓偵探 📋] 案件已建檔 (案件-{case_id})！Discord 已標註 🕵️ 表情。")

    # 自動呼叫 agentapi 為該案在 Antigravity 開啟全新獨立對話
    try:
        prompt = (
            f"你是 Antigravity 找餐廳小貓偵探。請嚴格依據 AGENTS.md 與 找餐廳判斷規則.md 調查【案件-{case_id}】。\n"
            f"案件圖片：案件/案件-{case_id}/案件-{case_id}-Discord照片.jpg\n"
            f"案件檔案：案件/案件-{case_id}/案件-{case_id}-Discord照片.md 與 案件/案件-{case_id}/案件-{case_id}.json\n"
            f"請利用本機 Chrome 9222、Google Lens、以圖搜尋與 Google Maps 進行深度微型物證排查，"
            f"核對近期營業狀態與器皿，確認後更新 案件/案件-{case_id}/案件-{case_id}.json（填寫 leading_candidate、status='resolved'、resolved=true）"
            f"與對應的 .md 檔案以完成結案！"
        )
        cmd = ["cmd.exe", "/c", "agentapi", "new-conversation", f"--title=案件-{case_id} 調查", prompt]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0:
            print(f"[貓貓偵探 🚀] 已成功為【案件-{case_id}】自動開啟獨立調查新對話！")
        else:
            print(f"[貓貓偵探 ⚠️] 自動開啟新對話異常 (代碼 {res.returncode}): {res.stderr or res.stdout}")
    except Exception as e:
        print(f"[貓貓偵探 ⚠️] 呼叫 agentapi 失敗: {e}")

def extract_maps_url(lead_dict: dict) -> str:
    """
    穩健且乾淨地提取 Google Maps 連結：
    優先產生乾淨短網址 (maps.app.goo.gl 或 ?cid=)，絕不包含 %E... 冗長文字編碼，避免通訊軟體解析錯誤
    """
    if not lead_dict:
        return ""
    import re
    import urllib.parse

    raw_url = (
        lead_dict.get("google_maps_url") or
        lead_dict.get("maps_url") or
        lead_dict.get("map_url") or
        lead_dict.get("url") or
        ""
    ).strip()

    # 1. 已經是官方分享短網址或 CID 純數字短網址
    if "maps.app.goo.gl" in raw_url or "goo.gl/maps" in raw_url or "?cid=" in raw_url:
        return raw_url

    # 2. 若為 Google Maps 長網址，自動提取 hex CID (如 0x7c0cdaf76b2ced82) 轉成十進位 CID 短網址
    cid_match = re.search(r':(0x[0-9a-fA-F]+)', raw_url)
    if cid_match:
        try:
            cid_hex = cid_match.group(1)
            cid_dec = int(cid_hex, 16)
            return f"https://maps.google.com/?cid={cid_dec}"
        except Exception:
            pass

    # 3. 若為帶有 query 的網址，將中文解碼 (unquote)
    if "api=1&query=" in raw_url:
        match = re.search(r'query=([^&]+)', raw_url)
        if match:
            clean_q = urllib.parse.unquote(match.group(1))
            return f"https://maps.google.com/?q={clean_q}"

    # 4. 若無直接網址，以店名或地址產生簡短乾淨連結
    if not raw_url:
        target = lead_dict.get("name") or lead_dict.get("address") or ""
        if target:
            return f"https://maps.google.com/?q={target}"
        return ""

    # 5. 兜底：解碼所有百分比字元以還原純文字
    return urllib.parse.unquote(raw_url).split("&entry=")[0].split("?entry=")[0]

async def watch_case_resolutions():
    """
    背景輪詢監聽：
    1. 執行 30 分鐘停損檢查 (超時自動標記為尚無法確認)
    2. 當 Antigravity 獨立新對話破案並結案時，精確比對群友是否搶先答對，並回傳 Discord！
    """
    import time
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
                maps_url = extract_maps_url(lead)
                status = case_data.get("status")
                case_id = case_data.get("case_id")

                if channel_id and message_id:
                    channel = client.get_channel(channel_id)
                    if channel:
                        try:
                            msg = await channel.fetch_message(message_id)
                            # 情況 A: 30 分鐘停損
                            if status == "unconfirmed" or case_data.get("timeout_cutoff"):
                                await set_single_reaction(msg, "❓")
                                print(f"[貓貓偵探 ❓] 案件-{case_id} 達 30 分鐘停損，已在 Discord 標註 ❓ 表情。")

                            # 情況 B: 本地深度破案成功
                            elif name:
                                print(f"[貓貓偵探 🎯] 案件-{case_id} 本地破案成功，權威店名：【{name}】！正在比對群友是否搶先猜對...")
                                
                                core_keywords = [name]
                                parts = name.split()
                                if len(parts) > 1 and len(parts[0]) >= 2:
                                    core_keywords.append(parts[0])

                                correct_msg = None
                                try:
                                    async for history_msg in channel.history(after=msg, limit=50):
                                        if history_msg.author.bot:
                                            continue
                                        text_lower = history_msg.content.lower()
                                        if any(kw.lower() in text_lower for kw in core_keywords):
                                            correct_msg = history_msg
                                            break
                                except Exception as e:
                                    print(f"[貓貓偵探 ⚠️] 檢查頻道發言歷史失敗: {e}")

                                display_name = name if name.startswith("這是") else f"這是 {name}"
                                if correct_msg:
                                    try:
                                        await correct_msg.add_reaction("🎯")
                                        print(f"[貓貓偵探 👏] 群友【{correct_msg.author}】答對了！已加上 🎯 表情。")
                                    except Exception:
                                        pass

                                    time_diff = time.time() - correct_msg.created_at.timestamp()
                                    if time_diff > 180:
                                        print(f"[貓貓偵探 🤫] 群友答對超過 3 分鐘 (差 {time_diff:.1f} 秒)，只按表情不發文字打擾。")
                                        await set_single_reaction(msg, "✅")
                                        case_manager.mark_case_notified(json_path, case_data)
                                        continue

                                    reply_lines = [
                                        f"🎉 已被 {correct_msg.author.mention} 搶先答對囉！",
                                        display_name,
                                        maps_url
                                    ]
                                else:
                                    reply_lines = [display_name, maps_url]

                                if config.reply_footer:
                                    reply_lines.append(config.reply_footer)

                                await msg.reply("\n".join(reply_lines), mention_author=False)
                                await set_single_reaction(msg, "✅")
                                print(f"[貓貓偵探 🎉] 案件-{case_id} 已成功回傳 Discord！")
                        except Exception as e:
                            print(f"[貓貓偵探 ❌] 案件回報 Discord 失敗: {e}")
                case_manager.mark_case_notified(json_path, case_data)
        except Exception as e:
            print(f"[貓貓偵探 ⚠️] 監聽案件結案異常: {e}")
        await asyncio.sleep(5)

@client.event
async def on_ready():
    print("=" * 55)
    print(f"[+] 這哪家小貓偵探機器人已成功上線！🐾")
    print(f"[+] 機器人帳號: {client.user} (ID: {client.user.id})")
    print(f"[+] 觸發模式: 發圖標註 @這哪家 或 回覆照片 @這哪家")
    print(f"[+] 運作架構: 純本地秒驗證 + Antigravity 獨立新對話深度接力")
    print("=" * 55)
    client.loop.create_task(watch_case_resolutions())

@client.event
async def on_error(event, *args, **kwargs):
    err_text = traceback.format_exc()
    print(f"[💥 Discord 事件異常: {event}]\n{err_text}")

@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    is_mentioned = client.user in message.mentions
    if not is_mentioned and message.guild:
        bot_member = message.guild.get_member(client.user.id)
        if bot_member:
            bot_role_ids = {r.id for r in bot_member.roles}
            if any(r.id in bot_role_ids for r in message.role_mentions):
                is_mentioned = True
    if not is_mentioned and ("這哪家" in message.content or str(client.user.id) in message.content):
        is_mentioned = True

    image_attachments = [
        att for att in message.attachments
        if att.content_type and att.content_type.startswith("image/")
    ]

    # 情境 A: 使用者上傳照片同時 @機器人
    if image_attachments and is_mentioned:
        existing_case = case_manager.find_case_by_message(message.id)
        if existing_case:
            ex_lead = existing_case.get("leading_candidate", {}) or {}
            ex_name = ex_lead.get("name")
            ex_status = existing_case.get("status")
            if existing_case.get("resolved") and ex_name:
                display_name = ex_name if ex_name.startswith("這是") else f"這是 {ex_name}"
                reply_lines = [display_name, extract_maps_url(ex_lead)]
                if config.reply_footer:
                    reply_lines.append(config.reply_footer)
                await message.reply("\n".join(reply_lines), mention_author=False)
                await set_single_reaction(message, "✅")
                return
            elif ex_status == "investigating":
                await set_single_reaction(message, "🕵️")
                await message.reply(f"🐾 偵探貓貓正在為此照片進行深度微型物證排查（案件-{existing_case.get('case_id')}），請稍候片刻！", mention_author=False)
                return

        print(f"[貓貓偵探 📸] 收到來自【{message.author}】上傳的 {len(image_attachments)} 張照片！")
        for att in image_attachments:
            local_filename = f"{message.id}_{att.filename}"
            save_path = os.path.join(scratch_dir, local_filename)
            await att.save(save_path)
            print(f"[貓貓偵探 💾] 照片已下載暫存: {save_path} (大小: {att.size} bytes)")

            is_food, reason = await asyncio.to_thread(food_detector.is_food_image, save_path)
            if is_food:
                print(f"[貓貓偵探 🐟] 判定為美食照片 ({reason})！直接啟動找餐廳流程（不倒數）。")
                await start_investigation(message, save_path)
            else:
                print(f"[貓貓偵探 🐾] 判定非美食照片 ({reason})，略過處理。")
        return

    # 情境 B: 使用者回覆某則圖片訊息並 @機器人
    if is_mentioned and message.reference:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            ref_images = [
                att for att in ref_msg.attachments
                if att.content_type and att.content_type.startswith("image/")
            ]
            if ref_images:
                existing_case = case_manager.find_case_by_message(ref_msg.id)
                if existing_case:
                    ex_lead = existing_case.get("leading_candidate", {}) or {}
                    ex_name = ex_lead.get("name")
                    ex_status = existing_case.get("status")
                    if existing_case.get("resolved") and ex_name:
                        display_name = ex_name if ex_name.startswith("這是") else f"這是 {ex_name}"
                        reply_lines = [display_name, extract_maps_url(ex_lead)]
                        if config.reply_footer:
                            reply_lines.append(config.reply_footer)
                        await message.reply("\n".join(reply_lines), mention_author=False)
                        await set_single_reaction(message, "✅")
                        return
                    elif ex_status == "investigating":
                        await set_single_reaction(message, "🕵️")
                        await message.reply(f"🐾 偵探貓貓正在為此照片進行深度微型物證排查（案件-{existing_case.get('case_id')}），請稍候片刻！", mention_author=False)
                        return

                print(f"[貓貓偵探 📜] 抓取到被引用訊息【{ref_msg.id}】中的 {len(ref_images)} 張歷史照片！")
                for att in ref_images:
                    local_filename = f"{ref_msg.id}_{att.filename}"
                    save_path = os.path.join(scratch_dir, local_filename)
                    if not os.path.exists(save_path):
                        await att.save(save_path)

                    is_food, reason = await asyncio.to_thread(food_detector.is_food_image, save_path)
                    if is_food:
                        print(f"[貓貓偵探 🐟] 引用照片判定為美食 ({reason})！直接啟動找餐廳流程（不倒數）。")
                        await start_investigation(ref_msg, save_path)
                return
        except Exception as e:
            print(f"[貓貓偵探 ⚠️] 解析引用歷史訊息失敗: {e}")

    # 處理狀態查詢指令 (!status 或 @這哪家 status)
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

def main():
    if not config.bot_token or config.bot_token == "YOUR_DISCORD_BOT_TOKEN":
        print("[!] 尚未在 config.json 或環境變數中設定 DISCORD_BOT_TOKEN！")
        return

    client.run(config.bot_token)

if __name__ == "__main__":
    main()
