import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
from collections import deque
import os


# ============================================================
# CẤU HÌNH
# ============================================================

WHITE_THRESHOLD = 245

# Độ sai khác màu cho phép khi nhận diện nền.
# Tăng lên nếu nền có gradient / hơi nhiễu.
BACKGROUND_TOLERANCE = 35

# Chỉ xóa vùng nền liên thông với mép ảnh.
# Điều này giúp không xóa những vùng màu giống nền
# nhưng nằm bên trong nhân vật.
USE_FLOOD_FILL = True


# ============================================================
# FOREGROUND
# ============================================================

def is_foreground(r, g, b, a=255):
    return a > 10 and (
        r < WHITE_THRESHOLD or
        g < WHITE_THRESHOLD or
        b < WHITE_THRESHOLD
    )


# ============================================================
# COLUMN PROJECTION
# ============================================================

def build_column_projection(rgba, ignore_top):
    w, h = rgba.size
    px = rgba.load()

    col_has = []

    for x in range(w):
        count = 0

        for y in range(ignore_top, h):
            if is_foreground(*px[x, y]):
                count += 1

        col_has.append(count)

    return col_has


# ============================================================
# TÁCH VÙNG RỘNG
# ============================================================

def split_wide_run(col_has, x1, x2, min_width=20):

    width = x2 - x1 + 1

    if width < min_width * 2:
        return [(x1, x2)]

    values = col_has[x1:x2 + 1]

    if not values:
        return [(x1, x2)]

    # Làm mượt projection
    smooth = []

    for i in range(len(values)):

        start = max(0, i - 2)
        end = min(len(values), i + 3)

        avg = sum(values[start:end]) / (end - start)

        smooth.append(avg)

    middle = len(smooth) // 2

    left_values = smooth[:middle]
    right_values = smooth[middle:]

    if not left_values or not right_values:
        return [(x1, x2)]

    search_start = max(
        3,
        int(len(smooth) * 0.25)
    )

    search_end = min(
        len(smooth) - 4,
        int(len(smooth) * 0.75)
    )

    if search_start >= search_end:
        return [(x1, x2)]

    best_index = None
    best_score = float("inf")

    for i in range(search_start, search_end + 1):

        valley = smooth[i]

        left_near = max(
            smooth[max(0, i - 15):i]
        ) if i > 0 else 0

        right_near = max(
            smooth[i + 1:min(len(smooth), i + 16)]
        )

        if left_near <= 0 or right_near <= 0:
            continue

        relative = valley / max(
            1,
            min(left_near, right_near)
        )

        center_distance = abs(
            i - len(smooth) / 2
        ) / max(
            1,
            len(smooth)
        )

        score = relative + center_distance * 0.35

        if score < best_score:
            best_score = score
            best_index = i

    if best_index is None:
        return [(x1, x2)]

    valley = smooth[best_index]

    left_peak = max(
        smooth[
            max(
                0,
                best_index - int(len(smooth) * 0.35)
            ):best_index
        ]
    )

    right_peak = max(
        smooth[
            best_index + 1:
            min(
                len(smooth),
                best_index + int(len(smooth) * 0.35)
            )
        ]
    )

    surrounding_peak = min(
        left_peak,
        right_peak
    )

    if surrounding_peak <= 0:
        return [(x1, x2)]

    valley_ratio = (
        valley / surrounding_peak
    )

    if valley_ratio > 0.70:
        return [(x1, x2)]

    split_x = x1 + best_index

    left_width = split_x - x1 + 1
    right_width = x2 - split_x

    if (
        left_width < min_width or
        right_width < min_width
    ):
        return [(x1, x2)]

    return [
        (x1, split_x),
        (split_x + 1, x2)
    ]


# ============================================================
# PHÁT HIỆN RUN
# ============================================================

def detect_horizontal_runs(
    col_has,
    gap_threshold,
    min_width
):

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

                runs.append(
                    (start, last_nonzero)
                )

                start = None
                gap = 0

    if start is not None:

        runs.append(
            (start, last_nonzero)
        )

    merged = []

    for a, b in runs:

        if not merged:

            merged.append([a, b])

        elif a - merged[-1][1] > gap_threshold:

            merged.append([a, b])

        else:

            merged[-1][1] = b

    merged = [
        r for r in merged
        if r[1] - r[0] + 1 >= min_width
    ]

    return merged


# ============================================================
# TÁCH RUN QUÁ RỘNG
# ============================================================

