"""فيديو قرآن طويل (سورة كاملة، 16:9) كل يومين، بترتيب المصحف من سورة البقرة.

منفصل تمامًا عن main.py (الشورتس): ملف تشغيل وسجل وworkflow خاصين بيه.

تشغيل يدوي:
    python long_video.py --force            # ينشر السورة التالية حتى لو لسه ما عدّاش يومين
    python long_video.py --surah 3           # سورة معيّنة (ما بيغيّرش ترتيب السور التالية)
    python long_video.py --dry-run --force   # يرندر ويطلّع الملفات من غير رفع
"""
import argparse
import base64
import json
import os
import random
import shutil
import subprocess
import sys
import time
import wave
from datetime import date, datetime, timezone

import requests

import long_images
import long_prompts as prompts
import long_render as render

LOG_FILE = "long_log.json"
WORK_DIR = "long_work"

FIRST_SURAH = 2      # البقرة
LAST_SURAH = 114
MIN_DAYS_BETWEEN = 2

IMAGE_EVERY_SEC = int(os.environ.get("LONG_IMAGE_EVERY_SEC", "300"))
MAX_IMAGES = 30
CHAPTER_EVERY_SEC = 600
INTRO_SEC = 3.5
XFADE_SEC = 0.12   # تداخل ناعم بين الآيات في المسار الاحتياطي
SAMPLE_RATE = 44100
MAX_LOG_PROMPTS = 6000

API = "https://api.alquran.cloud/v1"
QURAN_COM = "https://api.quran.com/api/v4"
# كلمات تعريف القارئ في قائمة chapter_reciters (مقارنة بحروف صغيرة)
EDITION_KEYWORDS = {
    "ar.alafasy": ("afasy",),
    "ar.husary": ("husary",),
    "ar.minshawi": ("minshawi",),
}
RECITERS = ["ar.alafasy", "ar.husary", "ar.minshawi"]
RECITER_NAMES = {
    "ar.alafasy": "مشاري العفاسي",
    "ar.husary": "محمود خليل الحصري",
    "ar.minshawi": "محمد صديق المنشاوي",
}

TITLE_TEMPLATES = [
    "{surah} كاملة بصوت {reciter} | تلاوة هادئة تريح القلب 🤍",
    "{surah} كاملة ({dur}) بصوت {reciter} 🎧 تلاوة خاشعة",
    "اسمع {surah} كاملة بصوت {reciter} 🕊️ تلاوة تريح النفس",
    "تلاوة {surah} كاملة | {reciter} | مع الآيات مكتوبة والترجمة",
    "{surah} كاملة مكتوبة | بصوت {reciter} | تلاوة خاشعة ✨",
    "قرآن كريم | {surah} كاملة بصوت {reciter} 🤍",
    "{surah} كاملة للسكينة والراحة النفسية | {reciter}",
]

DESC_TEMPLATES = [
    "تلاوة كاملة لـ{surah} بصوت الشيخ {reciter}، مع الآيات مكتوبة والترجمة الإنجليزية على الشاشة.",
    "استمع إلى {surah} كاملة بصوت الشيخ {reciter} في تلاوة هادئة تريح القلب، والآيات أمامك مكتوبة.",
    "{surah} كاملة بصوت {reciter}. تابع الآيات على الشاشة ومعها الترجمة الإنجليزية.",
]


# ================== السجل والجدولة ==================
def default_log():
    return {
        "next_surah": FIRST_SURAH,
        "uploads": [],
        "used_prompt_ids": [],
        "recent_styles": [],
        "recent_palettes": [],
    }


def load_log(path=LOG_FILE):
    log = default_log()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if raw:
            log.update(json.loads(raw))
    return log


def save_log(log, path=LOG_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
        f.write("\n")


def cairo_today():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Africa/Cairo")).date()
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc).date()


def is_due(log, today, min_days=MIN_DAYS_BETWEEN):
    if not log["uploads"]:
        return True
    last = date.fromisoformat(log["uploads"][-1]["date"])
    return (today - last).days >= min_days


def following_surah(n):
    """بعد آخر سورة نرجع للبقرة (الفاتحة قصيرة جدًا ومش هتبقى فيديو طويل)."""
    return FIRST_SURAH if n >= LAST_SURAH else n + 1


