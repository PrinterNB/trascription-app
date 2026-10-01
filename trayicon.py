from PIL import Image, ImageDraw

SIZE = 64

COLORS = {
    "idle": (62, 66, 78),
    "recording": (212, 62, 62),
    "processing": (222, 164, 58),
    "paused": (108, 110, 118),
}


def image_for(status="idle"):
    color = COLORS.get(status, COLORS["idle"])
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, SIZE - 4, SIZE - 4], radius=14, fill=color + (255,))

    cx, cy = SIZE // 2, 22
    d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(245, 245, 248, 255))
    d.line([cx, cy + 10, cx, 47], fill=(245, 245, 248, 255), width=4)
    d.line([cx - 12, 49, cx + 12, 49], fill=(245, 245, 248, 255), width=4)
    return img


def save_icon(path="icon.ico"):
    image_for("idle").save(path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])


if __name__ == "__main__":
    import os

    save_icon(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