def split_runs_if_needed(
    col_has,
    runs,
    w
):

    if not runs:
        return runs

    widths = [
        b - a + 1
        for a, b in runs
    ]

    sorted_widths = sorted(widths)

    median_width = (
        sorted_widths[
            len(sorted_widths) // 2
        ]
    )

    result = []

    for x1, x2 in runs:

        width = x2 - x1 + 1

        suspicious = (
            width > median_width * 1.45
            if median_width > 0
            else width > w * 0.20
        )

        if suspicious:

            split = split_wide_run(
                col_has,
                x1,
                x2,
                min_width=max(
                    20,
                    int(w * 0.02)
                )
            )

            result.extend(split)

        else:

            result.append(
                (x1, x2)
            )

    return result


# ============================================================
# CẮT CHIỀU DỌC
# ============================================================

def crop_vertical_region(
    rgba,
    x1,
    x2,
    ignore_top,
    padding
):

    w, h = rgba.size
    px = rgba.load()

    row_counts = []

    for y in range(
        ignore_top,
        h
    ):

        count = 0

        for x in range(
            x1,
            x2 + 1
        ):

            if is_foreground(
                *px[x, y]
            ):
                count += 1

        row_counts.append(count)

    occupied = [
        c > 0
        for c in row_counts
    ]

    regions = []

    s = None

    for i, ok in enumerate(
        occupied
    ):

        if ok and s is None:

            s = i

        elif not ok and s is not None:

            regions.append(
                (s, i - 1)
            )

            s = None

    if s is not None:

        regions.append(
            (
                s,
                len(occupied) - 1
            )
        )

    if not regions:
        return None

    region = max(
        regions,
        key=lambda r:
        r[1] - r[0]
    )

    y1 = ignore_top + region[0]
    y2 = ignore_top + region[1]

    # Gộp phần nhỏ nằm sát phía dưới
    for r in regions:

        ry1 = ignore_top + r[0]
        ry2 = ignore_top + r[1]

        if (
            ry1 > y2 and
            ry1 - y2 <= 10
        ):

            y2 = ry2

    x1p = max(
        0,
        x1 - padding
    )

    x2p = min(
        w - 1,
        x2 + padding
    )

    y1p = max(
        0,
        y1 - padding
    )

    y2p = min(
        h - 1,
        y2 + padding
    )

    return rgba.crop(
        (
            x1p,
            y1p,
            x2p + 1,
            y2p + 1
        )
    )


# ============================================================
# TÍNH KHOẢNG CÁCH MÀU
# ============================================================

def color_distance(c1, c2):

    r1, g1, b1, a1 = c1
    r2, g2, b2, a2 = c2

    return (
        abs(r1 - r2) +
        abs(g1 - g2) +
        abs(b1 - b2)
    ) / 3.0


# ============================================================
# XÁC ĐỊNH MÀU NỀN
# ============================================================

def get_background_colors(img):

    rgba = img.convert("RGBA")

    w, h = rgba.size
    px = rgba.load()

    samples = []

    # Lấy mẫu ở bốn cạnh.
    step_x = max(
        1,
        w // 50
    )

    step_y = max(
        1,
        h // 50
    )

    # Mép trên
    for x in range(
        0,
        w,
        step_x
    ):

        samples.append(
            px[x, 0]
        )

    # Mép dưới
    for x in range(
        0,
        w,
        step_x
    ):

        samples.append(
            px[x, h - 1]
        )

    # Mép trái
    for y in range(
        0,
        h,
        step_y
    ):

        samples.append(
            px[0, y]
        )

    # Mép phải
    for y in range(
        0,
        h,
        step_y
    ):

        samples.append(
            px[w - 1, y]
        )

    if not samples:
        return [(255, 255, 255, 255)]

    # Chia các màu thành nhóm gần nhau.
    clusters = []

    for color in samples:

        found = False

        for cluster in clusters:

            if color_distance(
                color,
                cluster[0]
            ) <= BACKGROUND_TOLERANCE:

                cluster.append(color)

                found = True

                break

        if not found:

            clusters.append(
                [color]
            )

    # Nhóm lớn nhất thường là màu nền.
    clusters.sort(
        key=len,
        reverse=True
    )

    background_colors = []

    for cluster in clusters[:3]:

        avg_r = int(
            sum(
                c[0]
                for c in cluster
            ) / len(cluster)
        )

        avg_g = int(
            sum(
                c[1]
                for c in cluster
            ) / len(cluster)
        )

        avg_b = int(
            sum(
                c[2]
                for c in cluster
            ) / len(cluster)
        )

        background_colors.append(
            (
                avg_r,
                avg_g,
                avg_b,
                255
            )
        )

    return background_colors


# ============================================================
# XÓA NỀN BẰNG FLOOD FILL
# ============================================================