# ================== النصوص والعناوين ==================
def strip_diacritics(text):
    out = []
    for ch in text:
        code = ord(ch)
        if 0x064B <= code <= 0x065F or code == 0x0670 or 0x06D6 <= code <= 0x06ED:
            continue
        out.append("ا" if ch == "\u0671" else ch)
    return "".join(out)


def clean_name(api_name):
    """'سُورَةُ ٱلْبَقَرَةِ' -> 'سورة البقرة'"""
    words = strip_diacritics(api_name).split()
    if words and words[0] == "سورة":
        words = words[1:]
    return "سورة " + " ".join(words)


def fmt_ts(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def duration_text(seconds):
    total_min = int(round(seconds / 60))
    h, m = divmod(total_min, 60)
    if h and m:
        return f"{h} ساعة و{m} دقيقة"
    if h:
        return f"{h} ساعة"
    return f"{m} دقيقة"


def short_duration(seconds):
    total_min = int(round(seconds / 60))
    h, m = divmod(total_min, 60)
    return f"{h}:{m:02d}" if h else f"{m} د"


def build_timeline(durations):
    starts, t = [], INTRO_SEC
    for d in durations:
        starts.append(t)
        t += d
    return starts, t


def build_chapters(starts, ayahs, every=CHAPTER_EVERY_SEC):
    """فصول يوتيوب: 0:00 ثم علامة تقريبًا كل 10 دقايق عند بداية آية."""
    marks = [(0.0, "بداية السورة")]
    next_mark = every
    for start, ayah in zip(starts, ayahs):
        if start >= next_mark:
            marks.append((start, f"الآية {ayah['number']}"))
            next_mark = start + every
    if len(marks) < 3:  # يوتيوب محتاج 3 فصول على الأقل
        return ""
    return "\n".join(f"{fmt_ts(t)} {label}" for t, label in marks)


def pick_index(rng, count, recent):
    options = [i for i in range(count) if i not in recent[-2:]] or list(range(count))
    return rng.choice(options)


def build_metadata(rng, surah, reciter, total_sec, chapters, recent_titles=()):
    title_idx = pick_index(rng, len(TITLE_TEMPLATES), list(recent_titles))
    dur = duration_text(total_sec)
    title = TITLE_TEMPLATES[title_idx].format(surah=surah, reciter=reciter, dur=dur)[:100]
    intro = rng.choice(DESC_TEMPLATES).format(surah=surah, reciter=reciter)
    hashtags = f"#قرآن #القرآن_الكريم #تلاوة #{surah.replace(' ', '_')}"
    parts = [intro, f"المدة: {dur}"]
    if chapters:
        parts.append("الفصول:\n" + chapters)
    parts.append(hashtags)
    tags = ["قرآن", "القرآن الكريم", "تلاوة", "تلاوة خاشعة", surah, f"{surah} كاملة", reciter, "quran", "quran recitation"]
    return title, "\n\n".join(parts)[:4900], tags, title_idx


# ================== جلب السورة والصوت ==================
def api_get(url, retries=4):
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, timeout=30)
            res.raise_for_status()
            return res.json()["data"]
        except Exception:  # noqa: BLE001
            if attempt == retries:
                raise
            time.sleep(2 * attempt)


def fetch_surah(s_id, edition):
    audio = api_get(f"{API}/surah/{s_id}/{edition}")
    ar = api_get(f"{API}/surah/{s_id}/quran-simple")
    en = api_get(f"{API}/surah/{s_id}/en.sahih")
    n = len(audio["ayahs"])
    if not (n == len(ar["ayahs"]) == len(en["ayahs"])):
        raise RuntimeError("عدد الآيات مختلف بين الصوت والنص والترجمة.")
    ayahs = [
        {
            "number": audio["ayahs"][i]["numberInSurah"],
            "audio": audio["ayahs"][i]["audio"],
            "ar": ar["ayahs"][i]["text"],
            "en": en["ayahs"][i]["text"],
        }
        for i in range(n)
    ]
    return {"id": s_id, "name": audio["name"], "ayahs": ayahs}


def download(url, path, retries=4):
    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, timeout=60, stream=True) as res:
                res.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in res.iter_content(65536):
                        f.write(chunk)
            return
        except Exception:  # noqa: BLE001
            if attempt == retries:
                raise
            time.sleep(2 * attempt)


def decode_pcm(path):
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        check=True, capture_output=True,
    ).stdout


