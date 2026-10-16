import os
import re
import json
import shutil
import time
from typing import Dict, Any, List, Optional

class CaseManager:
    """
    案件分發與管理系統：
    將 Discord 的疑難照片接軌至專案的「案件/」目錄，交由 Antigravity 深度物證分析。
    """
    def __init__(self, cases_dir: str = None):
        if cases_dir is None:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            cases_dir = os.path.join(project_root, "案件")
        self.cases_dir = cases_dir
        self.template_path = os.path.join(os.path.dirname(self.cases_dir), "案件模板.md")
        os.makedirs(self.cases_dir, exist_ok=True)

    def get_next_case_id(self) -> str:
        """
        掃描案件目錄，取得未使用的下一號案件編號 (例如 008)
        """
        existing_ids = []
        pattern = re.compile(r"案件-(\d{3})")
        for fname in os.listdir(self.cases_dir):
            match = pattern.search(fname)
            if match:
                existing_ids.append(int(match.group(1)))
        next_num = max(existing_ids, default=0) + 1
        return f"{next_num:03d}"

    def create_case_from_discord(
        self,
        image_path: str,
        channel_id: int,
        message_id: int,
        author_name: str,
        guess_candidates: List[str] = None
    ) -> str:
        """
        為疑難照片建立新案件 (JPG + Markdown + JSON)
        """
        case_id = self.get_next_case_id()
        base_name = f"案件-{case_id}-Discord照片"
        dest_jpg = os.path.join(self.cases_dir, f"{base_name}.jpg")
        dest_md = os.path.join(self.cases_dir, f"{base_name}.md")
        dest_json = os.path.join(self.cases_dir, f"案件-{case_id}.json")

        # 1. 複製圖片至案件目錄
        shutil.copy2(image_path, dest_jpg)

        # 2. 建立 JSON 資料檔
        guesses = guess_candidates or []
        case_data = {
            "case_id": case_id,
            "case_title": "Discord 上傳照片辨識",
            "source": "discord",
            "discord_meta": {
                "channel_id": channel_id,
                "message_id": message_id,
                "author": author_name,
                "created_at": time.time()
            },
            "status": "investigating",
            "guesses": guesses,
            "exclusions": [],
            "leading_candidate": None,
            "resolved": False
        }
        with open(dest_json, "w", encoding="utf-8") as f:
            json.dump(case_data, f, ensure_ascii=False, indent=2)

        # 3. 依據模板建立 Markdown 檔案
        today_str = time.strftime("%Y-%m-%d")
        guesses_str = "、".join(guesses) if guesses else "暫無"
        md_content = f"""# 餐廳辨識案件

## 案件資訊

- 案件編號：{case_id}
- 建立日期：{today_str}
- 照片／線索：Discord 頻道由 {author_name} 上傳之食物照片
- 群友猜測候選：{guesses_str}
- 目前狀態：調查中（已轉交 Antigravity 深度微型物證排查）

## 使用者提供的範圍與限制

- 可能地點：依規則預設（台北、桃園、台南），必要時擴大
- 指定日期或時間：預設目前仍營業之店家
- 其他限制：近期器皿不符直接排除

## 照片觀察

![案件照片]({os.path.basename(dest_jpg)})

### 餐點

- 可確認：
- 推測、待確認：

### 餐具與器皿

- 碗／盤／托盤的顏色、材質、形狀、花紋：

### 餐廳環境

- 桌面、牆面、風扇、座椅、照明、擺設及空間：

## 使用者後續補充或更正

- 來自 Discord 訊息 ID: {message_id}

## 候選店家

| 店名 | Google Maps 地點 | 餐點符合處 | 環境／器皿符合處 | 不符合處 | 近期營業證據 | 判斷 |
| --- | --- | --- | --- | --- | --- | --- |

## 結論

- 店名：
- Google Maps 地點：
- 把握度：低／中／高
- 主要依據：
- 尚未確認之處：
"""
        with open(dest_md, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"[CaseManager] 疑難案件已成功建檔: {base_name} (案件編號: {case_id})")
        return case_id

    def get_investigating_cases(self) -> List[Dict[str, Any]]:
        """
        取得目前所有正在調查中的案件清單
        """
        results = []
        for fname in os.listdir(self.cases_dir):
            if fname.startswith("案件-") and fname.endswith(".json"):
                fpath = os.path.join(self.cases_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("status") == "investigating" and not data.get("resolved", False):
                        results.append(data)
                except Exception:
                    pass
        return results

    def get_resolved_unnotified_cases(self) -> List[Dict[str, Any]]:
        """
        取得已結案但尚未回報至 Discord 的案件
        """
        resolved_cases = []
        for fname in os.listdir(self.cases_dir):
            if fname.startswith("案件-") and fname.endswith(".json"):
                fpath = os.path.join(self.cases_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("source") == "discord" and data.get("resolved") and not data.get("discord_notified", False):
                        resolved_cases.append((fpath, data))
                except Exception:
                    pass
        return resolved_cases

    def mark_case_notified(self, json_path: str, data: Dict[str, Any]):
        data["discord_notified"] = True
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[CaseManager] 標記案件已通知失敗: {e}")

    def check_and_apply_timeout_cutoff(self, max_seconds: int = 1800):
        """
        檢查調查中案件，若超過 30 分鐘 (1800s) 則依 AGENTS.md 停損原則自動標記為尚無法確認
        """
        now = time.time()
        for fname in os.listdir(self.cases_dir):
            if fname.startswith("案件-") and fname.endswith(".json"):
                fpath = os.path.join(self.cases_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("source") == "discord" and data.get("status") == "investigating" and not data.get("resolved", False):
                        created_at = data.get("discord_meta", {}).get("created_at", now)
                        if now - created_at >= max_seconds:
                            data["status"] = "unconfirmed"
                            data["resolved"] = True
                            data["timeout_cutoff"] = True
                            data["discord_notified"] = False
                            with open(fpath, "w", encoding="utf-8") as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                            print(f"[CaseManager] 案件-{data.get('case_id')} 已達 30 分鐘停損時限，自動標記為尚無法確認。")
                except Exception as e:
                    print(f"[CaseManager] 檢查停損異常: {e}")
