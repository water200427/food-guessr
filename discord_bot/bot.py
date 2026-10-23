from typing import List, Union, Optional
import os
import sys
import socket
import asyncio
import subprocess
import traceback
import builtins
import shutil
import re
import urllib.parse
from datetime import datetime

# 單一實例保證（防止多重開機或重複回覆）
_lock_socket = None
def ensure_single_instance():
    global _lock_socket
    if _lock_socket is not None:
        return True
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.bind(("127.0.0.1", 58421))
        return True
    except socket.error:
        print("[💥 啟動終止] 偵測到已有其他 Discord 機器人實例正在運行中 (Port 58421 被佔用)！為避免重複回覆，此實例自動退出。")
        sys.exit(0)

if __name__ == "__main__":
    ensure_single_instance()

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
from services.investigation_tracker import InvestigationTracker

config = DiscordBotConfig.load()
food_detector = FoodDetector(api_key=config.gemini_api_key)
case_manager = CaseManager()
investigation_tracker = InvestigationTracker()

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

async def start_investigation(message: discord.Message, image_paths: Union[str, List[str]], initial_hint: Optional[str] = None):
    """
    極速立案並觸發 Antigravity 自動開啟獨立調查新對話（支援單圖或多圖聯合排查，並納入使用者初始文字提示）
    """
    await set_single_reaction(message, "🕵️")

    if isinstance(image_paths, str):
        img_list = [image_paths]
    else:
        img_list = list(image_paths)

    clean_hint = initial_hint.strip() if initial_hint else None

    case_id = case_manager.create_case_from_discord(
        image_paths=img_list,
        channel_id=message.channel.id,
        message_id=message.id,
        author_name=str(message.author),
        guild_id=message.guild.id if message.guild else None,
        jump_url=message.jump_url,
        initial_hint=clean_hint
    )
    hint_desc = f"，並附帶初始提示：『{clean_hint}』" if clean_hint else ""
    print(f"[貓貓偵探 📋] 案件已建檔 (案件-{case_id}，共 {len(img_list)} 張照片{hint_desc})！Discord 已標註 🕵️ 表情。")

    # 自動呼叫 agentapi 為該案在 Antigravity 開啟全新獨立對話
    try:
        price_instruction = ""
        if getattr(config, "enable_price_estimation", True):
            price_instruction = (
                "【重要任務：菜單與價目表核對】若確認為實體餐廳與餐點，請進一步參考該店家在 Google Maps 最新（2025～2026年）之菜單/價目表照片，"
                "精確比對並盤點照片中的餐點品項名稱、規格份量與單價，計算出預估總金額（含幣別與服務費備註）。\n"
            )

        if len(img_list) > 1:
            img_bullets = "\n".join([f"  - 案件/案件-{case_id}/案件-{case_id}-Discord照片-{i}.jpg" for i in range(1, len(img_list) + 1)])
            images_section = (
                f"案件圖片（共 {len(img_list)} 張多視角物證照片）：\n{img_bullets}\n"
                f"💡 本案包含多視角線索（如環境裝潢、不同餐點或菜單局部），請交叉比對各照片特徵以高把握度破案！\n"
            )
        else:
            images_section = f"案件圖片：案件/案件-{case_id}/案件-{case_id}-Discord照片.jpg\n"

        hint_section = ""
        if clean_hint:
            hint_section = (
                f"💡【使用者提供之初始提示與線索】：\n"
                f"「{clean_hint}」\n"
                f"請嚴格納入判斷考量（例如地點、料理類別或特殊回憶），切勿忽視此關鍵提示！\n\n"
            )

        prompt = (
            f"你是 Antigravity 找餐廳小貓偵探。請嚴格依據 AGENTS.md 與 找餐廳判斷規則.md 調查【案件-{case_id}】。\n"
            f"{images_section}"
            f"{hint_section}"
            f"案件檔案：案件/案件-{case_id}/案件-{case_id}-Discord照片.md 與 案件/案件-{case_id}/案件-{case_id}.json\n"
            f"請利用本機 Chrome 9222、Google Lens、以圖搜尋與 Google Maps 進行深度微型物證排查，"
            f"核對近期營業狀態與器皿。\n"
            f"{price_instruction}"
            f"【手作自煮料理識別機制】：若排查無果且物證高度吻合居家生活環境（如電腦桌、家用非成套碗盤、家用紙巾盒或家用調味品），"
            f"請大膽判定為「這是自己手作的料理（自煮美食）」，填寫 is_restaurant=false、is_homemade=true，且不附 Google Maps 連結即可結案！\n"
            f"確認後更新 案件/案件-{case_id}/案件-{case_id}.json（填寫 leading_candidate、price_estimation、status='resolved'、resolved=true）"
            f"與對應的 .md 檔案（在結論中附帶餐點品項與價位試算）以完成結案！"
        )
        agentapi_bin = shutil.which("agentapi")
        if not agentapi_bin:
            default_bin = os.path.expanduser(r"~\.gemini\antigravity\bin\agentapi.bat")
            if os.path.exists(default_bin):
                agentapi_bin = default_bin
            else:
                agentapi_bin = "agentapi"

        cmd = ["cmd.exe", "/c", agentapi_bin, "new-conversation", f"--title=案件-{case_id} 調查", prompt]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0:
            print(f"[貓貓偵探 🚀] 已成功為【案件-{case_id}】自動開啟獨立調查新對話！")
        else:
            print(f"[貓貓偵探 ⚠️] 自動開啟新對話異常 (代碼 {res.returncode}): {res.stderr or res.stdout}")
    except Exception as e:
        print(f"[貓貓偵探 ⚠️] 呼叫 agentapi 失敗: {e}")