def _wav_seconds(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / w.getframerate()


def find_chapter_reciter(edition):
    """يدوّر على معرّف القارئ في Quran.com بالاسم (مش أرقام ثابتة)، ويفضّل المرتّل."""
    res = requests.get(f"{QURAN_COM}/resources/chapter_reciters", timeout=30)
    res.raise_for_status()
    words = EDITION_KEYWORDS[edition]
    matches = [r for r in res.json().get("reciters", []) if any(w in str(r.get("name", "")).lower() for w in words)]

    def style(r):
        st = r.get("style")
        return str(st.get("name") if isinstance(st, dict) else st or "").lower()

    murattal = [r for r in matches if style(r) == "murattal"]
    chosen = murattal or matches
    return chosen[0]["id"] if chosen else None


def fetch_continuous(s_id, edition, n_ayahs):
    """بيرجّع (رابط ملف السورة الكامل، بدايات الآيات بالمللي ثانية) أو None لو مش متاح/مش موثوق."""
    reciter_id = find_chapter_reciter(edition)
    if reciter_id is None:
        return None
    res = requests.get(
        f"{QURAN_COM}/chapter_recitations/{reciter_id}/{s_id}", params={"segments": "true"}, timeout=30
    )
    res.raise_for_status()
    audio_file = res.json()["audio_file"]
    stamps = audio_file.get("timestamps") or []
    if len(stamps) != n_ayahs:
        return None
    starts_ms = []
    for i, stamp in enumerate(stamps, 1):
        if stamp.get("verse_key") != f"{s_id}:{i}":
            return None
        starts_ms.append(int(stamp["timestamp_from"]))
    if any(b <= a for a, b in zip(starts_ms, starts_ms[1:])):
        return None
    url = audio_file["audio_url"]
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith("http"):
        url = "https://audio.qurancdn.com/" + url.lstrip("/")
    return url, starts_ms


def build_audio_continuous(s_id, edition, n_ayahs, work_dir):
    """تلاوة السورة كملف واحد متصل (من غير أي قطع)، والتوقيتات من Quran.com."""
    info = fetch_continuous(s_id, edition, n_ayahs)
    if not info:
        return None
    url, starts_ms = info
    src = os.path.join(work_dir, "full_surah.mp3")
    wav_path = os.path.join(work_dir, "audio.wav")
    download(url, src)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src, "-ac", "1", "-ar", str(SAMPLE_RATE),
         "-af", f"adelay={int(INTRO_SEC * 1000)}:all=1", wav_path],
        check=True,
    )
    os.remove(src)
    total = _wav_seconds(wav_path)
    if starts_ms[-1] / 1000 >= total - INTRO_SEC - 0.5:
        print("⚠️ توقيتات Quran.com مش متطابقة مع الملف، هتجاهلها.")
        return None
    starts = [INTRO_SEC] + [INTRO_SEC + ms / 1000 for ms in starts_ms[1:]]
    durations = [b - a for a, b in zip(starts, starts[1:])] + [total - starts[-1]]
    return wav_path, durations


