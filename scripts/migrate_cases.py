import os
import re
import shutil

def migrate():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "案件"))
    if not os.path.exists(base_dir):
        print(f"Directory not found: {base_dir}")
        return

    pattern = re.compile(r"^案件-(\d{3})")
    files = os.listdir(base_dir)

    # 收集每個 case_id 對應的所有檔案
    cases = {}
    for f in files:
        fpath = os.path.join(base_dir, f)
        if os.path.isfile(fpath) and f != "案件模板.md":
            m = pattern.match(f)
            if m:
                cid = m.group(1)
                cases.setdefault(cid, []).append(f)

    print(f"找到 {len(cases)} 個案件待歸檔...")

    total_moved = 0
    for cid in sorted(cases.keys()):
        case_folder_name = f"案件-{cid}"
        case_dir = os.path.join(base_dir, case_folder_name)
        os.makedirs(case_dir, exist_ok=True)

        for fname in cases[cid]:
            src = os.path.join(base_dir, fname)
            dst = os.path.join(case_dir, fname)
            shutil.move(src, dst)
            total_moved += 1
            print(f"  [+] 搬移: {fname} -> {case_folder_name}/{fname}")

    print(f"遷移完成！共歸檔 {len(cases)} 個案件目錄，移動 {total_moved} 個檔案。")

if __name__ == "__main__":
    migrate()
