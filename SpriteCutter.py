# ============================================================
# LỌC VÙNG CHÍNH TRONG 1 Ô GRID
# ============================================================

def crop_main_sprite_region(
    frame,
    padding=4
):
    """
    Trong một ô animation:
    - Bỏ chữ tiêu đề ở phía trên.
    - Bỏ số frame ở phía dưới.
    - Giữ lại vùng nhân vật + hiệu ứng.

    Ta tìm các vùng foreground theo chiều dọc
    và chọn vùng lớn nhất.
    """

    rgba = frame.convert("RGBA")

    w, h = rgba.size
    px = rgba.load()

    row_counts = []

    # --------------------------------------------------------
    # Đếm foreground theo từng hàng
    # --------------------------------------------------------

    for y in range(h):

        count = 0

        for x in range(w):

            if is_foreground(*px[x, y]):
                count += 1

        row_counts.append(count)

    occupied = [
        c > 0
        for c in row_counts
    ]

    # --------------------------------------------------------
    # Tìm các vùng foreground theo chiều dọc
    # --------------------------------------------------------

    regions = []

    start = None

    for y, occupied_row in enumerate(occupied):

        if occupied_row and start is None:

            start = y

        elif not occupied_row and start is not None:

            regions.append(
                (start, y - 1)
            )

            start = None

    if start is not None:

        regions.append(
            (
                start,
                len(occupied) - 1
            )
        )

    if not regions:

        return frame

    # --------------------------------------------------------
    # Loại vùng quá nhỏ
    # --------------------------------------------------------

    min_region_height = max(
        15,
        int(h * 0.04)
    )

    regions = [
        region
        for region in regions
        if region[1] - region[0] + 1
        >= min_region_height
    ]

    if not regions:

        return frame

    # --------------------------------------------------------
    # Chọn vùng lớn nhất theo chiều cao.
    #
    # ATTACK thường cao ~50-70 px
    # số 01/02... thường cao ~30-40 px
    # nhân vật cao hơn nhiều.
    # --------------------------------------------------------

    main_region = max(
        regions,
        key=lambda r: r[1] - r[0] + 1
    )

    y1 = main_region[0]
    y2 = main_region[1]

    # --------------------------------------------------------
    # Tìm biên ngang của vùng nhân vật
    # --------------------------------------------------------

    x1 = w
    x2 = -1

    for y in range(y1, y2 + 1):

        for x in range(w):

            if is_foreground(
                *px[x, y]
            ):

                x1 = min(
                    x1,
                    x
                )

                x2 = max(
                    x2,
                    x
                )

    if x2 < x1:

        return frame

    # --------------------------------------------------------
    # Padding
    # --------------------------------------------------------

    x1 = max(
        0,
        x1 - padding
    )

    x2 = min(
        w - 1,
        x2 + padding
    )

    y1 = max(
        0,
        y1 - padding
    )

    y2 = min(
        h - 1,
        y2 + padding
    )

    return rgba.crop(
        (
            x1,
            y1,
            x2 + 1,
            y2 + 1
        )
    )
