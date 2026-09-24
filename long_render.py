"""رندر الفيديو الطويل (16:9): إطارات الآيات + الصورة المصغرة + تجميع ffmpeg.

الفكرة: بدل رندر إطار لكل ثانية، بنعمل صورة واحدة لكل آية وffmpeg بيجمعها مع الصوت.
ده بيخلّي رندر سورة زي البقرة (٢+ ساعة) ياخد دقايق مش ساعات.
"""
import os
import subprocess
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, features

from long_images import cover_resize

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_AR = os.path.join(HERE, "ArabicFont.ttf")
FONT_EN = os.path.join(HERE, "Roboto-Regular.ttf")

W, H = 1920, 1080
THUMB_W, THUMB_H = 1280, 720
GOLD = (255, 215, 0)
FPS = 10

RAQM = features.check("raqm")
_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def to_arabic_digits(value):
    return str(value).translate(_DIGITS)


@lru_cache(maxsize=256)
def font(path, size):
    return ImageFont.truetype(path, size)


def _shape(text):
    if RAQM:
        return text
    try:  # مسار احتياطي لو libraqm مش متاحة
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        return text


def _kw():
    return {"direction": "rtl", "language": "ar"} if RAQM else {}


def ar_width(fnt, text):
    return fnt.getlength(_shape(text), **_kw())


def draw_ar(draw, xy, text, fnt, fill, stroke=3):
    draw.text(
        xy, _shape(text), font=fnt, fill=fill, anchor="mm",
        stroke_width=stroke, stroke_fill="black", **_kw(),
    )


def wrap_px(text, fnt, max_w, arabic):
    measure = (lambda t: ar_width(fnt, t)) if arabic else (lambda t: fnt.getlength(t))
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and measure(trial) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def fit_text(ar, en, box_w, box_h):
    """يختار أكبر خط يخلّي الآية (والترجمة لو دخلت) جوه المربع."""
    result = None
    for with_en in ((True, False) if en else (False,)):
        sizes = range(92, 39, -4) if with_en else range(92, 33, -4)
        for size in sizes:
            f_ar = font(FONT_AR, size)
            ar_lines = wrap_px(ar, f_ar, box_w, True)
            ar_lh = int(size * 1.6)
            total = len(ar_lines) * ar_lh
            en_lines, f_en, en_lh = [], None, 0
            if with_en:
                en_size = max(26, int(size * 0.42))
                f_en = font(FONT_EN, en_size)
                en_lines = wrap_px(en, f_en, box_w, False)
                en_lh = int(en_size * 1.35)
                total += 30 + len(en_lines) * en_lh
            result = {
                "f_ar": f_ar, "ar_lines": ar_lines, "ar_lh": ar_lh,
                "f_en": f_en, "en_lines": en_lines, "en_lh": en_lh, "total": total,
            }
            if total <= box_h:
                return result
    return result


def prepare_background(img):
    """يجهّز الخلفية: مقاس 1920×1080 + تعتيم + فينيت خفيف عشان النص يبان."""
    img = cover_resize(img.convert("RGB"), W, H)
    black = Image.new("RGB", (W, H), (0, 0, 0))
    img = Image.blend(img, black, 0.42)
    mask = Image.radial_gradient("L").resize((W, H)).point(lambda v: int(v * 0.55))
    return Image.composite(black, img, mask)


def _panel_overlay(box):
    x0, y0, x1, y1 = box
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(box, radius=28, fill=(0, 0, 0, 115), outline=GOLD + (230,), width=3)
    od.rounded_rectangle((x0 + 14, y0 + 14, x1 - 14, y1 - 14), radius=20, outline=GOLD + (110,), width=1)
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        r = 11
        od.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=GOLD + (240,))
    return overlay