def build_audio_ayah(ayahs, work_dir):
    """المسار الاحتياطي: آية-آية، بدمج ناعم (crossfade) وبدون فراغات صامتة بين الآيات."""
    import numpy as np

    wav_path = os.path.join(work_dir, "audio.wav")
    tmp = os.path.join(work_dir, "ayah.mp3")
    n_x = int(XFADE_SEC * SAMPLE_RATE)
    pos = int(INTRO_SEC * SAMPLE_RATE)
    bounds, tail = [], np.zeros(0, dtype=np.int16)

    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"\x00\x00" * pos)
        for i, ayah in enumerate(ayahs, 1):
            download(ayah["audio"], tmp)
            cur = np.frombuffer(decode_pcm(tmp), dtype=np.int16)
            os.remove(tmp)

            k = min(n_x, len(tail), len(cur) // 2)
            if k > 0:
                t = np.linspace(0.0, 1.0, k, dtype=np.float32)
                blend = tail[-k:].astype(np.float32) * np.cos(t * np.pi / 2) + cur[:k].astype(np.float32) * np.sin(t * np.pi / 2)
                w.writeframes(tail[:-k].tobytes())
                pos += len(tail) - k
                bounds.append(pos + k // 2)  # بداية الآية = منتصف منطقة الدمج
                w.writeframes(np.clip(blend, -32768, 32767).astype(np.int16).tobytes())
                pos += k
                cur = cur[k:]
            else:
                w.writeframes(tail.tobytes())
                pos += len(tail)
                bounds.append(pos)

            keep = min(n_x, len(cur))
            w.writeframes(cur[: len(cur) - keep].tobytes())
            pos += len(cur) - keep
            tail = cur[len(cur) - keep:]
            if i % 25 == 0 or i == len(ayahs):
                print(f"   🔊 الصوت: {i}/{len(ayahs)} آية")
        w.writeframes(tail.tobytes())
        pos += len(tail)

    durations = [(b - a) / SAMPLE_RATE for a, b in zip(bounds, bounds[1:])] + [(pos - bounds[-1]) / SAMPLE_RATE]
    return wav_path, durations


def build_audio(data, edition, work_dir):
    """يفضّل الملف المتصل للسورة؛ ولو مش متاح ينزل للمسار الاحتياطي. بيرجّع (wav, durations, mode)."""
    mode = os.environ.get("LONG_AUDIO_MODE", "auto").lower()
    if mode in ("auto", "continuous"):
        try:
            result = build_audio_continuous(data["id"], edition, len(data["ayahs"]), work_dir)
            if result:
                return result[0], result[1], "continuous"
            print("⚠️ التلاوة المتصلة مش متاحة لهذا القارئ/السورة.")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ فشل جلب التلاوة المتصلة: {exc}")
        if mode == "continuous":
            raise RuntimeError("LONG_AUDIO_MODE=continuous لكن التلاوة المتصلة غير متاحة.")
        print("   هستخدم آية-آية بدمج ناعم.")
    wav_path, durations = build_audio_ayah(data["ayahs"], work_dir)
    return wav_path, durations, "ayah"


# ================== الصور والإطارات ==================
def image_count(total_sec):
    return max(1, min(MAX_IMAGES, round(total_sec / IMAGE_EVERY_SEC)))


def image_index_for(start, total, n):
    return min(n - 1, int(start / total * n))


def make_backgrounds(plan, rng, work_dir):
    paths = []
    for k, item in enumerate(plan["items"]):
        img, source = long_images.generate_image(
            item["prompt"], rng.randint(1, 10**9), render.W, render.H, plan["palette"]
        )
        path = os.path.join(work_dir, f"bg_{k:02d}.jpg")
        render.prepare_background(img).save(path, "JPEG", quality=95)
        paths.append(path)
        print(f"   🖼️ خلفية {k + 1}/{len(plan['items'])} ({source})")
    return paths


def make_frames(ayahs, starts, durations, total, bg_paths, name, reciter, dur_txt, work_dir):
    from PIL import Image

    frames = []
    cache = {"idx": None, "img": None}

    def base_for(idx):
        if cache["idx"] != idx:
            cache["img"] = Image.open(bg_paths[idx]).convert("RGB")
            cache["idx"] = idx
        return cache["img"]

    title_path = os.path.join(work_dir, "frame_title.jpg")
    render.render_title_frame(base_for(0), name, reciter, len(ayahs), dur_txt, title_path)
    frames.append((title_path, INTRO_SEC))

    n_bg = len(bg_paths)
    for i, ayah in enumerate(ayahs):
        base = base_for(image_index_for(starts[i], total, n_bg))
        path = os.path.join(work_dir, f"frame_{i:04d}.jpg")
        render.render_ayah_frame(
            base, name, ayah["number"], ayah["ar"], ayah["en"], reciter,
            progress=(starts[i] + durations[i]) / total, idx=i + 1, total=len(ayahs), out_path=path,
        )
        frames.append((path, durations[i]))
        if (i + 1) % 50 == 0 or i + 1 == len(ayahs):
            print(f"   🎞️ الإطارات: {i + 1}/{len(ayahs)}")
    return frames


# ================== يوتيوب ==================
def youtube_authenticate():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_data = json.loads(base64.b64decode(os.environ["TOKEN_BASE64"]).decode("utf-8"))
    return build("youtube", "v3", credentials=Credentials.from_authorized_user_info(token_data))


def upload_video(youtube, path, title, description, tags):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": title, "description": description, "tags": tags,
            "categoryId": "22", "defaultLanguage": "ar", "defaultAudioLanguage": "ar",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=64 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response, retries = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"   ⬆️ الرفع: {int(status.progress() * 100)}%")
        except HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and retries < 8:
                retries += 1
                time.sleep(5 * retries)
                continue
            raise
        except (ConnectionError, TimeoutError, OSError):
            if retries >= 8:
                raise
            retries += 1
            time.sleep(5 * retries)

    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("لم تُرجع واجهة YouTube معرّف الفيديو بعد الرفع.")
    return video_id


def verify_uploaded_video(youtube, video_id):
    items = youtube.videos().list(part="id,snippet,status,processingDetails", id=video_id).execute().get("items", [])
    if not items:
        raise RuntimeError(f"تعذر قراءة الفيديو المرفوع {video_id} بعد الرفع.")
    video = items[0]
    own = youtube.channels().list(part="id", mine=True).execute().get("items", [])
    if own and video.get("snippet", {}).get("channelId") != own[0]["id"]:
        raise RuntimeError("تم الرفع إلى قناة غير القناة المصادق عليها.")
    if video.get("status", {}).get("privacyStatus") != "public":
        raise RuntimeError("تم الرفع لكن الفيديو ليس عامًا.")
    if video.get("processingDetails", {}).get("processingStatus") == "failed":
        raise RuntimeError("فشلت معالجة الفيديو في YouTube.")


def set_thumbnail(youtube, video_id, path, strict=False):
    """فشل الصورة المصغرة مش بيلغي النشر (غالبًا القناة محتاجة توثيق)."""
    from googleapiclient.http import MediaFileUpload

    try:
        youtube.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(path, mimetype="image/jpeg")
        ).execute()
        print("   ✅ تم ضبط الصورة المصغرة")
    except Exception as exc:  # noqa: BLE001
        if strict:
            raise
        print(f"::warning title=الصورة المصغرة::تعذر ضبطها ({exc})")


