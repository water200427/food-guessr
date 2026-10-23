import os
import re
import json
import shutil
import time
import hashlib
from typing import Dict, Any, List, Optional, Union

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
        self.notified_cases_file = os.path.join(self.project_root, "scratch", "notified_cases.json")
        self.notified_case_ids = self._load_notified_case_ids()

    def _load_notified_case_ids(self) -> set:
        """
        載入已成功向 Discord 發送結案通知的案件 ID，杜絕外部覆寫導致重複發送
        """
        notified = set()
        if os.path.exists(self.notified_cases_file):
            try:
                with open(self.notified_cases_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        notified.update(str(x) for x in loaded)
            except Exception:
                pass
        for fpath in self._get_case_json_paths():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("discord_notified") is True:
                    cid = data.get("case_id")
                    if cid:
                        notified.add(str(cid))
            except Exception:
                pass
        return notified

    def _save_notified_case_ids(self):
        """持久化保存已通知案件 ID"""
        try:
            os.makedirs(os.path.dirname(self.notified_cases_file), exist_ok=True)
            with open(self.notified_cases_file, "w", encoding="utf-8") as f:
                json.dump(sorted(list(self.notified_case_ids)), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

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

    def get_case_jump_url(self, case_data: dict, default_guild_id: Optional[int] = None) -> Optional[str]:
        """
        取得案件對應的 Discord 原始訊息跳轉連結 (jump_url)。
        優先讀取儲存的 jump_url；若無則自動由 guild_id、channel_id 與 message_id 兜底合成。
        """
        if not case_data:
            return None
        meta = case_data.get("discord_meta") or {}
        if meta.get("jump_url"):
            return meta.get("jump_url")

        channel_id = meta.get("channel_id")
        message_id = meta.get("message_id")
        if not channel_id or not message_id:
            return None

        guild_id = meta.get("guild_id") or default_guild_id or "@me"
        return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

    def create_case_from_discord(
        self,
        image_paths: Union[str, List[str]] = None,
        channel_id: int = 0,
        message_id: int = 0,
        author_name: str = "",
        guess_candidates: List[str] = None,
        guild_id: Optional[int] = None,
        jump_url: Optional[str] = None,
        image_path: Optional[str] = None
    ) -> str:
        """
        為疑難照片建立新案件 (支援單圖或多圖合併為同一案)，內建去重防護與標準 Schema 結構。
        完美相容 image_paths (多圖/單圖列表) 與 image_path (傳統單圖參數)。
        """
        actual_input = image_paths if image_paths is not None else image_path
        if actual_input is None:
            raise ValueError("必須提供 image_paths 或 image_path")

        if isinstance(actual_input, str):
            image_list = [actual_input]
        else:
            image_list = list(actual_input)

        if not image_list:
            raise ValueError("圖片路徑清單不得為空")

        # 1. 檢查是否同訊息已立案
        existing_by_msg = self.find_case_by_message(message_id)
        if existing_by_msg and existing_by_msg.get("case_id"):
            existing_id = existing_by_msg.get("case_id")
            print(f"[CaseManager ♻️] 訊息 ID {message_id} 已經立案過 (案件-{existing_id})，直接沿用不重複開案。")
            return existing_id

        # 2. 檢查圖片內容是否與既有已結案/調查中案件完全一致
        for img_p in image_list:
            existing_by_img = self.find_case_by_image_hash(img_p)
            if existing_by_img and existing_by_img.get("case_id"):
                existing_id = existing_by_img.get("case_id")
                print(f"[CaseManager ♻️] 照片特徵完全吻合既有案件 (案件-{existing_id})，直接沿用不重複建檔。")
                return existing_id

        case_id = self.get_next_case_id()
        case_folder_name = f"案件-{case_id}"
        case_dir = os.path.join(self.cases_dir, case_folder_name)
        os.makedirs(case_dir, exist_ok=True)

        # 1. 複製圖片至案件專屬目錄 (單圖維持傳統命名，多圖附加序號並複製代表圖)
        copied_filenames = []
        if len(image_list) == 1:
            dest_jpg_name = f"案件-{case_id}-Discord照片.jpg"
            dest_jpg = os.path.join(case_dir, dest_jpg_name)
            shutil.copy2(image_list[0], dest_jpg)
            copied_filenames.append(dest_jpg_name)
        else:
            for idx, img_p in enumerate(image_list, 1):
                dest_jpg_name = f"案件-{case_id}-Discord照片-{idx}.jpg"
                dest_jpg = os.path.join(case_dir, dest_jpg_name)
                shutil.copy2(img_p, dest_jpg)
                copied_filenames.append(dest_jpg_name)
            # 同步備份第 1 張為預設代表圖
            shutil.copy2(image_list[0], os.path.join(case_dir, f"案件-{case_id}-Discord照片.jpg"))

        dest_md = os.path.join(case_dir, f"案件-{case_id}-Discord照片.md")
        dest_json = os.path.join(case_dir, f"案件-{case_id}.json")

        # 2. 建立 JSON 資料檔（包含 guild_id、jump_url、images 清單與標準 Schema 骨架）
        case_data = {
            "case_id": case_id,
            "case_title": "Discord 上傳照片辨識",
            "source": "discord",
            "discord_meta": {
                "guild_id": guild_id,
                "channel_id": channel_id,
                "message_id": message_id,
                "jump_url": jump_url or f"https://discord.com/channels/{guild_id or '@me'}/{channel_id}/{message_id}",
                "author": author_name,
                "created_at": time.time()
            },
            "status": "investigating",
            "resolved": False,
            "discord_notified": False,
            "images": copied_filenames,
            "leading_candidate": None,
            "price_estimation": None,
            "guesses": [],
            "exclusions": []
        }
        with open(dest_json, "w", encoding="utf-8") as f:
            json.dump(case_data, f, ensure_ascii=False, indent=2)

        # 3. 依據模板建立 Markdown 檔案（支援多圖展示與最新餐點價位試算骨架）
        today_str = time.strftime("%Y-%m-%d")
        if len(copied_filenames) == 1:
            md_images = f"![案件照片]({copied_filenames[0]})"
            case_desc = f"Discord 頻道由 {author_name} 上傳之食物照片"
        else:
            md_images = "\n\n".join([f"![案件照片 {i}]({fn})" for i, fn in enumerate(copied_filenames, 1)])
            case_desc = f"Discord 頻道由 {author_name} 上傳之多視角食物照片（共 {len(copied_filenames)} 張）"

        md_content = f"""# 餐廳辨識案件

## 案件資訊

- 案件編號：{case_id}
- 建立日期：{today_str}
- 照片／線索：{case_desc}
- 目前狀態：調查中（已轉交 Antigravity 深度微型物證排查）

## 使用者提供的範圍與限制

- 可能地點：依規則預設（台北、桃園、台南），必要時擴大
- 指定日期或時間：預設目前仍營業之店家
- 其他限制：近期器皿不符直接排除

## 照片觀察

{md_images}

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

### 餐點品項與價位試算

- 參考菜單來源：（如：Google Maps 2026年最新菜單照片／店家官方價目表）
- 價目表日期：（如：2026 年）
- 幣別：新台幣 (TWD)

| 辨識品項 | 規格／數量 | 單價 | 小計 | 照片依據與備註 |
| --- | --- | --- | --- | --- |

- **預估總金額：**
- 費用與低消備註：（如：免收服務費／內用需加收 10% 服務費／無低消限制）
"""
        with open(dest_md, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"[CaseManager] 疑難案件已成功建檔: {case_folder_name} (案件編號: {case_id}, 共 {len(copied_filenames)} 張照片)")
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
        取得已結案但尚未回報至 Discord 的案件（具備記憶體與持久化去重，徹底防止二次發送）
        """
        resolved_cases = []
        for fpath in self._get_case_json_paths():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                case_id = str(data.get("case_id", ""))
                # 若該案件已被記錄為已通知，絕不重複回傳
                if case_id and case_id in self.notified_case_ids:
                    continue
                if data.get("source") == "discord" and data.get("resolved") and not data.get("discord_notified", False):
                    resolved_cases.append((fpath, data))
            except Exception:
                pass
        return resolved_cases

    def mark_case_notified(self, json_path: str, data: Dict[str, Any]):
        data["discord_notified"] = True
        case_id = str(data.get("case_id", ""))
        if case_id:
            self.notified_case_ids.add(case_id)
            self._save_notified_case_ids()
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

    def get_case_md_path(self, case_id: str, json_path: str = None) -> Optional[str]:
        """
        尋找案件對應的 Markdown 報告檔案
        """
        if json_path and os.path.exists(json_path):
            case_dir = os.path.dirname(json_path)
            # 優先找以 案件-{case_id} 開頭的 md
            for fname in os.listdir(case_dir):
                if fname.startswith(f"案件-{case_id}") and fname.endswith(".md"):
                    return os.path.join(case_dir, fname)
            # 其次找目錄下任一非模板的 md
            for fname in os.listdir(case_dir):
                if fname.endswith(".md") and "模板" not in fname:
                    return os.path.join(case_dir, fname)

        # 遍歷案件目錄子資料夾
        target_dir = os.path.join(self.cases_dir, f"案件-{case_id}")
        if os.path.exists(target_dir):
            for fname in os.listdir(target_dir):
                if fname.endswith(".md") and "模板" not in fname:
                    return os.path.join(target_dir, fname)

        # 兜底檢查案件根目錄
        root_md = os.path.join(self.cases_dir, f"案件-{case_id}.md")
        if os.path.exists(root_md):
            return root_md

        return None

    def get_github_md_url(self, md_path: str, repo_owner_name: str = "water200427/food-guessr", branch: str = "main") -> Optional[str]:
        """
        取得 GitHub 公開查看 Markdown 報告的完整網址 (含 URL 編碼避免特殊字元截斷)
        """
        if not md_path or not os.path.exists(md_path):
            return None
        import urllib.parse
        try:
            rel_path = os.path.relpath(md_path, self.project_root).replace("\\", "/")
            quoted_rel = urllib.parse.quote(rel_path)
            return f"https://github.com/{repo_owner_name}/blob/{branch}/{quoted_rel}"
        except Exception:
            return None

    def git_commit_and_push(self, case_id: str) -> bool:
        """
        自動將案件變更 git add, git commit 並 git push 到 GitHub 遠端倉庫，確保為 public
        """
        import subprocess
        try:
            # 1. 加入案件目錄與可能的新檔案
            subprocess.run(["git", "add", "案件/"], cwd=self.project_root, check=False)
            
            # 2. 檢查是否有需要 commit 的內容
            diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=self.project_root)
            if diff_res.returncode != 0:
                commit_msg = f"docs(case-{case_id}): 完成案件-{case_id} 調查報告"
                subprocess.run(["git", "commit", "-m", commit_msg], cwd=self.project_root, check=False)
                print(f"[CaseManager 🐙] 已自動 commit 案件-{case_id} 報告！")
            
            # 3. 推送至遠端 GitHub 確保 public
            push_res = subprocess.run(["git", "push", "origin", "main"], cwd=self.project_root, capture_output=True, text=True, check=False)
            if push_res.returncode == 0:
                print(f"[CaseManager 🚀] 案件-{case_id} 報告已成功 push 至 GitHub (Public)！")
                return True
            else:
                print(f"[CaseManager ⚠️] git push 異常: {push_res.stderr or push_res.stdout}")
                return False
        except Exception as e:
            print(f"[CaseManager ⚠️] 自動執行 git commit & push 失敗: {e}")
            return False

    def get_all_resolved_cases(self) -> List[Dict[str, Any]]:
        """
        取得所有已結案案件清單，依案件編號升序排序
        """
        cases = []
        for fpath in self._get_case_json_paths():
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("resolved"):
                    data["_json_path"] = fpath
                    cases.append(data)
            except Exception:
                pass
        cases.sort(key=lambda x: str(x.get("case_id", "000")))
        return cases

    def get_recent_resolved_cases(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        取得最近結案的案件清單（由新到舊）
        """
        resolved = self.get_all_resolved_cases()
        return list(reversed(resolved))[:limit]

    def find_case_by_query(self, query: str = "") -> Optional[Dict[str, Any]]:
        """
        智慧模糊查詢已結案案件：
        1. 空字串 ➜ 回傳最新結案案件
        2. 數字或案件編號 ➜ 精確比對案件編號 (如 23, 023, 案件-023)
        3. 關鍵字 ➜ 依序搜尋店名、料理、判定依據與 Markdown 報告內文 (回傳最新匹配者)
        """
        resolved = self.get_all_resolved_cases()
        if not resolved:
            return None

        # 情境 1: 無參數，回傳最新結案
        if not query or not query.strip():
            return resolved[-1]

        q = query.strip().lower()

        # 情境 2: 數字或編號比對
        m = re.search(r"(\d+)", q)
        if m:
            target_id = f"{int(m.group(1)):03d}"
            for c in reversed(resolved):
                if c.get("case_id") == target_id:
                    return c

        # 情境 3: 店名、料理、判定理由關鍵字比對
        for c in reversed(resolved):
            lead = c.get("leading_candidate", {}) or {}
            if isinstance(lead, str):
                lead = {"name": lead}
            name = lead.get("name", "").lower()
            dish = lead.get("dish", "").lower()
            basis = (lead.get("basis") or lead.get("reason") or "").lower()
            cid = str(c.get("case_id", "")).lower()

            if q in name or q in dish or q in basis or q in cid:
                return c

        # 情境 4: Markdown 報告全文搜尋比對
        for c in reversed(resolved):
            json_path = c.get("_json_path")
            case_id = c.get("case_id")
            md_path = self.get_case_md_path(case_id, json_path)
            if md_path and os.path.exists(md_path):
                try:
                    with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
                        md_content = f.read().lower()
                    if q in md_content:
                        return c
                except Exception:
                    pass

        return None
