import os
import glob
import json
import re
from typing import Dict, Any, List, Tuple, Optional

class InvestigationTracker:
    """
    即時調查進度監聽與轉譯引擎：
    自動掛載 Antigravity 獨立調查對話的 transcript.jsonl，
    將底層工具動作轉譯為生動的繁體中文前線戰報與動態階段表情。
    """
    def __init__(self, brain_dir: str = None):
        if brain_dir is None:
            user_home = os.path.expanduser("~")
            brain_dir = os.path.join(user_home, ".gemini", "antigravity", "brain")
        self.brain_dir = brain_dir
        # 紀錄案件對應的 (transcript_path, last_step_index, current_stage_emoji)
        self._case_sessions: Dict[str, Dict[str, Any]] = {}

    def locate_transcript_for_case(self, case_id: str) -> Optional[str]:
        """
        在 brain 目錄中尋找案件對應的 transcript.jsonl
        透過第一行包含的 '案件-{case_id}' 精確比對
        """
        if not os.path.exists(self.brain_dir):
            return None

        # 優先依照修改時間由新到舊搜尋
        pattern = os.path.join(self.brain_dir, "*", ".system_generated", "logs", "transcript.jsonl")
        files = glob.glob(pattern)
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

        target_tag = f"案件-{case_id}"
        for fpath in files[:20]:  # 只掃描最近 20 個對話
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    first_line = f.readline()
                    if target_tag in first_line:
                        return fpath
            except Exception:
                pass
        return None

    def _translate_action_to_report(self, tool_name: str, args: dict) -> Tuple[str, str]:
        """
        將工具調用名稱與參數轉譯為繁體中文戰報，並回傳 (中文戰報, 推薦表情)
        """
        tool_action = args.get("toolAction") or args.get("toolSummary") or ""
        cmd = args.get("CommandLine") or ""

        # 1. 圖片處理與局部微距放大
        if "crop" in cmd.lower() or "zooming" in tool_action.lower() or "cropping" in tool_action.lower():
            if "bottle" in tool_action.lower() or "調味" in tool_action:
                return "正在微距放大比對桌上調味料瓶與標籤特徵...", "🔍"
            if "toothpick" in tool_action.lower() or "牙籤" in tool_action:
                return "正在微距放大觀察桌面擺設與牙籤筒型態...", "🔍"
            return f"正在進行局部物證微距放大（{tool_action or '關鍵線索'}）...", "🔍"

        # 2. 以圖搜尋 / Google Lens
        if "lens" in cmd.lower() or "lens" in tool_action.lower() or "以圖" in tool_action:
            return "啟動 Google Lens 進行視覺物證檢索與餐點辨識...", "🔍"

        # 3. 網頁檢索與官方網站搜尋
        if tool_name == "search_web" or "search" in tool_action.lower():
            query = args.get("query") or tool_action
            if "朝食" in query or "早餐" in query or "菜單" in query:
                return f"比對候選店家菜單與供餐配置：{query[:35]}...", "🔍"
            return f"搜尋比對網路食記與近期情報：{query[:35]}...", "🔍"

        # 4. 瀏覽器導航與畫面截圖
        if "goto" in cmd.lower() or "navigating" in tool_action.lower():
            if "maps" in cmd.lower() or "maps" in tool_action.lower():
                return "進入 Google Maps 商家頁面，核對門市街景、近期裝潢與營業狀態...", "🗺️"
            if "image" in cmd.lower() or "images" in tool_action.lower():
                return "比對 Google 圖片庫中的顧客實體用餐照片...", "🔍"
            return f"瀏覽店家官方資訊頁面（{tool_action or '核對細節'}）...", "🔍"

        if "screenshot" in cmd.lower() or "screenshotting" in tool_action.lower():
            if "maps" in tool_action.lower():
                return "擷取 Google Maps 照片庫比對器皿與桌椅質感...", "🗺️"
            return "擷取店家即時畫面進行特徵交叉比對...", "🔍"

        # 5. 官方短網址提取
        if "share" in cmd.lower() or "getting official" in tool_action.lower():
            return "已高度鎖定目標！正在提取 Google Maps 權威官方分享短網址...", "🗺️"

        # 6. 撰寫報告與歸檔
        if "writing case" in tool_action.lower() or "report" in tool_action.lower() or "markdown" in tool_action.lower():
            return "關鍵物證完全吻合！正在彙整撰寫最終調查報告...", "✍️"

        if "committing" in tool_action.lower() or "git" in cmd.lower():
            return "調查完畢，正在同步報告至公開倉庫...", "✍️"

        # 兜底：若有描述性 toolAction
        if tool_action and not any(k in tool_action.lower() for k in ["viewing", "checking", "compiling"]):
            return f"推進調查進度：{tool_action}...", "🔍"

        return "", ""

    def poll_case_updates(self, case_id: str) -> Tuple[List[str], Optional[str]]:
        """
        輪詢特定案件的最新調查動態
        回傳: (新戰報列表, 最新的推薦表情)
        """
        session = self._case_sessions.get(case_id)
        if not session:
            tpath = self.locate_transcript_for_case(case_id)
            if not tpath:
                return [], None
            session = {
                "path": tpath,
                "last_step": 0,
                "current_emoji": "🕵️",
                "emitted_reports": set()
            }
            self._case_sessions[case_id] = session

        tpath = session["path"]
        if not os.path.exists(tpath):
            return [], None

        new_reports = []
        newest_emoji = None

        try:
            with open(tpath, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        step_data = json.loads(line)
                    except Exception:
                        continue

                    step_idx = step_data.get("step_index", 0)
                    if step_idx <= session["last_step"]:
                        continue

                    session["last_step"] = step_idx

                    # 解析 tool_calls
                    for tc in step_data.get("tool_calls", []):
                        name = tc.get("name", "")
                        args = tc.get("args", {}) or {}
                        report_text, rec_emoji = self._translate_action_to_report(name, args)
                        if report_text and report_text not in session["emitted_reports"]:
                            session["emitted_reports"].add(report_text)
                            new_reports.append(report_text)
                            if rec_emoji:
                                newest_emoji = rec_emoji
                                session["current_emoji"] = rec_emoji

        except Exception:
            pass

        return new_reports, newest_emoji
