import os
import sys
import argparse
import time
from PIL import Image

def crop_image(
    input_path: str,
    output_path: str = None,
    box: list = None,
    percent: list = None,
    zoom: float = 1.0
) -> str:
    """
    精確微距與局部物證裁切工具：
    支援絕對像素或百分比裁切，並可選高清晰度微距放大 (Lanczos)。
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"找不到輸入圖片檔案: {input_path}")

    with Image.open(input_path) as img:
        # 自動處理 EXIF 旋轉方向 (若有)
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        w, h = img.size

        if percent:
            if len(percent) != 4:
                raise ValueError("percent 參數必須為 4 個浮點數：left top right bottom (範圍 0.0 ~ 1.0)")
            p_left, p_top, p_right, p_bottom = [float(p) for p in percent]
            crop_box = (
                int(w * max(0.0, min(1.0, p_left))),
                int(h * max(0.0, min(1.0, p_top))),
                int(w * max(0.0, min(1.0, p_right))),
                int(h * max(0.0, min(1.0, p_bottom)))
            )
        elif box:
            if len(box) != 4:
                raise ValueError("box 參數必須為 4 個整數像素座標：x1 y1 x2 y2")
            x1, y1, x2, y2 = [int(b) for b in box]
            crop_box = (
                max(0, min(w, x1)),
                max(0, min(h, y1)),
                max(0, min(w, x2)),
                max(0, min(h, y2))
            )
        else:
            # 預設不裁切，只做複製或縮放
            crop_box = (0, 0, w, h)

        # 檢查裁切區域有效性
        cw = crop_box[2] - crop_box[0]
        ch = crop_box[3] - crop_box[1]
        if cw <= 0 or ch <= 0:
            raise ValueError(f"無效的裁切範圍: 寬度={cw}, 高度={ch}")

        cropped = img.crop(crop_box)

        # 支援微距超解析放大 (Lanczos)
        if zoom and zoom > 1.0:
            new_w = int(cw * zoom)
            new_h = int(ch * zoom)
            resample_filter = getattr(Image.Resampling, "LANCZOS", Image.LANCZOS)
            cropped = cropped.resize((new_w, new_h), resample_filter)

        # 決定輸出路徑
        if not output_path:
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            scratch_dir = os.path.join(project_root, "scratch")
            os.makedirs(scratch_dir, exist_ok=True)
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            output_path = os.path.join(scratch_dir, f"{base_name}_crop_{int(time.time())}.jpg")
        else:
            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)

        # 轉換為 RGB 儲存為 JPG (避免 RGBA 存 JPG 報錯)
        if cropped.mode in ("RGBA", "P"):
            cropped = cropped.convert("RGB")

        cropped.save(output_path, quality=95)
        print(f"[+] 局部裁切完成！原始尺寸: {w}x{h} -> 裁切尺寸: {cw}x{ch} (儲存至: {output_path})")
        return output_path

def main():
    parser = argparse.ArgumentParser(description="找餐廳微距物證圖片裁切工具")
    parser.add_argument("input", help="輸入圖片路徑")
    parser.add_argument("-o", "--output", help="輸出圖片路徑（預設存於 scratch/）")
    parser.add_argument("--box", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"), help="像素絕對座標裁切：x1 y1 x2 y2")
    parser.add_argument("--percent", nargs=4, type=float, metavar=("L", "T", "R", "B"), help="比例裁切 (0.0~1.0)：左 上 右 下")
    parser.add_argument("--zoom", type=float, default=1.0, help="微距放大倍率 (如 2.0 代表放大 2 倍)")
    parser.add_argument("--info", action="store_true", help="僅顯示圖片解析度與資訊")

    args = parser.parse_args()

    if args.info:
        if not os.path.exists(args.input):
            print(f"[!] 找不到檔案: {args.input}")
            sys.exit(1)
        with Image.open(args.input) as im:
            print(f"圖片路徑: {args.input}")
            print(f"解析度: {im.width} x {im.height}")
            print(f"色彩模式: {im.mode}")
            print(f"格式: {im.format}")
        return

    try:
        out = crop_image(
            input_path=args.input,
            output_path=args.output,
            box=args.box,
            percent=args.percent,
            zoom=args.zoom
        )
    except Exception as e:
        print(f"[!] 裁切失敗: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