def remove_background(
    img,
    tolerance=BACKGROUND_TOLERANCE
):

    rgba = img.convert("RGBA")

    w, h = rgba.size

    px = rgba.load()

    background_colors = (
        get_background_colors(rgba)
    )

    if not background_colors:
        return rgba

    visited = bytearray(
        w * h
    )

    queue = deque()

    # --------------------------------------------------------
    # Bắt đầu từ toàn bộ mép ảnh.
    # --------------------------------------------------------

    for x in range(w):

        queue.append(
            (x, 0)
        )

        queue.append(
            (x, h - 1)
        )

    for y in range(h):

        queue.append(
            (0, y)
        )

        queue.append(
            (w - 1, y)
        )

    # --------------------------------------------------------
    # Flood fill
    # --------------------------------------------------------

    while queue:

        x, y = queue.popleft()

        index = y * w + x

        if visited[index]:
            continue

        visited[index] = 1

        current = px[x, y]

        # Nếu pixel này không giống nền,
        # không đi sâu vào vùng đó.
        is_background = False

        for bg in background_colors:

            if color_distance(
                current,
                bg
            ) <= tolerance:

                is_background = True
                break

        if not is_background:
            continue

        # Xóa nền
        px[x, y] = (
            current[0],
            current[1],
            current[2],
            0
        )

        # Các pixel xung quanh
        neighbors = (
            (x - 1, y),
            (x + 1, y),
            (x, y - 1),
            (x, y + 1)
        )

        for nx, ny in neighbors:

            if (
                0 <= nx < w and
                0 <= ny < h
            ):

                nindex = ny * w + nx

                if not visited[nindex]:

                    queue.append(
                        (nx, ny)
                    )

    return rgba


# ============================================================
# AUTO CROP
# ============================================================

def auto_crop_frames(
    img,
    padding=4,
    gap_threshold=8
):

    rgba = img.convert("RGBA")

    w, h = rgba.size

    ignore_top = max(
        1,
        int(h * 0.08)
    )

    col_has = build_column_projection(
        rgba,
        ignore_top
    )

    min_width = max(
        8,
        int(w * 0.01)
    )

    runs = detect_horizontal_runs(
        col_has,
        gap_threshold,
        min_width
    )

    runs = split_runs_if_needed(
        col_has,
        runs,
        w
    )

    frames = []

    for x1, x2 in runs:

        crop = crop_vertical_region(
            rgba,
            x1,
            x2,
            ignore_top,
            padding
        )

        if crop is not None:

            frames.append(
                crop
            )

    return frames


# ============================================================
# GIAO DIỆN
# ============================================================