async def continue_investigation(message: discord.Message, case_id: str, new_images: Optional[List[str]] = None, user_hint: Optional[str] = None):
    """
    為既有案件（無論正在調查中或先前已停損）注入新照片或補充文字線索，並喚醒 Antigravity 開啟接續調查對話
    """
    await set_single_reaction(message, "🕵️")
    clean_hint = user_hint.strip() if user_hint else None
    new_img_list = list(new_images) if new_images else []

    try:
        added_img_section = ""
        if new_img_list:
            bullets = "\n".join([f"  - 案件/案件-{case_id}/{os.path.basename(p)}" for p in new_img_list])
            added_img_section = (
                f"📸 使用者在 Discord 追加了 {len(new_img_list)} 張全新多視角物證照片：\n"
                f"{bullets}\n"
                f"💡 請特別放大分析追加照片中的招牌菜色、器皿釉紋與微型細節！\n\n"
            )

        hint_section = ""
        if clean_hint:
            hint_section = (
                f"💡 使用者在 Discord 補充了最新關鍵線索：\n"
                f"「{clean_hint}」\n"
                f"請務必將此最新提示列為核心排查條件！\n\n"
            )

        price_instruction = ""
        if getattr(config, "enable_price_estimation", True):
            price_instruction = (
                "【重要任務：菜單與價目表核對】若確認為實體餐廳與餐點，請進一步參考該店家在 Google Maps 最新（2025～2026年）之菜單/價目表照片，"
                "精確比對並盤點照片中的餐點品項名稱、規格份量與單價，計算出預估總金額（含幣別與服務費備註）。\n"
            )

        prompt = (
            f"你是 Antigravity 找餐廳小貓偵探。【案件-{case_id} 追加線索與接續調查】\n"
            f"{added_img_section}"
            f"{hint_section}"
            f"案件檔案：案件/案件-{case_id}/案件-{case_id}-Discord照片.md 與 案件/案件-{case_id}/案件-{case_id}.json\n"
            f"請結合既有檔案與最新補充之物證/線索，利用本機 Chrome 9222、Google Lens、Google Maps 進行深度排查。\n"
            f"{price_instruction}"
            f"【重要寫檔順序】：調查確認後，必須先完整寫入 Markdown 報告（.md），確認已儲存硬碟後，"
            f"最後才更新 .json（填寫 leading_candidate、price_estimation、status='resolved'、resolved=true）以完成結案！"
        )

        agentapi_bin = shutil.which("agentapi")
        if not agentapi_bin:
            default_bin = os.path.expanduser(r"~\.gemini\antigravity\bin\agentapi.bat")
            if os.path.exists(default_bin):
                agentapi_bin = default_bin
            else:
                agentapi_bin = "agentapi"

        cmd = ["cmd.exe", "/c", agentapi_bin, "new-conversation", f"--title=案件-{case_id} 追加線索接續調查", prompt]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0:
            print(f"[貓貓偵探 🚀] 已為【案件-{case_id}】追加線索並自動開啟接續調查對話！")
        else:
            print(f"[貓貓偵探 ⚠️] 開啟接續調查對話異常 (代碼 {res.returncode}): {res.stderr or res.stdout}")
    except Exception as e:
        print(f"[貓貓偵探 ⚠️] 呼叫 agentapi 接續調查失敗: {e}")

def is_homemade_meal(lead_dict: dict) -> bool:
    """
    精準判斷是否為個人居家自煮手作料理，杜絕將「XX手作烘焙」、「XX家常牛肉麵」或「超商外帶商品」等誤判。
    """
    if not lead_dict or not isinstance(lead_dict, dict):
        return False

    # 防線 1: 若明確標註為實體餐廳或超商/零售外帶，絕非居家自煮
    if lead_dict.get("is_restaurant") is True:
        return False
    if lead_dict.get("is_retail") is True or lead_dict.get("is_takeout") is True:
        return False

    name = lead_dict.get("name", "")
    # 防線 2: 若名稱包含超商、便利商店、賣場或明確連鎖品牌，絕非自煮
    retail_phrases = ["7-Eleven", "7-11", "全家", "萊爾富", "OK超商", "超商", "便利商店", "全聯", "好市多", "Costco", "家樂福", "超市"]
    if any(rp.lower() in name.lower() for rp in retail_phrases):
        return False

    # 正向特徵 1: 明確標註為自煮手作
    if lead_dict.get("is_homemade") is True:
        return True

    # 正向特徵 2: 店名包含高置信度「自煮自製」專屬片語（杜絕單字「手作」或「家常」誤傷真實店家，嚴禁包含「非餐廳」）
    homemade_phrases = [
        "自己手作", "自己煮", "自己做", "自煮料理", "自煮美食",
        "親手做", "親手烹調", "親手製作", "自家手作", "自家烹飪",
        "自煮家常", "自製家常", "自己烘焙", "居家自煮"
    ]
    if any(phrase in name for phrase in homemade_phrases):
        # 若同時具備明確 Google Maps 連結，仍視為實體店家（避免 AI 寫錯店名）
        raw_url = (lead_dict.get("google_maps_url") or lead_dict.get("maps_url") or "").strip()
        if raw_url and ("maps.app.goo.gl" in raw_url or "cid=" in raw_url):
            return False
        return True

    return False

