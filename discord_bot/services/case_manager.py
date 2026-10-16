import os
import re
import json
import shutil
import time
import hashlib
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
        self.project_root = os.path.dirname(self.cases_dir)
        self.template_path = os.path.join(self.project_root, "案件模板.md")
        os.makedirs(self.cases_dir, exist_ok=True)

    def compute_file_hash(self, file_path: str) -> Optional[str]:
        """計算檔案的 SHA-256 哈希值供特徵去重比對"""
        if not file_path or not os.path.exists(file_path):
            return None
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return None

    def _get_case_json_paths(self) -> List[str]:
        """
        取得所有案件 JSON 檔案之路徑（同時相容子目錄 案件-00X/ 與根目錄）
        """
        json_paths = []
        if not os.path.exists(self.cases_dir):
            return json_paths

        for root, dirs, files in os.walk(self.cases_dir):
            for fname in files:
                if fname.startswith("案件-") and fname.endswith(".json"):
                    json_paths.append(os.path.join(root, fname))
        return json_paths

    def _get_case_image_paths(self) -> List[str]:
        """
        取得所有案件圖片檔案之路徑（同時相容子目錄 案件-00X/ 與根目錄）
        """
        img_paths = []
        if not os.path.exists(self.cases_dir):
            return img_paths

        for root, dirs, files in os.walk(self.cases_dir):
            for fname in files:
                if fname.startswith("案件-") and fname.lower().endswith((".jpg", ".jpeg", ".png")):
                    img_paths.append(os.path.join(root, fname))
        return img_paths

    def find_case_by_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """依照 Discord message_id 查詢是否已有立案"""
        if not message_id:
            return None
        target_str = str(message_id)
        for fpath in self._get_case_json_paths():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                meta = data.get("discord_meta", {})
                if str(meta.get("message_id")) == target_str:
                    data["_json_path"] = fpath
                    return data
            except Exception:
                pass
        return None

    def find_case_by_image_hash(self, image_path: str) -> Optional[Dict[str, Any]]:
        """比對照片特徵 SHA256，確認是否與既有案件照片完全相同"""
        target_hash = self.compute_file_hash(image_path)
        if not target_hash:
            return None

        # 遍歷所有圖片
        for fpath in self._get_case_image_paths():
            if self.compute_file_hash(fpath) == target_hash:
                fname = os.path.basename(fpath)
                match = re.search(r"案件-(\d{3})", fname)
                if match:
                    case_id = match.group(1)
                    # 優先在同目錄找 json
                    same_dir_json = os.path.join(os.path.dirname(fpath), f"案件-{case_id}.json")
                    root_dir_json = os.path.join(self.cases_dir, f"案件-{case_id}.json")
                    target_json = same_dir_json if os.path.exists(same_dir_json) else root_dir_json
                    if os.path.exists(target_json):
                        try:
                            with open(target_json, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            data["_json_path"] = target_json
                            return data
                        except Exception:
                            pass
        return None

    def attach_conversation_id(self, case_id: str, conversation_id: str):
        """將 Antigravity 開啟的 conversation_id 綁定並回寫至案件 JSON"""
        sub_json = os.path.join(self.cases_dir, f"案件-{case_id}", f"案件-{case_id}.json")
        root_json = os.path.join(self.cases_dir, f"案件-{case_id}.json")
        dest_json = sub_json if os.path.exists(sub_json) else root_json

        if os.path.exists(dest_json):
            try:
                with open(dest_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["conversation_id"] = conversation_id
                with open(dest_json, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[CaseManager] 綁定對話 ID 失敗: {e}")

    def get_next_case_id(self) -> str:
        """
        掃描案件目錄，取得未使用的下一號案件編號 (同時支援子目錄與根目錄)
        """
        existing_ids = []
        pattern = re.compile(r"案件-(\d{3})")
        if os.path.exists(self.cases_dir):
            for entry in os.listdir(self.cases_dir):
                match = pattern.search(entry)
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
        為疑難照片建立新案件 (JPG + Markdown + JSON)，內建去重防護
        """
        # 1. 檢查是否同訊息已立案
        existing_by_msg = self.find_case_by_message(message_id)
        if existing_by_msg and existing_by_msg.get("case_id"):
            existing_id = existing_by_msg.get("case_id")
            print(f"[CaseManager ♻️] 訊息 ID {message_id} 已經立案過 (案件-{existing_id})，直接沿用不重複開案。")
            return existing_id

        # 2. 檢查圖片內容是否與既有已結案/調查中案件完全一致
        existing_by_img = self.find_case_by_image_hash(image_path)
        if existing_by_img and existing_by_img.get("case_id"):
            existing_id = existing_by_img.get("case_id")
            print(f"[CaseManager ♻️] 照片特徵完全吻合既有案件 (案件-{existing_id})，直接沿用不重複建檔。")
            return existing_id

        case_id = self.get_next_case_id()
        case_folder_name = f"案件-{case_id}"
        case_dir = os.path.join(self.cases_dir, case_folder_name)
        os.makedirs(case_dir, exist_ok=True)

        base_name = f"案件-{case_id}-Discord照片"
        dest_jpg = os.path.join(case_dir, f"{base_name}.jpg")
        dest_md = os.path.join(case_dir, f"{base_name}.md")
        dest_json = os.path.join(case_dir, f"案件-{case_id}.json")

        # 1. 複製圖片至案件專屬目錄
        shutil.copy2(image_path, dest_jpg)

        # 2. 建立 JSON 資料檔（不再列入群友未篩選發言，避免消耗 Token）
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
            "guesses": [],
            "exclusions": [],
            "leading_candidate": None,
            "resolved": False
        }
        with open(dest_json, "w", encoding="utf-8") as f:
            json.dump(case_data, f, ensure_ascii=False, indent=2)

        # 3. 依據模板建立 Markdown 檔案（不再列入群友猜測，節省 Token）
        today_str = time.strftime("%Y-%m-%d")
        md_content = f"""# 餐廳辨識案件

## 案件資訊

- 案件編號：{case_id}
- 建立日期：{today_str}
- 照片／線索：Discord 頻道由 {author_name} 上傳之食物照片
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

        print(f"[CaseManager] 疑難案件已成功建檔: {case_folder_name}/{base_name} (案件編號: {case_id})")
        return case_id

    def get_investigating_cases(self) -> List[Dict[str, Any]]:
        """
        取得目前所有正在調查中的案件清單
        """
        results = []
        for fpath in self._get_case_json_paths():
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
        for fpath in self._get_case_json_paths():
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
        for fpath in self._get_case_json_paths():
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
