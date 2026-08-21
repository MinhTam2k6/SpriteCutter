import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
from collections import deque
import os


# ============================================================
# CẤU HÌNH
# ============================================================

WHITE_THRESHOLD = 245
BACKGROUND_TOLERANCE = 35


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

    smooth = []

    for i in range(len(values)):
        start = max(0, i - 2)
        end = min(len(values), i + 3)

        avg = sum(values[start:end]) / (end - start)
        smooth.append(avg)

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

    left_start = max(
        0,
        best_index - int(len(smooth) * 0.35)
    )

    left_peak = max(
        smooth[left_start:best_index]
    ) if best_index > left_start else 0

    right_end = min(
        len(smooth),
        best_index + int(len(smooth) * 0.35)
    )

    right_peak = max(
        smooth[best_index + 1:right_end]
    ) if right_end > best_index + 1 else 0

    surrounding_peak = min(
        left_peak,
        right_peak
    )

    if surrounding_peak <= 0:
        return [(x1, x2)]

    valley_ratio = valley / surrounding_peak

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

    median_width = sorted_widths[
        len(sorted_widths) // 2
    ]

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

    for y in range(ignore_top, h):

        count = 0

        for x in range(x1, x2 + 1):

            if is_foreground(*px[x, y]):
                count += 1

        row_counts.append(count)

    occupied = [
        c > 0
        for c in row_counts
    ]

    regions = []
    s = None

    for i, ok in enumerate(occupied):

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
        key=lambda r: r[1] - r[0]
    )

    y1 = ignore_top + region[0]
    y2 = ignore_top + region[1]

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
# GRID 2 x 4
# ============================================================

def crop_grid_2x4(img, padding=4):

    rgba = img.convert("RGBA")

    w, h = rgba.size

    if w < 4 or h < 2:
        return []

    frame_width = w // 4
    frame_height = h // 2

    frames = []

    # --------------------------------------------------------
    # Hàng trên: frame 01 -> 04
    # Hàng dưới: frame 05 -> 08
    # --------------------------------------------------------

    for row in range(2):

        for col in range(4):

            x1 = col * frame_width
            y1 = row * frame_height

            # Frame cuối cùng lấy đến mép thật
            # để tránh mất pixel do chia nguyên.
            if col == 3:
                x2 = w
            else:
                x2 = (col + 1) * frame_width

            if row == 1:
                y2 = h
            else:
                y2 = (row + 1) * frame_height

            # Padding nhỏ trong từng ô.
            x1p = max(
                0,
                x1 - padding
            )

            y1p = max(
                0,
                y1 - padding
            )

            x2p = min(
                w,
                x2 + padding
            )

            y2p = min(
                h,
                y2 + padding
            )

            frame = rgba.crop(
                (
                    x1p,
                    y1p,
                    x2p,
                    y2p
                )
            )

            frames.append(frame)

    return frames


# ============================================================
# KHOẢNG CÁCH MÀU
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

    step_x = max(
        1,
        w // 50
    )

    step_y = max(
        1,
        h // 50
    )

    for x in range(
        0,
        w,
        step_x
    ):

        samples.append(
            px[x, 0]
        )

        samples.append(
            px[x, h - 1]
        )

    for y in range(
        0,
        h,
        step_y
    ):

        samples.append(
            px[0, y]
        )

        samples.append(
            px[w - 1, y]
        )

    if not samples:
        return [
            (
                255,
                255,
                255,
                255
            )
        ]

    clusters = []

    for color in samples:

        found = False

        for cluster in clusters:

            if color_distance(
                color,
                cluster[0]
            ) <= BACKGROUND_TOLERANCE:

                cluster.append(
                    color
                )

                found = True

                break

        if not found:

            clusters.append(
                [color]
            )

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
# XÓA NỀN
# ============================================================

