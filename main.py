import os, requests, random, json, base64, sys
from datetime import datetime
import numpy as np
import moviepy.editor as mp
from moviepy.video.fx.all import loop
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

WIDTH = 1080
HEIGHT = 1920

LOG_FILE = "daily_log.txt"

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

AUDIO_EDITION = "ar.alafasy"

FONT_PATH_AR = "Amiri-Regular.ttf"
FONT_PATH_EN = "Roboto-Regular.ttf"


def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")


def is_uploaded_today():
    if not os.path.exists(LOG_FILE):
        return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return f.read().strip() == today_str()


def mark_uploaded_today():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(today_str())


def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode("utf-8"))
    creds = Credentials.from_authorized_user_info(token_data)
    return build("youtube", "v3", credentials=creds)


# ================= AI =================

def ai_analyze(channel_stats, news, hijri_date):

    prompt = f"""
انت خبير يوتيوب اسلامي.

هذه احصائيات القناة:
{channel_stats}

اليوم:
{hijri_date}

اخر الاخبار:
{news}

اقترح:
عنوان فيديو قصير
وصف
هاشتاجات
"""

    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama3-70b-8192",
            "messages": [{"role": "user", "content": prompt}],
        },
    )

    data = r.json()

    try:
        return data["choices"][0]["message"]["content"]
    except:
        return "تلاوة خاشعة من القرآن الكريم #quran #shorts"


# ================= API =================

def get_hijri_date():

    r = requests.get(
        "https://api.aladhan.com/v1/gToH?date=" + datetime.utcnow().strftime("%d-%m-%Y")
    ).json()

    d = r["data"]["hijri"]

    return f"{d['day']} {d['month']['ar']} {d['year']} هجري"


def get_news():

    try:

        r = requests.get(
            "https://newsapi.org/v2/everything?q=islam&quran&language=ar&pageSize=2"
        )

        data = r.json()

        return [a["title"] for a in data["articles"]]

    except:

        return []


def get_channel_stats(youtube):

    try:

        res = (
            youtube.channels()
            .list(part="statistics", mine=True)
            .execute()
        )

        stats = res["items"][0]["statistics"]

        return stats

    except:

        return {}


# ================= الفيديو =================

def build_shorts_video():

    youtube = youtube_authenticate()

    stats = get_channel_stats(youtube)
    news = get_news()
    hijri = get_hijri_date()

    ai_text = ai_analyze(stats, news, hijri)

    print("AI Result:", ai_text)

    s_id = random.randint(1, 114)

    res_ar = requests.get(
        f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}"
    ).json()["data"]

    res_en = requests.get(
        f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih"
    ).json()["data"]

    s_name = res_ar["name"]

    audio_clips = []
    text_parts_ar = []
    text_parts_en = []

    duration = 0

    for i, (a_ar, a_en) in enumerate(zip(res_ar["ayahs"], res_en["ayahs"])):

        path = f"temp{i}.mp3"

        with open(path, "wb") as f:
            f.write(requests.get(a_ar["audio"]).content)

        clip = mp.AudioFileClip(path)

        audio_clips.append(clip)

        text_parts_ar.append(a_ar["text"])
        text_parts_en.append(a_en["text"])

        duration += clip.duration

        if duration >= 50:
            break

    final_audio = mp.concatenate_audioclips(audio_clips)

    dur = min(59, final_audio.duration)

    headers = {"Authorization": PEXELS_API_KEY}

    v = requests.get(
        "https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=10",
        headers=headers,
    ).json()

    url = random.choice(v["videos"])["video_files"][0]["link"]

    with open("bg.mp4", "wb") as f:
        f.write(requests.get(url).content)

    bg = loop(
        mp.VideoFileClip("bg.mp4")
        .resize(height=HEIGHT)
        .crop(x1=0, y1=0, width=WIDTH, height=HEIGHT),
        duration=dur,
    )

    final = bg.set_audio(final_audio)

    final.write_videofile(
        "final.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac",
        bitrate="10000k",
        preset="ultrafast",
    )

    body = {
        "snippet": {
            "title": f"{s_name} | تلاوة خاشعة #shorts",
            "description": ai_text,
            "categoryId": "22",
        },
        "status": {"privacyStatus": "public"},
    }

    youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload("final.mp4", resumable=True),
    ).execute()

    print("تم الرفع بنجاح")


if __name__ == "__main__":

    if not is_uploaded_today() or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":

        try:

            build_shorts_video()

            mark_uploaded_today()

        except Exception as e:

            print("خطأ", e)

            sys.exit(1)
