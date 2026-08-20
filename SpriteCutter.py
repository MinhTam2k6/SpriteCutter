import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import os

WHITE_THRESHOLD = 245


def is_foreground(r, g, b, a=255):
    return a > 10 and (
        r < WHITE_THRESHOLD or
        g < WHITE_THRESHOLD or
        b < WHITE_THRESHOLD
    )


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


def split_wide_run(col_has, x1, x2, min_width=20):
    """
    Tự tìm điểm cắt bên trong một vùng quá rộng.

    Trường hợp hai nhân vật đứng quá sát nhau:
        [ NHÂN VẬT 1 ][NHÂN VẬT 2]
                     ^
               valley thấp

    Ta tìm valley có mật độ pixel thấp nhất.
    """

    width = x2 - x1 + 1

    # Không cố tách những vùng nhỏ.
    if width < min_width * 2:
        return [(x1, x2)]

    values = col_has[x1:x2 + 1]

    if not values:
        return [(x1, x2)]

    # ---------------------------------------------------------
    # Làm mượt projection nhẹ để tránh nhiễu 1-2 pixel
    # ---------------------------------------------------------
    smooth = []

    for i in range(len(values)):
        start = max(0, i - 2)
        end = min(len(values), i + 3)

        avg = sum(values[start:end]) / (end - start)
        smooth.append(avg)

    # ---------------------------------------------------------
    # Tìm peak trái / phải
    # ---------------------------------------------------------
    middle = len(smooth) // 2

    left_values = smooth[:middle]
    right_values = smooth[middle:]

    if not left_values or not right_values:
        return [(x1, x2)]

    left_peak = max(left_values)
    right_peak = max(right_values)

    # ---------------------------------------------------------
    # Tìm valley tốt nhất quanh khu vực giữa.
    #
    # Không bắt buộc valley phải bằng 0.
    # ---------------------------------------------------------
    search_start = max(3, int(len(smooth) * 0.25))
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

        # Hai bên valley phải có nội dung đủ lớn.
        left_near = max(smooth[max(0, i - 15):i]) if i > 0 else 0
        right_near = max(smooth[i + 1:min(len(smooth), i + 16)])

        if left_near <= 0 or right_near <= 0:
            continue

        # Valley càng thấp so với hai phía càng tốt.
        relative = valley / max(
            1,
            min(left_near, right_near)
        )

        # Ưu tiên valley nằm gần giữa.
        center_distance = abs(
            i - len(smooth) / 2
        ) / max(1, len(smooth))

        score = relative + center_distance * 0.35

        if score < best_score:
            best_score = score
            best_index = i

    if best_index is None:
        return [(x1, x2)]

    # ---------------------------------------------------------
    # Kiểm tra valley có đủ rõ không.
    #
    # Nếu không đủ rõ thì không tách.
    # ---------------------------------------------------------
    valley = smooth[best_index]

    left_peak = max(
        smooth[max(0, best_index - int(len(smooth) * 0.35)):best_index]
    )

    right_peak = max(
        smooth[
            best_index + 1:
            min(len(smooth), best_index + int(len(smooth) * 0.35))
        ]
    )

    surrounding_peak = min(left_peak, right_peak)

    if surrounding_peak <= 0:
        return [(x1, x2)]

    valley_ratio = valley / surrounding_peak

    # Valley phải thấp hơn khoảng 70% so với vùng nhân vật.
    if valley_ratio > 0.70:
        return [(x1, x2)]

    split_x = x1 + best_index

    left_width = split_x - x1 + 1
    right_width = x2 - split_x

    # Không tạo frame quá nhỏ.
    if left_width < min_width or right_width < min_width:
        return [(x1, x2)]

    return [
        (x1, split_x),
        (split_x + 1, x2)
    ]


def detect_horizontal_runs(col_has, gap_threshold, min_width):
    """
    Phát hiện các vùng nhân vật theo chiều ngang.
    """

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

    # ---------------------------------------------------------
    # Merge những đoạn bị tách bởi khe rất nhỏ.
    # ---------------------------------------------------------
    merged = []

    for a, b in runs:

        if not merged:
            merged.append([a, b])

        elif a - merged[-1][1] > gap_threshold:
            merged.append([a, b])

        else:
            merged[-1][1] = b

    # ---------------------------------------------------------
    # Loại bỏ noise quá nhỏ.
    # ---------------------------------------------------------
    merged = [
        r for r in merged
        if r[1] - r[0] + 1 >= min_width
    ]

    return merged


def split_runs_if_needed(col_has, runs, w):
    """
    Nếu một run rộng bất thường, thử tách thành 2 nhân vật.

    Đây là phần sửa lỗi chính.
    """

    if not runs:
        return runs

    widths = [
        b - a + 1
        for a, b in runs
    ]

    # Chiều rộng thông thường của sprite.
    sorted_widths = sorted(widths)
    median_width = sorted_widths[len(sorted_widths) // 2]

    result = []

    for x1, x2 in runs:

        width = x2 - x1 + 1

        # Một vùng rộng hơn đáng kể so với sprite thông thường
        # có khả năng chứa 2 nhân vật.
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
                min_width=max(20, int(w * 0.02))
            )

            result.extend(split)

        else:
            result.append((x1, x2))

    return result


