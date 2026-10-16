import time
import asyncio
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field

@dataclass
class DiscordFoodSession:
    session_id: str
    channel_id: int
    author_id: int
    first_message: Any  # discord.Message
    image_paths: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    timeout_seconds: int = 30
    timer_task: Optional[asyncio.Task] = None
    status: str = "PENDING"  # PENDING, TRIGGERED_CMD, TRIGGERED_TIMEOUT, CANCELLED_MENTIONED, FINISHED

class DiscordMessageTracker:
    """
    Discord 頻道食物圖片追蹤器 (非同步 asyncio 架構)
    """
    def __init__(
        self,
        command_triggers: List[str] = None,
        default_timeout: int = 30,
        on_trigger_search_async: Optional[Callable[[DiscordFoodSession, bool], Any]] = None,
        is_mentioning_restaurant_fn: Optional[Callable[[str], bool]] = None
    ):
        self.command_triggers = [t.lower() for t in (command_triggers or ["!where", "!這哪家", "!找餐廳"])]
        self.default_timeout = default_timeout
        self.on_trigger_search_async = on_trigger_search_async
        self.is_mentioning_restaurant_fn = is_mentioning_restaurant_fn

        # channel_id -> DiscordFoodSession
        self._active_sessions: Dict[int, DiscordFoodSession] = {}

    def add_food_image(self, channel_id: int, author_id: int, message: Any, image_path: str, timeout: Optional[int] = None) -> DiscordFoodSession:
        timeout_sec = self.default_timeout if timeout is None else timeout
        session = self._active_sessions.get(channel_id)

        # 若該頻道已有進行中的 Session，合併為同一次用餐體驗（多圖追加）
        if session and session.status == "PENDING":
            session.image_paths.append(image_path)
            print(f"[Tracker] 頻道 {channel_id} 追加食物照片 (目前共 {len(session.image_paths)} 張)。")
            return session

        # 建立新 Session
        session_id = f"session_{channel_id}_{int(time.time())}"
        session = DiscordFoodSession(
            session_id=session_id,
            channel_id=channel_id,
            author_id=author_id,
            first_message=message,
            image_paths=[image_path],
            timeout_seconds=timeout_sec,
            status="PENDING"
        )
        self._active_sessions[channel_id] = session

        # 若 timeout 為 0，立即非同步觸發辨識
        if timeout_sec <= 0:
            print(f"[Tracker] 頻道 {channel_id} 要求立即辨識（timeout=0），直接啟動！")
            session.status = "TRIGGERED_CMD"
            if self.on_trigger_search_async:
                loop = asyncio.get_event_loop()
                loop.create_task(self.on_trigger_search_async(session, True))
            return session

        # 啟動非同步倒數計時任務
        loop = asyncio.get_event_loop()
        task = loop.create_task(self._countdown_timer(session))
        session.timer_task = task
        print(f"[Tracker] 頻道 {channel_id} 啟動食物照片追蹤，倒數 {timeout_sec} 秒。")
        return session

    async def handle_text_message(self, channel_id: int, text: str) -> Optional[str]:
        session = self._active_sessions.get(channel_id)
        if not session or session.status != "PENDING":
            return "NO_PENDING_SESSION"

        clean_text = text.strip()
        lower_text = clean_text.lower()

        # 檢查 1: 是否命中 !where 等手動指令
        if any(cmd in lower_text for cmd in self.command_triggers):
            print(f"[Tracker] 頻道 {channel_id} 收到指令 '{clean_text}'，立即觸發找餐廳！")
            if session.timer_task and not session.timer_task.done():
                session.timer_task.cancel()
            session.status = "TRIGGERED_CMD"
            if self.on_trigger_search_async:
                await self.on_trigger_search_async(session, True)
            return "TRIGGERED_CMD"

        # 檢查 2: 是否在對話中提及店名/解答
        if self.is_mentioning_restaurant_fn and self.is_mentioning_restaurant_fn(clean_text):
            print(f"[Tracker] 頻道 {channel_id} 偵測到已提及店名 ('{clean_text}')，取消追蹤不主動回覆！")
            if session.timer_task and not session.timer_task.done():
                session.timer_task.cancel()
            session.status = "CANCELLED_MENTIONED"
            return "CANCELLED_MENTIONED"

        return "IGNORED"

    async def _countdown_timer(self, session: DiscordFoodSession):
        try:
            await asyncio.sleep(session.timeout_seconds)
            if session.status == "PENDING":
                print(f"[Tracker] 頻道 {session.channel_id} 3 分鐘逾時未提店名，自動啟動辨識！")
                session.status = "TRIGGERED_TIMEOUT"
                if self.on_trigger_search_async:
                    await self.on_trigger_search_async(session, False)
        except asyncio.CancelledError:
            pass
