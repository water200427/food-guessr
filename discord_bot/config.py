import os
import json
from dataclasses import dataclass, field
from typing import List

@dataclass
class DiscordBotConfig:
    bot_token: str = ""
    trigger_timeout_seconds: int = 30
    reply_footer: str = "(此為貓貓自動偵測回覆)"
    gemini_api_key: str = ""

    @classmethod
    def load(cls, config_path: str = None) -> "DiscordBotConfig":
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            candidates = [
                os.path.join(base_dir, "config.json"),
                os.path.join(os.path.dirname(base_dir), "config.json")
            ]
            for p in candidates:
                if os.path.exists(p):
                    config_path = p
                    break

        cfg = cls()
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cfg.bot_token = data.get("bot_token", cfg.bot_token)
                    cfg.trigger_timeout_seconds = int(data.get("trigger_timeout_seconds", cfg.trigger_timeout_seconds))
                    cfg.reply_footer = data.get("reply_footer", cfg.reply_footer)
                    cfg.gemini_api_key = data.get("gemini_api_key", cfg.gemini_api_key)
            except Exception as e:
                print(f"[!] 載入設定失敗 ({e})，使用預設值。")

        # 支援環境變數
        cfg.bot_token = os.getenv("DISCORD_BOT_TOKEN", cfg.bot_token)
        cfg.gemini_api_key = os.getenv("GEMINI_API_KEY", cfg.gemini_api_key)
        return cfg