def extract_maps_url(lead_dict: dict) -> str:
    """
    穩健且乾淨地提取 Google Maps 連結：
    優先產生乾淨短網址 (maps.app.goo.gl 或 ?cid=)，絕不包含 %E... 冗長文字編碼，避免通訊軟體解析錯誤
    """
    if not lead_dict:
        return ""
    import re
    import urllib.parse

    # 0. 若經研判確認為個人自煮料理或非實體餐廳/超商外帶，絕對不產生特定 Google 地點連結
    if is_homemade_meal(lead_dict) or lead_dict.get("is_restaurant") is False:
        return ""
    name_check = lead_dict.get("name", "")
    if any(k in name_check for k in ["非餐廳", "非實體", "超商外帶"]):
        return ""

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

    # 4. 若無直接網址但有明確實體地址或特定餐廳店名時，產生簡短乾淨連結
    if not raw_url:
        target = lead_dict.get("address") or lead_dict.get("name") or ""
        if target and not any(k in target for k in ["非餐廳", "非實體", "直播", "未確認", "自己手作", "自己煮", "自煮料理"]):
            return f"https://maps.google.com/?q={target}"
        return ""

    # 5. 兜底：解碼所有百分比字元以還原純文字
    return urllib.parse.unquote(raw_url).split("&entry=")[0].split("?entry=")[0]

def format_price_estimation(case_data: dict) -> list:
    """
    從案件資料中提取並排版餐點品項與總價估算
    選配開關受 config.enable_price_estimation 控制（預設為開）
    """
    if not getattr(config, "enable_price_estimation", True):
        return []

    lines = []
    lead = case_data.get("leading_candidate", {}) or {}

    pe = case_data.get("price_estimation") or {}
    if not pe and isinstance(lead, dict) and lead.get("price_estimation"):
        pe = lead.get("price_estimation") or {}

    items = pe.get("items") or []
    total_price = pe.get("total_price")
    currency = pe.get("currency", "NT$")
    if currency == "TWD":
        currency = "NT$"
    elif currency == "JPY":
        currency = "¥"

    menu_date = pe.get("menu_date", "")
    notes = pe.get("notes") or pe.get("additional_fees_note", "")

    # 向下相容：若根層級沒有 items，但 leading_candidate 內有 dish 或 estimated_total
    lead_dish = lead.get("dish") if isinstance(lead, dict) else None
    lead_total = lead.get("estimated_total") if isinstance(lead, dict) else None

    # [關鍵防禦] 若完全沒有具體品項，且確認為自煮手作料理，才顯示自家用心烹飪
    if not items and not lead_dish and isinstance(lead, dict) and is_homemade_meal(lead):
        return ["🍳 **餐點資訊**：自家用心烹飪，愛心無價 ❤️"]

    if not items and isinstance(lead, dict) and (lead_dish or lead_total):
        lines.append("💰 **餐點品項與預估價格**：")
        if lead_dish:
            lines.append(f"• {lead_dish}")
        if lead_total:
            lines.append(f"👉 **預估總計：約 {lead_total}**")
        return lines

    if not items and total_price is None:
        return lines

    date_str = f"（{menu_date} 最新菜單）" if menu_date else "（參考最新菜單）"
    lines.append(f"💰 **菜單品項與預估總價**{date_str}：")

    price_prefix = "¥" if currency == "¥" else ("$" if currency in ["NT$", "$"] else f"{currency} ")

    has_item_price = False
    for item in items:
        name = item.get("name", "餐點")
        spec = (item.get("spec") or item.get("specification") or "").strip()
        qty = item.get("quantity", 1)
        unit_price = item.get("unit_price")
        subtotal = item.get("subtotal")

        # 極簡清爽排版：規格僅在簡短（<= 8 字，如大碗/190g）且未重複於品項名時顯示；長篇描述留於 !report 報告
        spec_str = f"（{spec}）" if spec and len(spec) <= 8 and spec not in name else ""
        qty_str = f" × {qty}" if qty and qty > 1 else ""
        if subtotal is not None:
            price_str = f"：{price_prefix}{subtotal}"
            has_item_price = True
        elif unit_price is not None:
            price_str = f"：{price_prefix}{unit_price}"
            has_item_price = True
        else:
            price_str = ""

        lines.append(f"• {name}{spec_str}{qty_str}{price_str}")

    # 若只有單一品項且已清楚標示價格，不重複輸出總計行（保留 12:59 極簡清爽風格）；僅在多品項或未標單價時輸出
    if len(items) > 1 or not has_item_price:
        if total_price is not None:
            fee_str = f" ({notes})" if notes else ""
            if isinstance(total_price, (int, float)):
                lines.append(f"👉 **預估總計：約 {currency} {total_price:,.0f}**{fee_str}")
            else:
                lines.append(f"👉 **預估總計：約 {total_price}**{fee_str}")
        elif notes:
            lines.append(f"👉 **備註**：{notes}")

    return lines


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
                if isinstance(lead, str):
                    lead = {"name": lead}
                name = lead.get("name", "").strip()
                maps_url = extract_maps_url(lead)
                status = case_data.get("status")
                case_id = case_data.get("case_id")

                if channel_id and message_id:
                    channel = client.get_channel(channel_id)
                    if channel:
                        try:
                            msg = await channel.fetch_message(message_id)
                            jump_url = getattr(msg, "jump_url", None) or case_manager.get_case_jump_url(case_data, default_guild_id=msg.guild.id if msg and msg.guild else None)

                            # 情況 A: 30 分鐘停損
                            if status == "unconfirmed" or case_data.get("timeout_cutoff"):
                                await set_single_reaction(msg, "❓")
                                print(f"[貓貓偵探 ❓] 案件-{case_id} 達 30 分鐘停損，已在 Discord 標註 ❓ 表情。")

                                # 向原頻道發送友善停損回報，避免群友乾等
                                try:
                                    timeout_reply = (
                                        f"🐾 **【案件-{case_id} 調查停損通知】**\n"
                                        f"此案微型物證排查已達 30 分鐘時限，現有照片特徵尚不足以百分之百鎖定單一店家（已標註 ❓）。\n"
                                        f"💡 若有額外的拍攝地點、其他角度照片或回憶線索，歡迎隨時補充！🐾"
                                    )
                                    await msg.reply(timeout_reply, mention_author=False)
                                except Exception as te:
                                    print(f"[貓貓偵探 ⚠️] 原頻道發送停損通知失敗: {te}")

                                if config.log_channel_id:
                                    try:
                                        log_ch = client.get_channel(config.log_channel_id) or await client.fetch_channel(config.log_channel_id)
                                        if log_ch:
                                            timeout_lines = [
                                                f"❓ **【案件-{case_id} 調查停損（尚無法確認）】**",
                                                f"⏳ 已達 30 分鐘調查停損時限，待後續補充線索。"
                                            ]
                                            if jump_url:
                                                timeout_lines.append(f"🔗 **原始照片訊息**：[點此跳轉原圖訊息]({jump_url})")
                                            await log_ch.send("\n".join(timeout_lines))
                                    except Exception as le:
                                        print(f"[貓貓偵探 ⚠️] 日誌頻道發送停損通報失敗: {le}")

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
                                        display_name
                                    ]
                                else:
                                    reply_lines = [display_name]

                                # 取得該案 Markdown 報告檔案並自動同步 GitHub (Public)
                                md_path = case_manager.get_case_md_path(case_id, json_path)
                                github_url = None
                                if md_path:
                                    try:
                                        await asyncio.to_thread(case_manager.git_commit_and_push, case_id)
                                    except Exception as ge:
                                        print(f"[貓貓偵探 ⚠️] 自動 push GitHub 異常: {ge}")
                                    github_url = case_manager.get_github_md_url(md_path)

                                if maps_url:
                                    reply_lines.append(maps_url)

                                price_lines = format_price_estimation(case_data)
                                if price_lines:
                                    reply_lines.extend(price_lines)

                                # 依據設定決定是否自動附帶 Markdown 報告附件 (預設先取消展示，保持回覆清爽)
                                file_attachment = None
                                if getattr(config, "auto_attach_report", False):
                                    if github_url:
                                        reply_lines.append(f"📝 調查報告：{github_url}")
                                    if md_path and os.path.exists(md_path):
                                        file_attachment = discord.File(md_path, filename=os.path.basename(md_path))
                                else:
                                    reply_lines.append(f"*(輸入 `!report` 或 `!report {case_id}` 可調出完整調查報告)*")

                                if config.reply_footer:
                                    reply_lines.append(config.reply_footer)

                                if file_attachment:
                                    await msg.reply("\n".join(reply_lines), file=file_attachment, mention_author=False)
                                else:
                                    await msg.reply("\n".join(reply_lines), mention_author=False)
                                await set_single_reaction(msg, "✅")
                                print(f"[貓貓偵探 🎉] 案件-{case_id} 已成功回傳 Discord！")

                                # 同步向專屬日誌頻道發送結案通報（附帶跳轉原始照片訊息之連結）
                                if config.log_channel_id:
                                    try:
                                        log_ch = client.get_channel(config.log_channel_id) or await client.fetch_channel(config.log_channel_id)
                                        if log_ch:
                                            log_summary_lines = [
                                                f"🎯 **【案件-{case_id} 結案通報】**",
                                                f"🏠 **店名**：**{name}**"
                                            ]
                                            if maps_url:
                                                log_summary_lines.append(f"📍 **地點**：{maps_url}")
                                            price_lines = format_price_estimation(case_data)
                                            if price_lines:
                                                log_summary_lines.extend(price_lines)
                                            if jump_url:
                                                log_summary_lines.append(f"🔗 **原始照片訊息**：[點此跳轉原圖訊息]({jump_url})")
                                            await log_ch.send("\n".join(log_summary_lines))
                                    except Exception as le:
                                        print(f"[貓貓偵探 ⚠️] 日誌頻道發送結案通報失敗: {le}")
                        except Exception as e:
                            print(f"[貓貓偵探 ❌] 案件回報 Discord 失敗: {e}")
                case_manager.mark_case_notified(json_path, case_data)
        except Exception as e:
            print(f"[貓貓偵探 ⚠️] 監聽案件結案異常: {e}")
        await asyncio.sleep(5)

