"""توليد الصور للفيديوهات الطويلة.

الترتيب: المزوّد اللي في IMAGE_PROVIDER ← Pexels ← تدرّج لوني.
يعني النشر عمره ما بيقف بسبب فشل الـAI.

IMAGE_PROVIDER:
  pollinations (الافتراضي، مجاني وبدون مفتاح)
  openai       (محتاج OPENAI_API_KEY، واختياريًا OPENAI_IMAGE_MODEL)
  none         (يتخطى الـAI ويروح على الاحتياطي، مفيد للاختبار)
"""
import base64
import io
import os
import random
import time
import urllib.parse

import requests
from PIL import Image, ImageDraw

from long_prompts import PALETTE_RGB

FALLBACK_QUERIES = [
    "misty forest", "desert dunes", "night sky stars", "mountain lake",
    "waterfall nature", "calm ocean sunrise", "green valley", "clouds above mountains",
]


def _open(content):
    return Image.open(io.BytesIO(content)).convert("RGB")


def cover_resize(img, width, height):
    """يملأ المقاس بالكامل (قص من الأطراف) من غير تشويه."""
    scale = max(width / img.width, height / img.height)
    resized = img.resize((max(width, round(img.width * scale)), max(height, round(img.height * scale))), Image.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def from_pollinations(prompt, seed, width, height):
    url = (
        "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
        + f"?width={width}&height={height}&seed={seed}&nologo=true&model=flux"
    )
    res = requests.get(url, timeout=240)
    res.raise_for_status()
    if "image" not in res.headers.get("Content-Type", ""):
        raise RuntimeError("الرد مش صورة")
    return _open(res.content)


def from_openai(prompt, seed, width, height):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY غير موجود")
    res = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"),
            "prompt": prompt,
            "size": "1536x1024",
            "n": 1,
        },
        timeout=300,
    )
    res.raise_for_status()
    return _open(base64.b64decode(res.json()["data"][0]["b64_json"]))


def from_pexels(seed, width, height):
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY غير موجود")
    rng = random.Random(seed)
    query = rng.choice(FALLBACK_QUERIES)
    res = requests.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "orientation": "landscape", "per_page": 30},
        headers={"Authorization": key},
        timeout=30,
    )
    res.raise_for_status()
    photos = res.json().get("photos", [])
    if not photos:
        raise RuntimeError("Pexels مرجّعش صور")
    photo = rng.choice(photos)
    img_res = requests.get(photo["src"]["large2x"], timeout=60)
    img_res.raise_for_status()
    return _open(img_res.content)


def gradient_image(palette_idx, seed, width, height):
    """آخر خط دفاع: تدرّج لوني من ألوان القالب."""
    top, bottom = PALETTE_RGB[palette_idx % len(PALETTE_RGB)]
    rng = random.Random(seed)
    shift = rng.uniform(-0.15, 0.15)
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = min(1.0, max(0.0, y / height + shift))
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)
    return img


def generate_image(prompt, seed, width, height, palette_idx=0, retries=2):
    """بيرجع (صورة PIL بالمقاس المطلوب، اسم المصدر)."""
    provider = os.environ.get("IMAGE_PROVIDER", "pollinations").lower()
    providers = {"pollinations": from_pollinations, "openai": from_openai}

    if provider in providers:
        for attempt in range(1, retries + 1):
            try:
                img = providers[provider](prompt, seed + attempt, width, height)
                return cover_resize(img, width, height), provider
            except Exception as exc:  # noqa: BLE001
                print(f"⚠️ {provider} محاولة {attempt} فشلت: {exc}")
                time.sleep(3 * attempt)

    try:
        return cover_resize(from_pexels(seed, width, height), width, height), "pexels"
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ Pexels فشل: {exc}")

    return gradient_image(palette_idx, seed, width, height), "gradient"