def crop_vertical_region(
    rgba,
    x1,
    x2,
    ignore_top,
    padding
):
    """
    Cắt chiều dọc của từng nhân vật.
    """

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
            (s, len(occupied) - 1)
        )

    if not regions:
        return None

    # Vùng chính thường là vùng cao nhất.
    region = max(
        regions,
        key=lambda r: r[1] - r[0]
    )

    y1 = ignore_top + region[0]
    y2 = ignore_top + region[1]

    # ---------------------------------------------------------
    # Gộp những phần nhỏ nằm ngay bên dưới sprite.
    # ---------------------------------------------------------
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


def auto_crop_frames(
    img,
    padding=4,
    gap_threshold=8
):

    rgba = img.convert("RGBA")

    w, h = rgba.size

    # ---------------------------------------------------------
    # Bỏ qua banner phía trên.
    # ---------------------------------------------------------
    ignore_top = max(
        1,
        int(h * 0.08)
    )

    # ---------------------------------------------------------
    # Projection theo chiều ngang.
    # ---------------------------------------------------------
    col_has = build_column_projection(
        rgba,
        ignore_top
    )

    # ---------------------------------------------------------
    # Phát hiện vùng ban đầu.
    # ---------------------------------------------------------
    min_width = max(
        8,
        int(w * 0.01)
    )

    runs = detect_horizontal_runs(
        col_has,
        gap_threshold,
        min_width
    )

    # ---------------------------------------------------------
    # PHẦN SỬA LỖI:
    #
    # Nếu 2 nhân vật quá sát nhau và bị gộp thành 1 vùng,
    # thử tìm valley để tách chúng.
    # ---------------------------------------------------------
    runs = split_runs_if_needed(
        col_has,
        runs,
        w
    )

    # ---------------------------------------------------------
    # Cắt từng nhân vật.
    # ---------------------------------------------------------
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
            frames.append(crop)

    return frames


class SpriteCutter:

    def __init__(self, root):

        self.root = root

        self.root.title(
            "Sprite Cutter v2 - AutoStrategyGame"
        )

        self.root.geometry(
            "560x390"
        )

        self.root.resizable(
            False,
            False
        )

        self.image_path = None

        tk.Label(
            root,
            text="SPRITE CUTTER v2",
            font=("Arial", 20, "bold")
        ).pack(
            pady=(18, 3)
        )

        tk.Label(
            root,
            text="Tự phát hiện và cắt từng nhân vật trong sprite sheet",
            font=("Arial", 10)
        ).pack(
            pady=(0, 18)
        )

        tk.Button(
            root,
            text="1. Chọn Sprite Sheet",
            width=34,
            height=2,
            command=self.choose_image
        ).pack(
            pady=6
        )

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

        tk.Button(
            root,
            text="2. TỰ ĐỘNG CẮT",
            width=34,
            height=2,
            command=self.cut_auto
        ).pack(
            pady=12
        )

        self.status = tk.Label(
            root,
            text="Chưa chọn ảnh",
            wraplength=500
        )

        self.status.pack(
            pady=8
        )

        tk.Label(
            root,
            text=(
                "Tool có thể tách các nhân vật đứng sát nhau "
                "mà không cần khoảng trắng lớn."
            ),
            font=("Arial", 9)
        ).pack(
            pady=8
        )

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
                text="Đã chọn: "
                + os.path.basename(path)
            )

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
                int(self.padding.get())
            )

            gap = max(
                1,
                int(self.gap.get())
            )

            img = Image.open(
                self.image_path
            )

            frames = auto_crop_frames(
                img,
                padding=padding,
                gap_threshold=gap
            )

            if not frames:

                messagebox.showerror(
                    "Không tìm thấy frame",
                    (
                        "Không phát hiện được nhân vật. "
                        "Hãy kiểm tra ảnh có nền trắng."
                    )
                )

                return

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

            # Xóa frame cũ để tránh trường hợp
            # lần trước có 7 frame, lần này chỉ có 6
            # nhưng frame_07 cũ vẫn còn.
            for filename in os.listdir(output_dir):

                if (
                    filename.startswith("frame_")
                    and filename.lower().endswith(".png")
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

            for i, frame in enumerate(
                frames,
                1
            ):

                frame.save(
                    os.path.join(
                        output_dir,
                        f"frame_{i:02d}.png"
                    )
                )

            self.status.config(
                text=(
                    f"Đã tự động cắt "
                    f"{len(frames)} frame → "
                    f"{output_dir}"
                )
            )

            messagebox.showinfo(
                "Hoàn tất",
                (
                    f"Đã phát hiện và cắt "
                    f"{len(frames)} frame.\n\n"
                    f"Thư mục:\n"
                    f"{output_dir}"
                )
            )

        except Exception as e:

            messagebox.showerror(
                "Lỗi",
                str(e)
            )


root = tk.Tk()

SpriteCutter(root)

root.mainloop()