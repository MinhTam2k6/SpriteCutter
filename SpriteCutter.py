import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image
import os

class SpriteCutter:
    def __init__(self, root):
        self.root = root
        self.root.title("Sprite Cutter - AutoStrategyGame")
        self.root.geometry("520x300")
        self.image_path = None

        tk.Label(root, text="SPRITE CUTTER", font=("Arial", 18, "bold")).pack(pady=15)

        tk.Button(root, text="1. Chọn Sprite Sheet", width=30,
                  command=self.choose_image).pack(pady=8)

        frame = tk.Frame(root)
        frame.pack(pady=5)

        tk.Label(frame, text="Số frame:").pack(side="left")
        self.frames = tk.Entry(frame, width=8)
        self.frames.insert(0, "8")
        self.frames.pack(side="left", padx=8)

        tk.Button(root, text="2. Cắt Frame", width=30,
                  command=self.cut).pack(pady=12)

        self.status = tk.Label(root, text="Chưa chọn ảnh")
        self.status.pack(pady=5)

    def choose_image(self):
        self.image_path = filedialog.askopenfilename(
            title="Chọn sprite sheet",
            filetypes=[("Image", "*.png *.jpg *.jpeg *.webp")]
        )
        if self.image_path:
            self.status.config(text=os.path.basename(self.image_path))

    def cut(self):
        if not self.image_path:
            messagebox.showwarning("Thiếu ảnh", "Hãy chọn sprite sheet trước.")
            return

        try:
            count = int(self.frames.get())
            if count <= 0:
                raise ValueError

            img = Image.open(self.image_path).convert("RGBA")
            w, h = img.size

            # Chia đều theo chiều ngang
            frame_w = w // count

            output_dir = os.path.join(
                os.path.dirname(self.image_path),
                os.path.splitext(os.path.basename(self.image_path))[0] + "_frames"
            )
            os.makedirs(output_dir, exist_ok=True)

            for i in range(count):
                left = i * frame_w
                right = w if i == count - 1 else (i + 1) * frame_w
                frame = img.crop((left, 0, right, h))
                frame.save(os.path.join(output_dir, f"frame_{i+1:02d}.png"))

            messagebox.showinfo(
                "Hoàn tất",
                f"Đã cắt {count} frame.\\n\\nThư mục:\\n{output_dir}"
            )
            self.status.config(text=f"Đã cắt {count} frame")

        except Exception as e:
            messagebox.showerror("Lỗi", str(e))

root = tk.Tk()
SpriteCutter(root)
root.mainloop()
