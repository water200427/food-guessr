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
    log_channel_id: int = None
    auto_attach_report: bool = False
    config_file_path: str = None

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
        cfg.config_file_path = config_path
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cfg.bot_token = data.get("bot_token", cfg.bot_token)
                    cfg.trigger_timeout_seconds = int(data.get("trigger_timeout_seconds", cfg.trigger_timeout_seconds))
                    cfg.reply_footer = data.get("reply_footer", cfg.reply_footer)
                    cfg.gemini_api_key = data.get("gemini_api_key", cfg.gemini_api_key)
                    cfg.log_channel_id = data.get("log_channel_id", cfg.log_channel_id)
                    cfg.auto_attach_report = data.get("auto_attach_report", cfg.auto_attach_report)
            except Exception as e:
                print(f"[!] 載入設定失敗 ({e})，使用預設值。")

        # 支援環境變數
        cfg.bot_token = os.getenv("DISCORD_BOT_TOKEN", cfg.bot_token)
        cfg.gemini_api_key = os.getenv("GEMINI_API_KEY", cfg.gemini_api_key)
        if os.getenv("LOG_CHANNEL_ID"):
            try:
                cfg.log_channel_id = int(os.getenv("LOG_CHANNEL_ID"))
            except Exception:
                pass
        if os.getenv("AUTO_ATTACH_REPORT"):
            cfg.auto_attach_report = os.getenv("AUTO_ATTACH_REPORT").lower() in ("true", "1", "yes")
        return cfg

    def save(self):
        """將設定回寫至 config.json"""
        path = self.config_file_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        try:
            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["bot_token"] = self.bot_token
            data["trigger_timeout_seconds"] = self.trigger_timeout_seconds
            data["reply_footer"] = self.reply_footer
            data["gemini_api_key"] = self.gemini_api_key
            if self.log_channel_id is not None:
                data["log_channel_id"] = self.log_channel_id
            data["auto_attach_report"] = self.auto_attach_report
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.config_file_path = path
        except Exception as e:
            print(f"[!] 儲存設定檔失敗: {e}")

