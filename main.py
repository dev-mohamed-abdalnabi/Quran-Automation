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

# ================== إعدادات الأبعاد ==================
WIDTH = 1080
HEIGHT = 1920

# ================== سجل يومي ==================
LOG_FILE = "daily_log.txt"

def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def is_uploaded_today():
    if not os.path.exists(LOG_FILE): return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return f.read().strip() == today_str()

def mark_uploaded_today():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(today_str())

# ================== الإعدادات والخطوط ==================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

# قائمة قراء متنوعة (عاديين بدون حقوق معقدة)
RECITERS = [
    'ar.alafasy',      # مشاري العفاسي
    'ar.shaatree',     # أبو بكر الشاطري
    'ar.ajamy',        # أحمد العجمي
    'ar.husary',       # الحصري
    'ar.minshawi',     # المنشاوي
    'ar.saoodshuraym', # سعود الشريم
    'ar.abdulsamad'    # عبد الباسط
]

FONT_PATH_AR = "Amiri-Regular.ttf" 
FONT_PATH_EN = "Roboto-Regular.ttf"

reshaper_new = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})

def process_ar_new(t):
    try: return get_display(reshaper_new.reshape(t))
    except: return t

def safe_wrap(text, width):
    words = text.split()
    lines = []
    current_line = []
    current_length = 0
    for word in words:
        if current_length + len(word) <= width:
            current_line.append(word)
            current_length += len(word) + 1
        else:
            if current_line: lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word) + 1
    if current_line: lines.append(" ".join(current_line))
    return lines

def draw_text_with_shadow(draw, pos, text, font, fill_color):
    x, y = pos
    shadow_color = "black"
    offsets = [(4,4), (-4,4), (4,-4), (-4,-4)]
    for ox, oy in offsets:
        draw.text((x+ox, y+oy), text, font=font, fill=shadow_color, anchor="mm")
    draw.text((x, y), text, font=font, fill=fill_color, anchor="mm")

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🚀 [1/4] تحضير الموارد والشيخ...")
    
    s_id = random.randint(1, 114)
    chosen_reciter = random.choice(RECITERS)
    
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{chosen_reciter}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    audio_clips = []
    text_parts_ar = []
    text_parts_en = []
    current_total_duration = 0

    # تحميل الآيات حتى 58 ثانية لضمان جودة الـ Shorts
    for i, (a_ar, a_en) in enumerate(zip(res_ar['ayahs'], res_en['ayahs'])):
        f_path = f"temp_{i}.mp3"
        with open(f_path, 'wb') as f:
            f.write(requests.get(a_ar['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        # إزالة الصمت البسيط من أطراف المقطع لتقليل التقطيع
        clip = clip.subclip(0.1, clip.duration - 0.1) if clip.duration > 0.3 else clip
        
        audio_clips.append(clip)
        text_parts_ar.append(a_ar['text'])
        text_parts_en.append(a_en['text'])
        
        current_total_duration += clip.duration
        if current_total_duration >= 55: break

    # --- معالجة الصوت بدمج ناعم (Smooth Chain) ---
    final_audio = mp.concatenate_audioclips(audio_clips, method="chain")
    dur = min(59.0, final_audio.duration)
    final_audio = final_audio.subclip(0, dur)
    
    # حساب التوقيتات بناءً على أطوال الكليبات الفعلية
    starts = [0.0]
    for clip in audio_clips:
        starts.append(starts[-1] + clip.duration)

    # اختيار خلفية آمنة (بدون كائنات حية)
    headers = {'Authorization': PEXELS_API_KEY}
    safe_queries = ["milky way", "nebula galaxy", "abstract wave", "storm clouds aerial", "mountain tops", "ocean deep blue"]
    q = random.choice(safe_queries)
    v_res = requests.get(f'https://api.pexels.com/videos/search?query={q}&orientation=portrait&per_page=10', headers=headers).json()
    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)

    print(f"⚙️ [2/4] المونتاج البصري...")
    bg = loop(mp.VideoFileClip("bg_v.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT), duration=dur)
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=dur).set_opacity(0.5)

    font_ar = ImageFont.truetype(FONT_PATH_AR, 90) 
    font_en = ImageFont.truetype(FONT_PATH_EN, 42)
    font_s = ImageFont.truetype(FONT_PATH_AR, 130)

    text_clips = []
    for i in range(len(audio_clips)):
        c_start = starts[i]
        c_end = starts[i+1]
        if c_start >= dur: break

        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        
        ar_lines = safe_wrap(text_parts_ar[i], width=35)
        en_lines = safe_wrap(text_parts_en[i], width=40)
        
        # توسيط النص عمودياً
        total_h = (len(ar_lines)*120) + 60 + (len(en_lines)*55)
        y_cursor = (HEIGHT - total_h) / 2
        
        for line in ar_lines:
            draw_text_with_shadow(d, (WIDTH/2, y_cursor), process_ar_new(line), font_ar, "white")
            y_cursor += 120
        y_cursor += 60
        for line in en_lines:
            d.text((WIDTH/2, y_cursor), line, font=font_en, fill="#E0E0E0", anchor="mm", stroke_width=1, stroke_fill="black")
            y_cursor += 55
        
        t_clip = mp.ImageClip(np.array(img)).set_start(c_start).set_end(min(c_end, dur))
        text_clips.append(t_clip)

    # إضافة اسم السورة في الأعلى
    title_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_text_with_shadow(ImageDraw.Draw(title_img), (WIDTH/2, 200), process_ar_new(s_name), font_s, "#FFD700") # لون ذهبي خفيف
    title_clip = mp.ImageClip(np.array(title_img)).set_duration(dur).set_opacity(0.8)

    final = mp.CompositeVideoClip([bg, dark, title_clip] + text_clips).set_audio(final_audio)

    print("⏳ [3/4] رندر...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast", logger=None)

    print("📡 [4/4] الرفع لليوتيوب...")
    youtube = youtube_authenticate()
    body = {
        'snippet': {
            'title': f'تلاوة هادئة: سورة {s_name} | القارئ {chosen_reciter.split(".")[1].capitalize()}',
            'description': f'تلاوة من سورة {s_name} بصوت {chosen_reciter}. #shorts #quran #islam',
            'categoryId': '22'
        },
        'status': {'privacyStatus': 'public'}
    }
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)).execute()
    print(f"✅ تم الرفع بنجاح!")

if __name__ == "__main__":
    # تشغيل الكود إذا كان اليوم جديداً أو تم التشغيل يدوياً
    if not is_uploaded_today() or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        try:
            build_shorts_video()
            mark_uploaded_today()
        except Exception as e:
            print("🔥 حدث خطأ:", e); sys.exit(1)
