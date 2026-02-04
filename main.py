import os, requests, random, json, base64, textwrap, sys
from datetime import datetime
import numpy as np
import moviepy.editor as mp
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ================== الثوابت الهندسية (عشان كله يظبط على كله) ==================
# حدود المربع الشفاف (بالبكسل)
BOX_TOP = 260
BOX_BOTTOM = 1040
BOX_LEFT = 50
BOX_RIGHT = 670
BOX_RADIUS = 30
# الشفافية (0 = شفاف خالص، 255 = معتم)
BOX_OPACITY = 140 

# ================== سجل يومي ==================
LOG_FILE = "daily_log.txt"

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

# ================== الإعدادات ==================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
AUDIO_EDITION = 'ar.alafasy'
FONT_PATH = "ArabicFont.ttf"

def process_ar(t):
    try:
        reshaped = arabic_reshaper.reshape(t)
        bidi_text = get_display(reshaped)
        return bidi_text[::-1]
    except:
        return t

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🚀 [1/4] جاري التجهيز...")

    s_id = random.randint(1, 114)
    res = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    s_name = res['name']
    all_ayahs = res['ayahs']

    # تجميع الآيات
    audio_clips = []
    text_parts = []
    current_duration = 0
    TARGET_DURATION = 35 

    for i, a in enumerate(all_ayahs):
        f_path = f"temp_{i}.mp3"
        with open(f_path, 'wb') as f:
            f.write(requests.get(a['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        audio_clips.append(clip)
        text_parts.append(a['text'])
        current_duration += clip.duration

        if current_duration >= TARGET_DURATION:
            if current_duration > 58: 
                audio_clips.pop()
                text_parts.pop()
            break
    
    final_audio = mp.concatenate_audioclips(audio_clips)
    dur = min(59, final_audio.duration)
    final_audio = final_audio.subclip(0, dur)
    full_text = " ۞ ".join(text_parts)

    # الخلفية
    headers = {'Authorization': PEXELS_API_KEY}
    v_res = requests.get(
        'https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15',
        headers=headers
    ).json()

    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f:
        f.write(requests.get(v_url).content)

    print(f"⚙️ [2/4] المونتاج وضبط الطبقات...")

    # الطبقة 1: الفيديو الخلفي
    bg = mp.VideoFileClip("bg_v.mp4").resize(height=1280).crop(x1=0, y1=0, width=720, height=1280).set_duration(dur)
    dark = mp.ColorClip(size=(720, 1280), color=(0,0,0), duration=dur).set_opacity(0.4)

    # الطبقة 2: المربع الشفاف (باستخدام الثوابت)
    box_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    box_draw = ImageDraw.Draw(box_canvas)
    # رسم المربع بناءً على الثوابت
    box_draw.rounded_rectangle(
        [BOX_LEFT, BOX_TOP, BOX_RIGHT, BOX_BOTTOM], 
        radius=BOX_RADIUS, 
        fill=(0,0,0,BOX_OPACITY)
    )
    box_clip = mp.ImageClip(np.array(box_canvas)).set_duration(dur)

    # الطبقة 3: النص المتحرك
    lines = textwrap.wrap(full_text, width=28)
    line_h = 95
    canvas_h = (len(lines) + 3) * line_h # مساحة إضافية
    txt_img = Image.new('RGBA', (600, canvas_h), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(txt_img)
    font_a = ImageFont.truetype(FONT_PATH, 48)

    for i, line in enumerate(lines):
        d_t.text((300, i*line_h + 100), process_ar(line), font=font_a, fill="white", anchor="mm")

    txt_clip = mp.ImageClip(np.array(txt_img)).set_duration(dur)
    
    # حساب الحركة:
    # البداية: تحت المربع بـ 50 بكسل (BOX_BOTTOM + 50) عشان يطلع بالتدريج
    start_y = BOX_BOTTOM + 50
    # النهاية: النص يخلص كله ويطلع فوق المربع
    end_y = BOX_TOP - canvas_h 
    
    moving_txt = txt_clip.set_position(lambda t: ('center', start_y - (t * ((start_y - end_y) / dur))))

    # الـ Masking (المقص): لازم يكون جوه حدود المربع بالظبط (+10 هامش عشان الشكل)
    text_area = mp.CompositeVideoClip([moving_txt], size=(720, 1280))\
                .crop(
                    x1=BOX_LEFT, 
                    y1=BOX_TOP + 10,   # يقص من تحت الحافة العلوية للمربع
                    x2=BOX_RIGHT, 
                    y2=BOX_BOTTOM - 10 # يقص قبل الحافة السفلية للمربع
                )\
                .set_position(('center', 0))

    # الطبقة 4: العنوان (اسم السورة) - ثابت فوق المربع
    title_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    title_draw = ImageDraw.Draw(title_canvas)
    font_s = ImageFont.truetype(FONT_PATH, 85)
    # مكان العنوان: فوق بداية النص المتحرك بشوية
    title_y_pos = BOX_TOP - 60 
    title_draw.text((360, title_y_pos), process_ar(s_name), font=font_s, fill="#FFD700", anchor="mm")
    title_clip = mp.ImageClip(np.array(title_canvas)).set_duration(dur)

    # الترتيب: خلفية -> مربع -> نص مقصوص -> عنوان
    final = mp.CompositeVideoClip([bg, dark, box_clip, text_area, title_clip]).set_audio(final_audio)

    print("⏳ [3/4] الرندر...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", logger=None, threads=4)

    print("📡 [4/4] الرفع...")
    youtube = youtube_authenticate()

    body = {
        'snippet': {
            'title': f'تلاوة خاشعة - {s_name} #shorts #quran',
            'description': f'سورة {s_name} بصوت مشاري العفاسي',
            'categoryId': '22'
        },
        'status': {'privacyStatus': 'public'}
    }

    media = MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()

    print(f"✅ تم النشر: {s_name}")

if __name__ == "__main__":
    event_name = os.environ.get('GITHUB_EVENT_NAME')

    if is_uploaded_today():
        if event_name == 'workflow_dispatch':
            print("⚠️ تشغيل يدوي: جاري إنشاء نسخة إضافية...")
        else:
            print("✅ تخطي (تم النشر مسبقاً).")
            sys.exit(0)
    
    try:
        build_shorts_video()
        mark_uploaded_today()
        print("📝 تم.")
    except Exception as e:
        print("🔥 خطأ:", e)
        sys.exit(1)