def get_sanitized_logs(max_lines: int = 15) -> str:
    """
    讀取最新 log 並進行安全脫敏（自動替換本機 Windows 路徑為相對路徑）
    """
    if not os.path.exists(LOG_FILE_PATH):
        return "（目前尚無日誌檔案）"
    try:
        with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        if not lines:
            return "（日誌內容為空）"
        selected = lines[-max_lines:]
        content = "".join(selected)

        # 隱私脫敏：替換專案絕對路徑為相對路徑
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        content = content.replace(project_root, ".")
        content = content.replace(project_root.replace("\\", "/"), ".")

        # 隱私脫敏：替換使用者本機目錄 (如 C:\Users\water\...)
        import re
        content = re.sub(r"[a-zA-Z]:[/\\][Uu]sers[/\\][^\s/\\\"']+", "~", content)

        # 控制長度不超過 Discord 2000 字元上限
        if len(content) > 1800:
            content = content[-1800:]
            first_newline = content.find("\n")
            if first_newline != -1:
                content = content[first_newline + 1:]
        return content.strip()
    except Exception as e:
        return f"讀取日誌失敗: {e}"

async def stream_logs_to_channel():
    """
    背景任務：每 2~3 秒檢查 scratch/bot.log，若有新紀錄且已設定 log_channel_id，
    自動安全脫敏後同步發送至專屬日誌頻道！
    """
    await client.wait_until_ready()
    last_pos = 0
    if os.path.exists(LOG_FILE_PATH):
        try:
            last_pos = os.path.getsize(LOG_FILE_PATH)
        except Exception:
            last_pos = 0

    while not client.is_closed():
        try:
            if config.log_channel_id and os.path.exists(LOG_FILE_PATH):
                current_size = os.path.getsize(LOG_FILE_PATH)
                if current_size < last_pos:
                    last_pos = 0

                if current_size > last_pos:
                    with open(LOG_FILE_PATH, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(last_pos)
                        new_content = f.read()
                        last_pos = f.tell()

                    if new_content.strip():
                        # 安全脫敏
                        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                        sanitized = new_content.replace(project_root, ".")
                        sanitized = sanitized.replace(project_root.replace("\\", "/"), ".")
                        import re
                        sanitized = re.sub(r"[a-zA-Z]:[/\\][Uu]sers[/\\][^\s/\\\"']+", "~", sanitized)

                        # 切割成每段最多 1750 字元
                        lines = sanitized.strip().splitlines()
                        chunks = []
                        current_chunk = []
                        current_len = 0
                        for line in lines:
                            if current_len + len(line) + 1 > 1750:
                                chunks.append("\n".join(current_chunk))
                                current_chunk = [line]
                                current_len = len(line)
                            else:
                                current_chunk.append(line)
                                current_len += len(line) + 1
                        if current_chunk:
                            chunks.append("\n".join(current_chunk))

                        # 取得頻道發送
                        target_channel = client.get_channel(config.log_channel_id)
                        if not target_channel:
                            try:
                                target_channel = await client.fetch_channel(config.log_channel_id)
                            except Exception:
                                target_channel = None

                        if target_channel:
                            for chk in chunks:
                                await target_channel.send(f"```log\n{chk}\n```")
        except Exception:
            pass
        await asyncio.sleep(2.5)

async def monitor_investigation_progress():
    """
    即時調查進度轉播任務：
    每 2~3 秒檢查進行中案件的 Antigravity 對話動態，
    自動轉播前線戰報至 #偵探日誌，並動態切換原訊息的表情符號 (🕵️ ➜ 🔍 ➜ 🗺️ ➜ ✍️)
    """
    await client.wait_until_ready()
    case_emojis: dict = {}

    while not client.is_closed():
        try:
            active_cases = case_manager.get_investigating_cases()
            for c in active_cases:
                case_id = c.get("case_id")
                if not case_id:
                    continue

                reports, new_emoji = investigation_tracker.poll_case_updates(case_id)
                # 1. 輸出前線戰報（將自動推播至 #偵探日誌 頻道）
                for r in reports:
                    bot_print(f"[貓貓偵探 🐾 案件-{case_id}] {r}")

                # 2. 若調查階段推進，切換原訊息上的表情 (🕵️ ➜ 🔍 ➜ 🗺️ ➜ ✍️)
                if new_emoji and case_emojis.get(case_id) != new_emoji:
                    case_emojis[case_id] = new_emoji
                    meta = c.get("discord_meta", {})
                    channel_id = meta.get("channel_id")
                    message_id = meta.get("message_id")
                    if channel_id and message_id:
                        try:
                            channel = client.get_channel(channel_id)
                            if not channel:
                                channel = await client.fetch_channel(channel_id)
                            if channel:
                                msg = await channel.fetch_message(message_id)
                                await set_single_reaction(msg, new_emoji)
                        except Exception:
                            pass
        except Exception:
            pass
        await asyncio.sleep(2.5)

@client.event
async def on_ready():
    if getattr(client, "_tasks_started", False):
        return
    client._tasks_started = True

    print("=" * 55)
    print(f"[+] 這哪家小貓偵探機器人已成功上線！🐾")
    print(f"[+] 機器人帳號: {client.user} (ID: {client.user.id})")
    print(f"[+] 觸發模式: 發圖標註 @這哪家 或 回覆照片 @這哪家")
    print(f"[+] 運作架構: 純本地秒驗證 + Antigravity 獨立新對話深度接力")
    if config.log_channel_id:
        print(f"[+] 專屬日誌轉播頻道已設定: ID {config.log_channel_id}")
    else:
        print(f"[+] 尚未綁定日誌頻道 (可在目標頻道輸入 !setlogchannel 開啟轉播)")
    print("=" * 55)
    client.loop.create_task(watch_case_resolutions())
    client.loop.create_task(stream_logs_to_channel())
    client.loop.create_task(monitor_investigation_progress())

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

    # 提取乾淨的使用者文字提示 (去除 mention 與機器人呼喚詞)
    raw_content = message.content or ""
    clean_user_text = re.sub(r"<@!?\d+>", "", raw_content)
    clean_user_text = re.sub(r"\b這哪家\b", "", clean_user_text, flags=re.IGNORECASE).strip()

    image_attachments = [
        att for att in message.attachments
        if att.content_type and att.content_type.startswith("image/")
    ]

    # =========================================================================
    # 核心智慧分支 1: 回覆既有案件（回覆原照片訊息 或 回覆停損/立案/結案通知）
    # =========================================================================
    ref_case = None
    ref_msg = None
    if message.reference and message.reference.message_id:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            if ref_msg:
                # 判定被回覆的是否為既有案件 (支援原發圖、機器人通知、或二次引用)
                ref_ref_id = ref_msg.reference.message_id if ref_msg.reference else None
                ref_case = case_manager.find_case_by_reply(
                    ref_msg_id=ref_msg.id,
                    ref_msg_content=ref_msg.content or "",
                    ref_ref_id=ref_ref_id
                )
        except Exception as re_err:
            print(f"[貓貓偵探 ⚠️] 讀取被引用訊息失敗: {re_err}")

    if ref_case:
        target_cid = ref_case.get("case_id")

        # 子情境 1.1: 回覆時帶有新照片 ➜ 視為同案件追加新角度照片（絕不另立新案！）
        if image_attachments:
            print(f"[貓貓偵探 🔄] 偵測到針對【案件-{target_cid}】追加上傳 {len(image_attachments)} 張新照片！")
            valid_paths = []
            for att in image_attachments:
                local_filename = f"{message.id}_{att.filename}"
                save_path = os.path.join(scratch_dir, local_filename)
                await att.save(save_path)
                is_food, reason = await asyncio.to_thread(food_detector.is_food_image, save_path)
                if is_food:
                    valid_paths.append(save_path)
                else:
                    print(f"[貓貓偵探 🐾] 追加照片 {att.filename} 判定非有效照片 ({reason})，略過。")

            if valid_paths:
                case_manager.append_evidence_to_case(
                    case_id=target_cid,
                    new_image_paths=valid_paths,
                    user_hint=clean_user_text if clean_user_text else None,
                    message_id=message.id,
                    author_name=str(message.author)
                )
                await continue_investigation(
                    message=message,
                    case_id=target_cid,
                    new_images=valid_paths,
                    user_hint=clean_user_text
                )
                reply_txt = f"🐾 已為【案件-{target_cid}】追加 {len(valid_paths)} 張新角度物證照片"
                if clean_user_text:
                    reply_txt += f"，並同步記錄補充線索：『{clean_user_text}』"
                reply_txt += "！偵探貓貓已全速重啟接續排查中～🕵️"
                await message.reply(reply_txt, mention_author=False)
                return

        # 子情境 1.2: 回覆時無新照片，但有補充文字提示（非指令） ➜ 追加線索並喚醒排查
        if clean_user_text and not clean_user_text.startswith("!"):
            print(f"[貓貓偵探 💡] 偵測到針對【案件-{target_cid}】提供補充文字線索：『{clean_user_text}』！")
            case_manager.append_evidence_to_case(
                case_id=target_cid,
                new_image_paths=None,
                user_hint=clean_user_text,
                message_id=message.id,
                author_name=str(message.author)
            )
            await continue_investigation(
                message=message,
                case_id=target_cid,
                new_images=None,
                user_hint=clean_user_text
            )
            reply_txt = f"🐾 已為【案件-{target_cid}】收到補充線索：『{clean_user_text}』！偵探貓貓正在結合新線索全力深入排查中～🕵️"
            await message.reply(reply_txt, mention_author=False)
            return

        # 子情境 1.3: 純引用案件訊息但未附帶新物證或提示 (且有 @機器人) ➜ 回報目前進度或既有報告
        if is_mentioned:
            ex_lead = ref_case.get("leading_candidate", {}) or {}
            ex_name = ex_lead.get("name") if isinstance(ex_lead, dict) else str(ex_lead)
            ex_status = ref_case.get("status")
            if ref_case.get("resolved") and ex_name:
                display_name = ex_name if ex_name.startswith("這是") else f"這是 {ex_name}"
                reply_lines = [display_name]
                ex_maps = extract_maps_url(ex_lead)
                if ex_maps:
                    reply_lines.append(ex_maps)
                price_lines = format_price_estimation(ref_case)
                if price_lines:
                    reply_lines.extend(price_lines)
                ex_json_path = ref_case.get("_json_path")
                ex_md_path = case_manager.get_case_md_path(target_cid, ex_json_path)
                ex_file = None
                if getattr(config, "auto_attach_report", False):
                    if ex_md_path:
                        ex_gh_url = case_manager.get_github_md_url(ex_md_path)
                        if ex_gh_url:
                            reply_lines.append(f"📝 調查報告：{ex_gh_url}")
                        if os.path.exists(ex_md_path):
                            ex_file = discord.File(ex_md_path, filename=os.path.basename(ex_md_path))
                else:
                    reply_lines.append(f"*(輸入 `!report` 或 `!report {target_cid}` 可調出完整調查報告)*")

                if config.reply_footer:
                    reply_lines.append(config.reply_footer)
                if ex_file:
                    await message.reply("\n".join(reply_lines), file=ex_file, mention_author=False)
                else:
                    await message.reply("\n".join(reply_lines), mention_author=False)
                await set_single_reaction(message, "✅")
                return
            elif ex_status == "investigating":
                await set_single_reaction(message, "🕵️")
                await message.reply(f"🐾 偵探貓貓正在為此照片進行深度微型物證排查（案件-{target_cid}），請稍候片刻！", mention_author=False)
                return

    # =========================================================================
    # 核心智慧分支 2: 全新發起案件 (上傳照片同時 @機器人，支援初始文字提示)
    # =========================================================================
    if image_attachments and is_mentioned:
        existing_case = case_manager.find_case_by_message(message.id)
        if existing_case:
            ex_lead = existing_case.get("leading_candidate", {}) or {}
            ex_name = ex_lead.get("name")
            ex_status = existing_case.get("status")
            if existing_case.get("resolved") and ex_name:
                display_name = ex_name if ex_name.startswith("這是") else f"這是 {ex_name}"
                reply_lines = [display_name]
                ex_maps = extract_maps_url(ex_lead)
                if ex_maps:
                    reply_lines.append(ex_maps)
                price_lines = format_price_estimation(existing_case)
                if price_lines:
                    reply_lines.extend(price_lines)
                ex_case_id = existing_case.get("case_id")
                ex_json_path = existing_case.get("_json_path")
                ex_md_path = case_manager.get_case_md_path(ex_case_id, ex_json_path)
                ex_file = None
                if getattr(config, "auto_attach_report", False):
                    if ex_md_path:
                        ex_gh_url = case_manager.get_github_md_url(ex_md_path)
                        if ex_gh_url:
                            reply_lines.append(f"📝 調查報告：{ex_gh_url}")
                        if os.path.exists(ex_md_path):
                            ex_file = discord.File(ex_md_path, filename=os.path.basename(ex_md_path))
                else:
                    reply_lines.append(f"*(輸入 `!report` 或 `!report {ex_case_id}` 可調出完整調查報告)*")

                if config.reply_footer:
                    reply_lines.append(config.reply_footer)
                if ex_file:
                    await message.reply("\n".join(reply_lines), file=ex_file, mention_author=False)
                else:
                    await message.reply("\n".join(reply_lines), mention_author=False)
                await set_single_reaction(message, "✅")
                return
            elif ex_status == "investigating":
                await set_single_reaction(message, "🕵️")
                await message.reply(f"🐾 偵探貓貓正在為此照片進行深度微型物證排查（案件-{existing_case.get('case_id')}），請稍候片刻！", mention_author=False)
                return

        hint_info = f"，附帶提示：『{clean_user_text}』" if clean_user_text else ""
        print(f"[貓貓偵探 📸] 收到來自【{message.author}】上傳的 {len(image_attachments)} 張照片{hint_info}！")
        valid_paths = []
        for att in image_attachments:
            local_filename = f"{message.id}_{att.filename}"
            save_path = os.path.join(scratch_dir, local_filename)
            await att.save(save_path)
            print(f"[貓貓偵探 💾] 照片已下載暫存: {save_path} (大小: {att.size} bytes)")

            is_food, reason = await asyncio.to_thread(food_detector.is_food_image, save_path)
            if is_food:
                valid_paths.append(save_path)
            else:
                print(f"[貓貓偵探 🐾] 照片 {att.filename} 判定非有效照片 ({reason})，略過。")

        if valid_paths:
            print(f"[貓貓偵探 🐟] 共 {len(valid_paths)} 張有效照片！直接啟動找餐廳同案排查流程。")
            await start_investigation(message, valid_paths, initial_hint=clean_user_text if clean_user_text else None)
        return

    # =========================================================================
    # 核心智慧分支 3: 回覆未立案之歷史圖片訊息並 @機器人
    # =========================================================================
    if is_mentioned and message.reference:
        try:
            ref_msg = await message.channel.fetch_message(message.reference.message_id)
            ref_images = [
                att for att in ref_msg.attachments
                if att.content_type and att.content_type.startswith("image/")
            ]
            if ref_images:
                print(f"[貓貓偵探 📜] 抓取到被引用訊息【{ref_msg.id}】中的 {len(ref_images)} 張歷史照片！")
                valid_paths = []
                for att in ref_images:
                    local_filename = f"{ref_msg.id}_{att.filename}"
                    save_path = os.path.join(scratch_dir, local_filename)
                    if not os.path.exists(save_path):
                        await att.save(save_path)

                    is_food, reason = await asyncio.to_thread(food_detector.is_food_image, save_path)
                    if is_food:
                        valid_paths.append(save_path)

                if valid_paths:
                    print(f"[貓貓偵探 🐟] 引用照片共 {len(valid_paths)} 張有效！直接啟動找餐廳同案排查流程。")
                    await start_investigation(ref_msg, valid_paths, initial_hint=clean_user_text if clean_user_text else None)
                return
        except Exception as e:
            print(f"[貓貓偵探 ⚠️] 解析引用歷史訊息失敗: {e}")

    # 處理狀態與日誌查詢指令 (!status, !log, !logs, !logfile)
    if message.content:
        clean_content = message.content.strip().lower()

        # 0. 菜單價格試算選配開關指令 (!price, !price on/off 或 @這哪家 price)
        if clean_content.startswith("!price") or (is_mentioned and "price" in clean_content):
            parts = clean_content.split()
            arg = parts[1] if len(parts) > 1 else ""
            if arg in ("on", "true", "enable", "開"):
                config.enable_price_estimation = True
                config.save()
                await message.reply("✅ **已開啟【參考最新菜單顯示品項並計算總價格】功能！**\n後續結案將會自動核對最新菜單並試算消費金額。🐾", mention_author=False)
            elif arg in ("off", "false", "disable", "關"):
                config.enable_price_estimation = False
                config.save()
                await message.reply("🛑 **已關閉【參考最新菜單顯示品項並計算總價格】功能！**\n後續結案將只顯示店名與地點連結。🐾", mention_author=False)
            else:
                config.enable_price_estimation = not config.enable_price_estimation
                config.save()
                st_str = "開啟 ✅" if config.enable_price_estimation else "關閉 🛑"
                await message.reply(f"💰 目前菜單價格試算功能狀態為：**{st_str}**\n*(可輸入 `!price on` 或 `!price off` 明確設定)*", mention_author=False)
            return

        # 1. 設定專屬日誌轉播頻道 (!setlogchannel, !bindlog 或 @這哪家 setlog)
        if clean_content.startswith("!setlogchannel") or clean_content.startswith("!bindlog") or (is_mentioned and "setlog" in clean_content):
            config.log_channel_id = message.channel.id
            config.save()
            ch_name = getattr(message.channel, "name", str(message.channel.id))
            await message.reply(
                f"✅ **已成功將此頻道（#{ch_name}）設定為專屬日誌頻道！**\n"
                f"📡 後續所有貓貓偵探的即時物證分析、CoT 排查進度與系統日誌將會在此頻道同步轉播！🐾",
                mention_author=False
            )
            print(f"[貓貓偵探 📡] 已設定專屬日誌頻道: #{ch_name} (ID: {message.channel.id})")
            return

        # 2. 解除專屬日誌頻道 (!unsetlogchannel 或 @這哪家 unsetlog)
        if clean_content.startswith("!unsetlogchannel") or (is_mentioned and "unsetlog" in clean_content):
            config.log_channel_id = None
            config.save()
            await message.reply("🛑 已解除專屬日誌頻道綁定，停止日誌轉播！", mention_author=False)
            print("[貓貓偵探 🛑] 已解除專屬日誌頻道綁定。")
            return

        # 3. 處理調查報告調出指令 (!report, !rep, 或 @這哪家 report)
        if clean_content.startswith("!report") or clean_content.startswith("!rep") or (is_mentioned and "report" in clean_content):
            target_case = None

            # 情境 A: 使用者引用了一則特定的歷史訊息
            if message.reference and message.reference.message_id:
                target_case = case_manager.find_case_by_message(message.reference.message_id)

            # 情境 B: 解析參數進行智慧查詢 (空字串 ➜ 最新一案；關鍵字 ➜ 編號、店名、品項模糊比對)
            raw_query = ""
            if not target_case:
                import re
                raw_query = re.sub(r"^(!report|!rep|<@!?\d+>\s*report)\s*", "", message.content.strip(), flags=re.IGNORECASE).strip()
                target_case = case_manager.find_case_by_query(raw_query)

            if target_case:
                cid = target_case.get("case_id")
                json_path = target_case.get("_json_path")
                md_path = case_manager.get_case_md_path(cid, json_path)
                github_url = case_manager.get_github_md_url(md_path) if md_path else ""

                lead = target_case.get("leading_candidate", {}) or {}
                if isinstance(lead, str):
                    lead = {"name": lead}
                c_name = lead.get("name") or target_case.get("case_title") or f"案件-{cid}"

                rep_lines = [
                    f"📄 **【案件-{cid} 調查報告】{c_name}**"
                ]
                if github_url:
                    rep_lines.append(f"📝 GitHub 線上公開閱讀：{github_url}")

                file_att = None
                if md_path and os.path.exists(md_path):
                    file_att = discord.File(md_path, filename=os.path.basename(md_path))

                if file_att:
                    await message.reply("\n".join(rep_lines), file=file_att, mention_author=False)
                else:
                    await message.reply("\n".join(rep_lines), mention_author=False)
                return
            else:
                # 查無結果，友善提示最近結案清單
                recent = case_manager.get_recent_resolved_cases(limit=3)
                suggestions = []
                for rc in recent:
                    rc_id = rc.get("case_id")
                    rc_lead = rc.get("leading_candidate", {}) or {}
                    if isinstance(rc_lead, str):
                        rc_lead = {"name": rc_lead}
                    rc_name = rc_lead.get("name") or f"案件-{rc_id}"
                    short_name = rc_name[:25] + "..." if len(rc_name) > 25 else rc_name
                    suggestions.append(f"• 案件-{rc_id}: **{short_name}** (可輸入 `!report {rc_id}`)")

                sugg_text = "\n".join(suggestions)
                not_found_msg = (
                    f"⚠️ 找不到與「{raw_query}」相關的案件調查報告！\n\n"
                    f"💡 **最近結案的案件有**：\n{sugg_text}\n\n"
                    f"*(直接輸入 `!report` 可調出最新一案報告)*"
                )
                await message.reply(not_found_msg, mention_author=False)
                return

        # 4. 處理日誌查詢指令 (!log, !logs, !logfile 或 @這哪家 log)
        if clean_content.startswith("!log") or (is_mentioned and "log" in clean_content):
            # 情境 A: 請求完整日誌檔附件 (!logfile, !log file, !log all)
            if "file" in clean_content or "all" in clean_content:
                if os.path.exists(LOG_FILE_PATH):
                    file_attachment = discord.File(LOG_FILE_PATH, filename="bot.log")
                    await message.reply("📑 這是貓貓偵探目前的完整執行日誌：", file=file_attachment, mention_author=False)
                else:
                    await message.reply("⚠️ 目前尚無日誌檔案！", mention_author=False)
                return

            # 情境 B: 顯示最新幾行日誌 (預設 15 行，支援 !log 20、!log 30)
            import re
            lines_count = 15
            match = re.search(r"log\w*\s+(\d+)", clean_content)
            if match:
                try:
                    lines_count = max(3, min(35, int(match.group(1))))
                except Exception:
                    lines_count = 15

            logs = get_sanitized_logs(lines_count)
            reply_text = (
                f"📜 **貓貓偵探執行日誌 (最新 {lines_count} 行)**：\n"
                f"```log\n{logs}\n```\n"
                f"*(提示：在目標頻道輸入 `!setlogchannel` 可開啟即時自動轉播；亦可輸入 `!logfile` 取得完整日誌檔)*"
            )
            await message.reply(reply_text, mention_author=False)
            return

        # 4. 處理狀態查詢指令 (!status 或 @這哪家 status)
        if "!status" in clean_content or (is_mentioned and "status" in clean_content):
            active_cases = case_manager.get_investigating_cases()
            if active_cases:
                cases_str = "、".join([f"案件-{c.get('case_id')}" for c in active_cases])
                await message.reply(f"📋 目前共有 {len(active_cases)} 個疑難案件正在由 Antigravity 進行深度微型物證排查中：\n`{cases_str}`\n*(可輸入 `!log` 查看目前即時日誌)*", mention_author=False)
            else:
                await message.reply("✨ 目前沒有任何排查中的案件，所有照片皆已結案！\n*(可在欲轉播的頻道輸入 `!setlogchannel` 開啟即時動態串流)*", mention_author=False)
            return

def main():
    if not config.bot_token or config.bot_token == "YOUR_DISCORD_BOT_TOKEN":
        print("[!] 尚未在 config.json 或環境變數中設定 DISCORD_BOT_TOKEN！")
        return

    client.run(config.bot_token)

if __name__ == "__main__":
    main()