def render_ayah_frame(base, name, ayah_no, ar, en, reciter, progress, idx, total, out_path):
    box = (150, 175, 1770, 905)
    frame = Image.alpha_composite(base.convert("RGBA"), _panel_overlay(box))
    d = ImageDraw.Draw(frame)

    draw_ar(d, (W / 2, 100), name, font(FONT_AR, 78), GOLD, stroke=4)

    fit = fit_text(ar, en, (box[2] - box[0]) - 160, (box[3] - box[1]) - 110)
    y = (box[1] + box[3]) / 2 - fit["total"] / 2
    for line in fit["ar_lines"]:
        draw_ar(d, (W / 2, y + fit["ar_lh"] / 2), line, fit["f_ar"], "white", stroke=3)
        y += fit["ar_lh"]
    if fit["en_lines"]:
        y += 30
        for line in fit["en_lines"]:
            d.text(
                (W / 2, y + fit["en_lh"] / 2), line, font=fit["f_en"], fill=(224, 224, 224),
                anchor="mm", stroke_width=2, stroke_fill="black",
            )
            y += fit["en_lh"]

    # الفوتر: عدّاد الآيات | رقم الآية داخل دائرة | اسم القارئ
    cy = 985
    d.ellipse((W / 2 - 40, cy - 40, W / 2 + 40, cy + 40), outline=GOLD, width=3)
    draw_ar(d, (W / 2, cy), to_arabic_digits(ayah_no), font(FONT_AR, 36), GOLD, stroke=2)
    d.text((200, cy), f"{idx} / {total}", font=font(FONT_EN, 34), fill=(220, 220, 220), anchor="mm")
    draw_ar(d, (W - 270, cy), reciter, font(FONT_AR, 44), (235, 235, 235), stroke=2)

    # شريط التقدّم في أسفل الفيديو
    d.rectangle((0, H - 14, W, H), fill=(50, 50, 50))
    d.rectangle((0, H - 14, int(W * max(0.0, min(1.0, progress))), H), fill=GOLD)

    frame.convert("RGB").save(out_path, "JPEG", quality=92)


def render_title_frame(base, name, reciter, n_ayahs, dur_text, out_path):
    frame = Image.alpha_composite(base.convert("RGBA"), _panel_overlay((150, 175, 1770, 905)))
    d = ImageDraw.Draw(frame)

    size = 190
    while size > 80 and ar_width(font(FONT_AR, size), name) > 1400:
        size -= 6
    draw_ar(d, (W / 2, 400), name, font(FONT_AR, size), GOLD, stroke=6)
    draw_ar(d, (W / 2, 590), "تلاوة كاملة", font(FONT_AR, 84), "white", stroke=4)
    draw_ar(d, (W / 2, 720), f"بصوت {reciter}", font(FONT_AR, 60), (235, 235, 235), stroke=3)
    info = f"{to_arabic_digits(n_ayahs)} آية  |  {to_arabic_digits(dur_text)}"
    draw_ar(d, (W / 2, 820), info, font(FONT_AR, 48), GOLD, stroke=3)
    frame.convert("RGB").save(out_path, "JPEG", quality=92)


def make_thumbnail(img, name, reciter, dur_text, out_path):
    """صورة مصغرة 1280×720 (تحت 2MB زي شرط يوتيوب)."""
    base = cover_resize(img.convert("RGB"), THUMB_W, THUMB_H)
    black = Image.new("RGB", (THUMB_W, THUMB_H), (0, 0, 0))
    base = Image.blend(base, black, 0.32)
    mask = Image.radial_gradient("L").resize((THUMB_W, THUMB_H)).point(lambda v: int(v * 0.6))
    base = Image.composite(black, base, mask).convert("RGBA")

    overlay = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((60, 60, THUMB_W - 60, THUMB_H - 60), radius=30, outline=GOLD + (220,), width=4)
    od.rounded_rectangle((270, 425, THUMB_W - 270, 535), radius=26, fill=(0, 0, 0, 150))
    if dur_text:
        od.rounded_rectangle((90, 90, 90 + 250, 90 + 96), radius=22, fill=GOLD + (255,))
    thumb = Image.alpha_composite(base, overlay)
    d = ImageDraw.Draw(thumb)

    size = 250
    while size > 90 and ar_width(font(FONT_AR, size), name) > 1080:
        size -= 6
    draw_ar(d, (THUMB_W / 2, 270), name, font(FONT_AR, size), GOLD, stroke=10)
    draw_ar(d, (THUMB_W / 2, 478), "تلاوة كاملة", font(FONT_AR, 88), "white", stroke=5)
    draw_ar(d, (THUMB_W / 2, 597), reciter, font(FONT_AR, 62), (240, 240, 240), stroke=4)
    if dur_text:
        draw_ar(d, (215, 138), to_arabic_digits(dur_text), font(FONT_AR, 52), (20, 20, 20), stroke=0)

    thumb = thumb.convert("RGB")
    quality = 92
    while True:
        thumb.save(out_path, "JPEG", quality=quality)
        if os.path.getsize(out_path) < 1_900_000 or quality <= 60:
            break
        quality -= 8
    return out_path


def build_video(frames, audio_path, out_path, work_dir):
    """frames: قائمة (مسار_الصورة, المدة_بالثواني). بيجمعها مع الصوت في mp4 واحد."""
    list_path = os.path.join(work_dir, "frames.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for path, duration in frames:
            f.write(f"file '{os.path.abspath(path)}'\nduration {duration:.3f}\n")
        # ffmpeg بيتجاهل مدة آخر ملف إلا لو اتكرر
        f.write(f"file '{os.path.abspath(frames[-1][0])}'\n")

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", list_path,
        "-i", audio_path,
        "-vf", f"fps={FPS},format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "24",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path
