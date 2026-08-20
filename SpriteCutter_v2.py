import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import os

WHITE_THRESHOLD = 245

def is_foreground(r, g, b, a=255):
    return a > 10 and (r < WHITE_THRESHOLD or g < WHITE_THRESHOLD or b < WHITE_THRESHOLD)

def auto_crop_frames(img, padding=4, gap_threshold=8):
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()

    # Ignore the top banner area automatically. We keep a small margin so hair
    # near the top of the characters is not clipped.
    ignore_top = max(1, int(h * 0.08))

    # Column projection: count non-white pixels below the banner.
    col_has = []
    for x in range(w):
        count = 0
        for y in range(ignore_top, h):
            if is_foreground(*px[x, y]):
                count += 1
        col_has.append(count)

    # Fill tiny gaps inside one sprite, but keep large gaps between sprites.
    runs = []
    start = None
    gap = 0
    last_nonzero = -1

    for x, count in enumerate(col_has):
        if count > 0:
            if start is None:
                start = x
            gap = 0
            last_nonzero = x
        elif start is not None:
            gap += 1
            if gap > gap_threshold:
                runs.append((start, last_nonzero))
                start = None
                gap = 0

    if start is not None:
        runs.append((start, last_nonzero))

    # Merge very close runs (e.g. a disconnected sword/cape edge).
    merged = []
    for a, b in runs:
        if not merged or a - merged[-1][1] > gap_threshold:
            merged.append([a, b])
        else:
            merged[-1][1] = b

    # Remove very narrow noise/header remnants.
    min_width = max(8, int(w * 0.01))
    merged = [r for r in merged if r[1] - r[0] + 1 >= min_width]

    frames = []
    for x1, x2 in merged:
        # Row projection inside this sprite region.
        row_counts = []
        for y in range(ignore_top, h):
            count = sum(
                1 for x in range(x1, x2 + 1)
                if is_foreground(*px[x, y])
            )
            row_counts.append(count)

        # Find occupied vertical regions. Tiny regions (like number labels)
        # are ignored by selecting the largest region.
        occupied = [c > 0 for c in row_counts]
        regions = []
        s = None
        for i, ok in enumerate(occupied):
            if ok and s is None:
                s = i
            elif not ok and s is not None:
                regions.append((s, i - 1))
                s = None
        if s is not None:
            regions.append((s, len(occupied) - 1))

        if regions:
            # Main sprite is normally the tallest region.
            region = max(regions, key=lambda r: r[1] - r[0])
            y1 = ignore_top + region[0]
            y2 = ignore_top + region[1]

            # If there are small separated pieces just below the main sprite,
            # include them when they are close, but not distant number badges.
            for r in regions:
                ry1 = ignore_top + r[0]
                ry2 = ignore_top + r[1]
                if ry1 > y2 and ry1 - y2 <= 10:
                    y2 = ry2

            x1p = max(0, x1 - padding)
            x2p = min(w - 1, x2 + padding)
            y1p = max(0, y1 - padding)
            y2p = min(h - 1, y2 + padding)

            crop = rgba.crop((x1p, y1p, x2p + 1, y2p + 1))
            frames.append(crop)

    return frames


class SpriteCutter:
    def __init__(self, root):
        self.root = root
        self.root.title("Sprite Cutter v2 - AutoStrategyGame")
        self.root.geometry("560x390")
        self.root.resizable(False, False)
        self.image_path = None

        tk.Label(root, text="SPRITE CUTTER v2", font=("Arial", 20, "bold")).pack(pady=(18, 3))
        tk.Label(
            root,
            text="Tự phát hiện và cắt từng nhân vật trong sprite sheet",
            font=("Arial", 10)
        ).pack(pady=(0, 18))

        tk.Button(
            root, text="1. Chọn Sprite Sheet", width=34, height=2,
            command=self.choose_image
        ).pack(pady=6)

        options = tk.Frame(root)
        options.pack(pady=12)

        tk.Label(options, text="Khoảng đệm (px):").grid(row=0, column=0, padx=5)
        self.padding = tk.Entry(options, width=7)
        self.padding.insert(0, "4")
        self.padding.grid(row=0, column=1, padx=5)

        tk.Label(options, text="Khoảng trắng tối đa (px):").grid(row=0, column=2, padx=5)
        self.gap = tk.Entry(options, width=7)
        self.gap.insert(0, "8")
        self.gap.grid(row=0, column=3, padx=5)

        tk.Button(
            root, text="2. TỰ ĐỘNG CẮT", width=34, height=2,
            command=self.cut_auto
        ).pack(pady=12)

        self.status = tk.Label(root, text="Chưa chọn ảnh", wraplength=500)
        self.status.pack(pady=8)

        tk.Label(
            root,
            text="Mẹo: ảnh nền trắng và các nhân vật cách nhau sẽ cho kết quả tốt nhất.",
            font=("Arial", 9)
        ).pack(pady=8)

    def choose_image(self):
        path = filedialog.askopenfilename(
            title="Chọn sprite sheet",
            filetypes=[("Image", "*.png *.jpg *.jpeg *.webp")]
        )
        if path:
            self.image_path = path
            self.status.config(text="Đã chọn: " + os.path.basename(path))

    def cut_auto(self):
        if not self.image_path:
            messagebox.showwarning("Thiếu ảnh", "Hãy chọn sprite sheet trước.")
            return

        try:
            padding = max(0, int(self.padding.get()))
            gap = max(1, int(self.gap.get()))

            img = Image.open(self.image_path)
            frames = auto_crop_frames(img, padding=padding, gap_threshold=gap)

            if not frames:
                messagebox.showerror(
                    "Không tìm thấy frame",
                    "Không phát hiện được nhân vật. Hãy kiểm tra ảnh có nền trắng."
                )
                return

            base = os.path.splitext(os.path.basename(self.image_path))[0]
            output_dir = os.path.join(
                os.path.dirname(self.image_path), base + "_auto_frames"
            )
            os.makedirs(output_dir, exist_ok=True)

            for i, frame in enumerate(frames, 1):
                frame.save(os.path.join(output_dir, f"frame_{i:02d}.png"))

            self.status.config(
                text=f"Đã tự động cắt {len(frames)} frame → {output_dir}"
            )
            messagebox.showinfo(
                "Hoàn tất",
                f"Đã phát hiện và cắt {len(frames)} frame.\n\n"
                f"Thư mục:\n{output_dir}"
            )

        except Exception as e:
            messagebox.showerror("Lỗi", str(e))


root = tk.Tk()
SpriteCutter(root)
root.mainloop()