# ================== التشغيل ==================
def run(force=False, surah=None, dry_run=False):
    log = load_log()
    today = cairo_today()
    if not force and not is_due(log, today):
        print(f"ℹ️ لسه ما عدّاش {MIN_DAYS_BETWEEN} يوم على آخر فيديو طويل. مفيش نشر النهاردة.")
        return 0

    started = time.time()
    s_id = surah or log["next_surah"]
    rng = random.Random()
    last_reciter = log["uploads"][-1].get("reciter") if log["uploads"] else None
    edition = rng.choice([r for r in RECITERS if r != last_reciter] or RECITERS)
    reciter = RECITER_NAMES[edition]

    shutil.rmtree(WORK_DIR, ignore_errors=True)
    os.makedirs(WORK_DIR)
    try:
        print(f"📖 [1/5] جلب السورة رقم {s_id}...")
        data = fetch_surah(s_id, edition)
        name = clean_name(data["name"])

        print(f"🔊 [2/5] تجميع الصوت ({len(data['ayahs'])} آية) بصوت {reciter}...")
        wav_path, durations, audio_mode = build_audio(data, edition, WORK_DIR)
        starts, total = build_timeline(durations)
        print(f"   نوع الصوت: {audio_mode} | المدة الكلية: {fmt_ts(total)}")

        n_images = image_count(total)
        plan = prompts.plan_video(
            rng, n_images, log["used_prompt_ids"], log["recent_styles"], log["recent_palettes"]
        )
        print(f"🖼️ [3/5] توليد {n_images} صورة + الصورة المصغرة (من {prompts.total_combinations()} تركيبة)...")
        bg_paths = make_backgrounds(plan, rng, WORK_DIR)
        thumb_src, _ = long_images.generate_image(
            plan["thumb"]["prompt"], rng.randint(1, 10**9), render.W, render.H, plan["palette"]
        )
        thumb_path = os.path.join(WORK_DIR, "thumbnail.jpg")
        render.make_thumbnail(thumb_src, name, reciter, short_duration(total), thumb_path)

        print("🎞️ [4/5] رندر الإطارات والفيديو...")
        frames = make_frames(
            data["ayahs"], starts, durations, total, bg_paths, name, reciter, duration_text(total), WORK_DIR
        )
        video_path = os.path.join(WORK_DIR, "long_final.mp4")
        render.build_video(frames, wav_path, video_path, WORK_DIR)
        print(f"   حجم الفيديو: {os.path.getsize(video_path) / 1_000_000:.0f} MB")

        chapters = build_chapters(starts, data["ayahs"])
        recent_titles = [u.get("title_template") for u in log["uploads"] if u.get("title_template") is not None]
        title, description, tags, title_idx = build_metadata(rng, name, reciter, total, chapters, recent_titles)

        if dry_run:
            out_dir = "long_output"
            shutil.rmtree(out_dir, ignore_errors=True)
            os.makedirs(out_dir)
            shutil.copy(video_path, out_dir)
            shutil.copy(thumb_path, out_dir)
            with open(os.path.join(out_dir, "metadata.txt"), "w", encoding="utf-8") as f:
                f.write(f"{title}\n\n{description}\n\nTags: {', '.join(tags)}\n")
            print(f"✅ dry-run خلص. الملفات في {out_dir}/ (الوقت: {(time.time() - started) / 60:.1f} دقيقة)")
            return 0

        print("📡 [5/5] الرفع لليوتيوب...")
        youtube = youtube_authenticate()
        video_id = upload_video(youtube, video_path, title, description, tags)

        # نسجّل فورًا بعد نجاح الرفع، قبل أي فحص، عشان أي خطأ بعده ما يعمل رفع مكرر.
        record = {
            "date": today.isoformat(),
            "uploaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "video_id": video_id,
            "url": f"https://youtu.be/{video_id}",
            "title": title,
            "surah_id": s_id,
            "reciter": edition,
            "title_template": title_idx,
            "style": plan["style"],
            "palette": plan["palette"],
            "duration_sec": round(total),
            "audio_mode": audio_mode,
        }
        log["uploads"] = (log["uploads"] + [record])[-60:]
        if surah is None:  # رفع سورة يدويًا ما بيحرّكش الدور
            log["next_surah"] = following_surah(s_id)
        log["used_prompt_ids"] = (
            log["used_prompt_ids"] + [i["id"] for i in plan["items"]] + [plan["thumb"]["id"]]
        )[-MAX_LOG_PROMPTS:]
        log["recent_styles"] = (log["recent_styles"] + [plan["style"]])[-6:]
        log["recent_palettes"] = (log["recent_palettes"] + [plan["palette"]])[-6:]
        save_log(log)

        # الفحص اختياري: التوكن الحالي غالبًا صلاحيته رفع فقط (مش قراءة).
        try:
            verify_uploaded_video(youtube, video_id)
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=فحص الفيديو::تخطيت الفحص بعد الرفع ({exc})")
        set_thumbnail(youtube, video_id, thumb_path)
        print(f"✅ تم النشر: {record['url']} ({(time.time() - started) / 60:.1f} دقيقة)")
        return 0
    finally:
        shutil.rmtree(WORK_DIR, ignore_errors=True)