def remove_background(
    img,
    tolerance=BACKGROUND_TOLERANCE
):

    rgba = img.convert("RGBA")

    w, h = rgba.size
    px = rgba.load()

    background_colors = get_background_colors(
        rgba
    )

    if not background_colors:
        return rgba

    visited = bytearray(
        w * h
    )

    queue = deque()

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

    while queue:

        x, y = queue.popleft()

        index = y * w + x

        if visited[index]:
            continue

        visited[index] = 1

        current = px[x, y]

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

        px[x, y] = (
            current[0],
            current[1],
            current[2],
            0
        )

        neighbors = (
            (x - 1, y),
            (x + 1, y),
            (x, y - 1),
            (x, y + 1)
        )

        for nx, ny in neighbors:

            if (
                0 <= nx < w
                and
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
# CHECKERBOARD PREVIEW
# ============================================================

def make_checkerboard(
    width,
    height,
    cell=10
):

    image = Image.new(
        "RGB",
        (width, height),
        "white"
    )

    pixels = image.load()

    for y in range(height):

        for x in range(width):

            if (
                (x // cell)
                +
                (y // cell)
            ) % 2 == 0:

                pixels[x, y] = (
                    235,
                    235,
                    235
                )

            else:

                pixels[x, y] = (
                    255,
                    255,
                    255
                )

    return image


# ============================================================
# SPRITE CUTTER V4
# ============================================================

class SpriteCutter:

    def __init__(self, root):

        self.root = root

        self.root.title(
            "Sprite Cutter v4.1 - AutoStrategyGame"
        )

        self.root.geometry(
            "980x760"
        )

        self.root.minsize(
            900,
            680
        )

        self.image_path = None
        self.original_image = None

        self.preview_frames = []

        self.preview_photo = []

        self.preview_index = 0

        self.build_ui()


    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):

        title = tk.Label(
            self.root,
            text="SPRITE CUTTER v4.1",
            font=("Arial", 22, "bold")
        )

        title.pack(
            pady=(15, 2)
        )

        subtitle = tk.Label(
            self.root,
            text=(
                "AutoStrategyGame Asset Tool • "
                "Cắt nhân vật + Xóa nền + Preview"
            ),
            font=("Arial", 10)
        )

        subtitle.pack(
            pady=(0, 12)
        )

        # ----------------------------------------------------
        # CHỌN ẢNH
        # ----------------------------------------------------

        top = tk.Frame(
            self.root
        )

        top.pack(
            fill="x",
            padx=18
        )

        tk.Button(
            top,
            text="1. CHỌN SPRITE SHEET",
            width=28,
            height=2,
            command=self.choose_image
        ).pack(
            side="left",
            padx=5
        )

        self.file_label = tk.Label(
            top,
            text="Chưa chọn ảnh",
            anchor="w"
        )

        self.file_label.pack(
            side="left",
            padx=12,
            fill="x",
            expand=True
        )

        # ----------------------------------------------------
        # SETTINGS
        # ----------------------------------------------------

        settings = tk.LabelFrame(
            self.root,
            text="Thiết lập",
            padx=10,
            pady=8
        )

        settings.pack(
            fill="x",
            padx=18,
            pady=10
        )

        # Kiểu cắt
        tk.Label(
            settings,
            text="Kiểu cắt:"
        ).grid(
            row=0,
            column=0,
            padx=5,
            pady=5
        )

        self.cut_mode = ttk.Combobox(
            settings,
            values=[
                "Tự động",
                "Lưới 2 x 4"
            ],
            state="readonly",
            width=14
        )

        self.cut_mode.set(
            "Tự động"
        )

        self.cut_mode.grid(
            row=0,
            column=1,
            padx=5
        )

        self.cut_mode.bind(
            "<<ComboboxSelected>>",
            self.on_cut_mode_changed
        )

        # Số frame
        tk.Label(
            settings,
            text="Số frame:"
        ).grid(
            row=0,
            column=2,
            padx=5,
            pady=5
        )

        self.frame_mode = ttk.Combobox(
            settings,
            values=[
                "Tự động",
                "1",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "10",
                "11",
                "12",
                "13",
                "14",
                "15",
                "16"
            ],
            state="readonly",
            width=10
        )

        self.frame_mode.set(
            "Tự động"
        )

        self.frame_mode.grid(
            row=0,
            column=3,
            padx=5
        )

        # Padding
        tk.Label(
            settings,
            text="Padding:"
        ).grid(
            row=0,
            column=4,
            padx=5
        )

        self.padding = tk.Entry(
            settings,
            width=7
        )

        self.padding.insert(
            0,
            "4"
        )

        self.padding.grid(
            row=0,
            column=5,
            padx=5
        )

        # Gap
        tk.Label(
            settings,
            text="Gap:"
        ).grid(
            row=0,
            column=6,
            padx=5
        )

        self.gap = tk.Entry(
            settings,
            width=7
        )

        self.gap.insert(
            0,
            "8"
        )

        self.gap.grid(
            row=0,
            column=7,
            padx=5
        )

        # Background tolerance
        tk.Label(
            settings,
            text="Nhận diện nền:"
        ).grid(
            row=1,
            column=0,
            padx=5,
            pady=5
        )

        self.bg_tolerance = tk.Entry(
            settings,
            width=7
        )

        self.bg_tolerance.insert(
            0,
            "35"
        )

        self.bg_tolerance.grid(
            row=1,
            column=1,
            padx=5
        )

        tk.Label(
            settings,
            text=(
                "Mặc định: 35"
            )
        ).grid(
            row=1,
            column=2,
            padx=5
        )

        # Thông tin Grid
        self.grid_info = tk.Label(
            settings,
            text="",
            font=("Arial", 9)
        )

        self.grid_info.grid(
            row=1,
            column=3,
            columnspan=5,
            padx=5
        )

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        output_frame = tk.Frame(
            self.root
        )

        output_frame.pack(
            fill="x",
            padx=18,
            pady=4
        )

        tk.Label(
            output_frame,
            text="Thư mục xuất:"
        ).pack(
            side="left",
            padx=5
        )

        self.output_entry = tk.Entry(
            output_frame
        )

        self.output_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=5
        )

        tk.Button(
            output_frame,
            text="Chọn",
            width=10,
            command=self.choose_output
        ).pack(
            side="left",
            padx=5
        )

        # ----------------------------------------------------
        # BUTTONS
        # ----------------------------------------------------

        actions = tk.Frame(
            self.root
        )

        actions.pack(
            pady=10
        )

        tk.Button(
            actions,
            text="2. XEM TRƯỚC",
            width=24,
            height=2,
            command=self.preview
        ).pack(
            side="left",
            padx=8
        )

        tk.Button(
            actions,
            text="3. XUẤT TẤT CẢ",
            width=24,
            height=2,
            command=self.export_frames
        ).pack(
            side="left",
            padx=8
        )

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        self.status = tk.Label(
            self.root,
            text="Sẵn sàng",
            font=("Arial", 10),
            wraplength=900
        )

        self.status.pack(
            pady=5
        )

        # ----------------------------------------------------
        # PREVIEW
        # ----------------------------------------------------

        preview_box = tk.LabelFrame(
            self.root,
            text="Preview",
            padx=8,
            pady=8
        )

        preview_box.pack(
            fill="both",
            expand=True,
            padx=18,
            pady=(5, 15)
        )

        original_box = tk.LabelFrame(
            preview_box,
            text="Sprite Sheet"
        )

        original_box.pack(
            side="left",
            fill="both",
            expand=True,
            padx=5
        )

        self.original_canvas = tk.Canvas(
            original_box,
            bg="#202020",
            highlightthickness=0
        )

        self.original_canvas.pack(
            fill="both",
            expand=True
        )

        frames_box = tk.LabelFrame(
            preview_box,
            text="Frame"
        )

        frames_box.pack(
            side="left",
            fill="both",
            expand=True,
            padx=5
        )

        self.frames_canvas = tk.Canvas(
            frames_box,
            bg="#202020",
            highlightthickness=0
        )

        self.frames_canvas.pack(
            fill="both",
            expand=True
        )

        # ----------------------------------------------------
        # NAV
        # ----------------------------------------------------

        nav = tk.Frame(
            self.root
        )

        nav.pack(
            pady=(0, 12)
        )

        tk.Button(
            nav,
            text="◀",
            width=6,
            command=self.previous_frame
        ).pack(
            side="left",
            padx=5
        )

        self.frame_label = tk.Label(
            nav,
            text="Frame: -"
        )

        self.frame_label.pack(
            side="left",
            padx=15
        )

        tk.Button(
            nav,
            text="▶",
            width=6,
            command=self.next_frame
        ).pack(
            side="left",
            padx=5
        )

        # Cập nhật thông tin ban đầu
        self.on_cut_mode_changed()


    # ========================================================
    # KHI ĐỔI KIỂU CẮT
    # ========================================================

    def on_cut_mode_changed(self, event=None):

        mode = self.cut_mode.get()

        if mode == "Lưới 2 x 4":

            self.grid_info.config(
                text=(
                    "Ảnh sẽ được chia thành "
                    "2 hàng × 4 cột = 8 frame"
                )
            )

            self.frame_mode.set(
                "8"
            )

        else:

            self.grid_info.config(
                text=(
                    "Dùng thuật toán tự động "
                    "như các phiên bản trước"
                )
            )

            self.frame_mode.set(
                "Tự động"
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

        if not path:
            return

        try:

            image = Image.open(
                path
            ).convert(
                "RGBA"
            )

            self.image_path = path
            self.original_image = image

            self.preview_frames = []
            self.preview_photo = []
            self.preview_index = 0

            self.file_label.config(
                text=os.path.basename(path)
            )

            self.output_entry.delete(
                0,
                tk.END
            )

            base = os.path.splitext(
                os.path.basename(path)
            )[0]

            default_output = os.path.join(
                os.path.dirname(path),
                base + "_auto_frames"
            )

            self.output_entry.insert(
                0,
                default_output
            )

            self.show_original_preview()

            self.frames_canvas.delete(
                "all"
            )

            self.frame_label.config(
                text="Frame: -"
            )

            self.status.config(
                text=(
                    f"Đã chọn ảnh: "
                    f"{os.path.basename(path)} | "
                    f"Kích thước: "
                    f"{image.width} × "
                    f"{image.height}px"
                )
            )

        except Exception as e:

            messagebox.showerror(
                "Không thể mở ảnh",
                str(e)
            )


    # ========================================================
    # CHỌN OUTPUT
    # ========================================================

    def choose_output(self):

        initial = None

        if self.output_entry.get():

            initial = (
                self.output_entry.get()
            )

        folder = filedialog.askdirectory(
            title="Chọn thư mục xuất",
            initialdir=(
                initial
                if initial
                and os.path.isdir(initial)
                else None
            )
        )

        if folder:

            self.output_entry.delete(
                0,
                tk.END
            )

            self.output_entry.insert(
                0,
                folder
            )


    # ========================================================
    # SETTINGS
    # ========================================================

    def get_settings(self):

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

        mode = self.frame_mode.get()

        if mode == "Tự động":
            requested_count = None
        else:
            requested_count = int(mode)

        return (
            padding,
            gap,
            tolerance,
            requested_count
        )


    # ========================================================
    # XỬ LÝ FRAME
    # ========================================================

    def process_frames(self):

        if not self.original_image:

            raise ValueError(
                "Hãy chọn sprite sheet trước."
            )

        (
            padding,
            gap,
            tolerance,
            requested_count
        ) = self.get_settings()

        cut_mode = self.cut_mode.get()

        # ----------------------------------------------------
        # GRID 2 x 4
        # ----------------------------------------------------

        if cut_mode == "Lưới 2 x 4":

            frames = crop_grid_2x4(
                self.original_image,
                padding=padding
            )

            if len(frames) != 8:

                raise ValueError(
                    (
                        "Không thể tạo đủ 8 frame "
                        "từ lưới 2 × 4."
                    )
                )

        # ----------------------------------------------------
        # AUTO
        # ----------------------------------------------------

        else:

            frames = auto_crop_frames(
                self.original_image,
                padding=padding,
                gap_threshold=gap
            )

        if not frames:

            raise ValueError(
                "Không phát hiện được frame."
            )

        # ----------------------------------------------------
        # KIỂM TRA SỐ FRAME
        # ----------------------------------------------------

        detected_count = len(frames)

        if requested_count is not None:

            if detected_count != requested_count:

                raise ValueError(
                    (
                        f"Tool phát hiện "
                        f"{detected_count} frame, "
                        f"nhưng bạn yêu cầu "
                        f"{requested_count} frame."
                    )
                )

        # ----------------------------------------------------
        # XÓA NỀN
        # ----------------------------------------------------

        transparent_frames = []

        for frame in frames:

            transparent = remove_background(
                frame,
                tolerance=tolerance
            )

            transparent_frames.append(
                transparent
            )

        return transparent_frames


    # ========================================================
    # PREVIEW
    # ========================================================

    def preview(self):

        try:

            frames = self.process_frames()

            self.preview_frames = frames
            self.preview_index = 0

            self.show_frame_preview()

            mode = self.cut_mode.get()

            self.status.config(
                text=(
                    f"✓ Preview hoàn tất — "
                    f"phát hiện {len(frames)} frame "
                    f"({mode}). Chưa xuất file."
                )
            )

        except Exception as e:

            messagebox.showwarning(
                "Không thể preview",
                str(e)
            )


    # ========================================================
    # PREVIEW SPRITE SHEET
    # ========================================================

    def show_original_preview(self):

        if not self.original_image:
            return

        self.root.update_idletasks()

        canvas_width = max(
            300,
            self.original_canvas.winfo_width()
        )

        canvas_height = max(
            250,
            self.original_canvas.winfo_height()
        )

        image = (
            self.original_image.copy()
        )

        image.thumbnail(
            (
                canvas_width - 20,
                canvas_height - 20
            ),
            Image.Resampling.LANCZOS
        )

        photo = ImageTk.PhotoImage(
            image
        )

        self.original_photo = photo

        self.original_canvas.delete(
            "all"
        )

        self.original_canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=photo,
            anchor="center"
        )


    # ========================================================
    # PREVIEW FRAME
    # ========================================================

    def show_frame_preview(self):

        self.frames_canvas.delete(
            "all"
        )

        self.preview_photo = []

        if not self.preview_frames:

            self.frame_label.config(
                text="Frame: -"
            )

            return

        self.root.update_idletasks()

        canvas_width = max(
            300,
            self.frames_canvas.winfo_width()
        )

        canvas_height = max(
            250,
            self.frames_canvas.winfo_height()
        )

        frame = self.preview_frames[
            self.preview_index
        ]

        checker = make_checkerboard(
            max(100, frame.width),
            max(100, frame.height)
        )

        checker = checker.resize(
            frame.size
        ).convert(
            "RGBA"
        )

        checker.alpha_composite(
            frame
        )

        display = checker.convert(
            "RGB"
        )

        display.thumbnail(
            (
                canvas_width - 30,
                canvas_height - 30
            ),
            Image.Resampling.LANCZOS
        )

        photo = ImageTk.PhotoImage(
            display
        )

        self.preview_photo.append(
            photo
        )

        self.frames_canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=photo,
            anchor="center"
        )

        self.frame_label.config(
            text=(
                f"Frame "
                f"{self.preview_index + 1}"
                f" / "
                f"{len(self.preview_frames)}"
                f"   |   "
                f"{frame.width} × "
                f"{frame.height}px"
            )
        )


    # ========================================================
    # FRAME TRƯỚC
    # ========================================================

    def previous_frame(self):

        if not self.preview_frames:
            return

        self.preview_index -= 1

        if self.preview_index < 0:

            self.preview_index = (
                len(self.preview_frames) - 1
            )

        self.show_frame_preview()


    # ========================================================
    # FRAME SAU
    # ========================================================

    def next_frame(self):

        if not self.preview_frames:
            return

        self.preview_index += 1

        if self.preview_index >= len(
            self.preview_frames
        ):

            self.preview_index = 0

        self.show_frame_preview()


    # ========================================================
    # EXPORT
    # ========================================================

    def export_frames(self):

        try:

            frames = self.process_frames()

            output_dir = (
                self.output_entry.get().strip()
            )

            if not output_dir:

                raise ValueError(
                    "Hãy chọn thư mục xuất."
                )

            os.makedirs(
                output_dir,
                exist_ok=True
            )

            # ------------------------------------------------
            # FRAME CŨ
            # ------------------------------------------------

            old_frames = []

            for filename in os.listdir(
                output_dir
            ):

                if (
                    filename.startswith(
                        "frame_"
                    )
                    and
                    filename.lower().endswith(
                        ".png"
                    )
                ):

                    old_frames.append(
                        filename
                    )

            if old_frames:

                answer = messagebox.askyesno(
                    "Frame cũ",
                    (
                        f"Thư mục đang có "
                        f"{len(old_frames)} frame PNG.\n\n"
                        f"Xóa frame cũ và xuất lại?"
                    )
                )

                if not answer:
                    return

                for filename in old_frames:

                    try:

                        os.remove(
                            os.path.join(
                                output_dir,
                                filename
                            )
                        )

                    except Exception:
                        pass

            # ------------------------------------------------
            # LƯU
            # ------------------------------------------------

            for i, frame in enumerate(
                frames,
                1
            ):

                output_path = os.path.join(
                    output_dir,
                    f"frame_{i:02d}.png"
                )

                frame.save(
                    output_path,
                    "PNG"
                )

            self.preview_frames = frames
            self.preview_index = 0

            self.show_frame_preview()

            self.status.config(
                text=(
                    f"✓ Đã xuất thành công "
                    f"{len(frames)} frame PNG "
                    f"trong suốt."
                )
            )

            messagebox.showinfo(
                "Hoàn tất",
                (
                    f"Đã xuất {len(frames)} frame.\n\n"
                    f"✓ Cắt frame\n"
                    f"✓ Xóa nền\n"
                    f"✓ PNG trong suốt\n"
                    f"✓ Thứ tự frame được giữ nguyên\n\n"
                    f"Thư mục:\n"
                    f"{output_dir}"
                )
            )

        except Exception as e:

            messagebox.showerror(
                "Không thể xuất",
                str(e)
            )


# ============================================================
# MAIN
# ============================================================

root = tk.Tk()

app = SpriteCutter(root)

root.mainloop()