class SpriteCutter:

    def __init__(self, root):

        self.root = root

        self.root.title(
            "Sprite Cutter v3 - AutoStrategyGame"
        )

        self.root.geometry(
            "620x470"
        )

        self.root.resizable(
            False,
            False
        )

        self.image_path = None

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        tk.Label(
            root,
            text="SPRITE CUTTER v3",
            font=("Arial", 20, "bold")
        ).pack(
            pady=(18, 3)
        )

        tk.Label(
            root,
            text=(
                "Tự động cắt nhân vật + xóa nền "
                "thành PNG trong suốt"
            ),
            font=("Arial", 10)
        ).pack(
            pady=(0, 18)
        )

        # ----------------------------------------------------
        # CHỌN ẢNH
        # ----------------------------------------------------

        tk.Button(
            root,
            text="1. Chọn Sprite Sheet",
            width=36,
            height=2,
            command=self.choose_image
        ).pack(
            pady=6
        )

        # ----------------------------------------------------
        # OPTIONS
        # ----------------------------------------------------

        options = tk.Frame(root)

        options.pack(
            pady=12
        )

        tk.Label(
            options,
            text="Khoảng đệm (px):"
        ).grid(
            row=0,
            column=0,
            padx=5
        )

        self.padding = tk.Entry(
            options,
            width=7
        )

        self.padding.insert(
            0,
            "4"
        )

        self.padding.grid(
            row=0,
            column=1,
            padx=5
        )

        tk.Label(
            options,
            text="Khoảng trắng tối đa (px):"
        ).grid(
            row=0,
            column=2,
            padx=5
        )

        self.gap = tk.Entry(
            options,
            width=7
        )

        self.gap.insert(
            0,
            "8"
        )

        self.gap.grid(
            row=0,
            column=3,
            padx=5
        )

        # ----------------------------------------------------
        # BACKGROUND TOLERANCE
        # ----------------------------------------------------

        bg_options = tk.Frame(root)

        bg_options.pack(
            pady=4
        )

        tk.Label(
            bg_options,
            text="Độ nhận diện nền:"
        ).grid(
            row=0,
            column=0,
            padx=5
        )

        self.bg_tolerance = tk.Entry(
            bg_options,
            width=7
        )

        self.bg_tolerance.insert(
            0,
            str(BACKGROUND_TOLERANCE)
        )

        self.bg_tolerance.grid(
            row=0,
            column=1,
            padx=5
        )

        tk.Label(
            bg_options,
            text="(mặc định 35)"
        ).grid(
            row=0,
            column=2,
            padx=5
        )

        # ----------------------------------------------------
        # BUTTON
        # ----------------------------------------------------

        tk.Button(
            root,
            text="2. TỰ ĐỘNG CẮT + XÓA NỀN",
            width=36,
            height=2,
            command=self.cut_auto
        ).pack(
            pady=15
        )

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        self.status = tk.Label(
            root,
            text="Chưa chọn ảnh",
            wraplength=560
        )

        self.status.pack(
            pady=8
        )

        tk.Label(
            root,
            text=(
                "Nền trắng, xám, xanh, đỏ... đều có thể "
                "được tự động xóa. Kết quả là PNG trong suốt."
            ),
            font=("Arial", 9),
            wraplength=560
        ).pack(
            pady=8
        )

        tk.Label(
            root,
            text=(
                "Nếu nền hơi nhiễu hoặc gradient, "
                "tăng 'Độ nhận diện nền'."
            ),
            font=("Arial", 9)
        ).pack(
            pady=2
        )

    # ========================================================
    # CHỌN ẢNH
    # ========================================================

    def choose_image(self):

        path = filedialog.askopenfilename(
            title="Chọn sprite sheet",
            filetypes=[
                (
                    "Image",
                    "*.png *.jpg *.jpeg *.webp"
                )
            ]
        )

        if path:

            self.image_path = path

            self.status.config(
                text=(
                    "Đã chọn: "
                    + os.path.basename(path)
                )
            )

    # ========================================================
    # CẮT
    # ========================================================

    def cut_auto(self):

        if not self.image_path:

            messagebox.showwarning(
                "Thiếu ảnh",
                "Hãy chọn sprite sheet trước."
            )

            return

        try:

            padding = max(
                0,
                int(
                    self.padding.get()
                )
            )

            gap = max(
                1,
                int(
                    self.gap.get()
                )
            )

            tolerance = max(
                1,
                int(
                    self.bg_tolerance.get()
                )
            )

            # ------------------------------------------------
            # Đọc ảnh
            # ------------------------------------------------

            img = Image.open(
                self.image_path
            ).convert(
                "RGBA"
            )

            # ------------------------------------------------
            # Cắt frame
            # ------------------------------------------------

            frames = auto_crop_frames(
                img,
                padding=padding,
                gap_threshold=gap
            )

            if not frames:

                messagebox.showerror(
                    "Không tìm thấy frame",
                    (
                        "Không phát hiện được nhân vật.\n\n"
                        "Hãy kiểm tra sprite sheet."
                    )
                )

                return

            # ------------------------------------------------
            # Output folder
            # ------------------------------------------------

            base = os.path.splitext(
                os.path.basename(
                    self.image_path
                )
            )[0]

            output_dir = os.path.join(
                os.path.dirname(
                    self.image_path
                ),
                base + "_auto_frames"
            )

            os.makedirs(
                output_dir,
                exist_ok=True
            )

            # ------------------------------------------------
            # Xóa frame cũ
            # ------------------------------------------------

            for filename in os.listdir(
                output_dir
            ):

                if (
                    filename.startswith("frame_")
                    and
                    filename.lower().endswith(
                        ".png"
                    )
                ):

                    try:

                        os.remove(
                            os.path.join(
                                output_dir,
                                filename
                            )
                        )

                    except:
                        pass

            # ------------------------------------------------
            # Xóa nền + lưu
            # ------------------------------------------------

            for i, frame in enumerate(
                frames,
                1
            ):

                transparent_frame = (
                    remove_background(
                        frame,
                        tolerance=tolerance
                    )
                )

                output_path = os.path.join(
                    output_dir,
                    f"frame_{i:02d}.png"
                )

                transparent_frame.save(
                    output_path,
                    "PNG"
                )

            # ------------------------------------------------
            # Status
            # ------------------------------------------------

            self.status.config(
                text=(
                    f"Đã cắt {len(frames)} frame "
                    f"+ xóa nền → "
                    f"{output_dir}"
                )
            )

            messagebox.showinfo(
                "Hoàn tất",
                (
                    f"Đã xử lý {len(frames)} frame.\n\n"
                    f"✓ Tự động cắt\n"
                    f"✓ Tự động xóa nền\n"
                    f"✓ PNG trong suốt\n\n"
                    f"Thư mục:\n"
                    f"{output_dir}"
                )
            )

        except Exception as e:

            messagebox.showerror(
                "Lỗi",
                str(e)
            )


# ============================================================
# MAIN
# ============================================================

root = tk.Tk()

SpriteCutter(root)

root.mainloop()