def thumb_only(video_id, surah_id):
    """يعمل صورة مصغرة جديدة لفيديو مرفوع بالفعل ويضبطها عليه (بدون رندر أو رفع)."""
    log = load_log()
    rng = random.Random()
    data = api_get(f"{API}/surah/{surah_id}")
    name = clean_name(data["name"])
    plan = prompts.plan_video(rng, 1, log["used_prompt_ids"], log["recent_styles"], log["recent_palettes"])
    print(f"🖼️ توليد الصورة المصغرة لـ{name}...")
    img, source = long_images.generate_image(
        plan["thumb"]["prompt"], rng.randint(1, 10**9), render.W, render.H, plan["palette"]
    )
    print(f"   المصدر: {source}")
    os.makedirs(WORK_DIR, exist_ok=True)
    try:
        path = os.path.join(WORK_DIR, "thumbnail.jpg")
        render.make_thumbnail(img, name, RECITER_NAMES["ar.alafasy"], None, path)
        set_thumbnail(youtube_authenticate(), video_id, path, strict=True)
    finally:
        shutil.rmtree(WORK_DIR, ignore_errors=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description="نشر فيديو قرآن طويل (سورة كاملة).")
    parser.add_argument("--force", action="store_true", help="تجاهل شرط اليومين")
    parser.add_argument("--surah", type=int, help="رقم سورة معيّنة")
    parser.add_argument("--dry-run", action="store_true", help="رندر بدون رفع")
    parser.add_argument("--thumb-only", metavar="VIDEO_ID", help="صورة مصغرة لفيديو مرفوع (مع --surah)")
    args = parser.parse_args()
    try:
        if args.thumb_only:
            if not args.surah:
                parser.error("--thumb-only محتاج --surah")
            sys.exit(thumb_only(args.thumb_only, args.surah))
        sys.exit(run(force=args.force or bool(args.surah), surah=args.surah, dry_run=args.dry_run))
    except Exception as exc:  # noqa: BLE001
        print("فشل التشغيل:", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
