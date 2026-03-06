
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

# ================== إعدادات الأبعاد (Full HD 1080p) ==================
WIDTH = 1080
HEIGHT = 1920

BOX_X = 75
BOX_Y = 420
BOX_W = 930
BOX_H = 1125
BOX_OPACITY = 160

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

# ================== الإعدادات والخطوط ==================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
AUDIO_EDITION = 'ar.alafasy'

FONT_PATH_AR = "Amiri-Regular.ttf" 
FONT_PATH_EN = "Roboto-Regular.ttf"

reshaper_old = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': True, 'support_ligatures': True})
reshaper_new = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})

def process_ar_old(t):
    try: return get_display(reshaper_old.reshape(t))[::-1]
    except: return t

def process_ar_new(t):
    try: return get_display(reshaper_new.reshape(t))[::-1]
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
    offsets = [(3,3), (-3,3), (3,-3), (-3,-3), (0,3), (0,-3), (3,0), (-2,0)]
    for ox, oy in offsets:
        draw.text((x+ox, y+oy), text, font=font, fill=shadow_color, anchor="mm")
    draw.text((x, y), text, font=font, fill=fill_color, anchor="mm")

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🚀 [1/4] تحضير الموارد (1080p)...")
    
    s_id = random.randint(1, 114)
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    audio_clips = []
    text_parts_ar = []
    text_parts_en = []
    current_duration = 0

    for i, (a_ar, a_en) in enumerate(zip(res_ar['ayahs'], res_en['ayahs'])):
        f_path = f"temp_{i}.mp3"
        with open(f_path, 'wb') as f:
            f.write(requests.get(a_ar['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        audio_clips.append(clip)
        text_parts_ar.append(a_ar['text'])
        text_parts_en.append(a_en['text'])
        
        current_duration += clip.duration
        if current_duration >= 50: break

    # --- معالجة الصوت بدون تقطيع ---
    final_audio = mp.concatenate_audioclips(audio_clips)
    dur = min(70.0, final_audio.duration)
    final_audio = final_audio.subclip(0, dur)
    
    # حساب توقيتات الآيات بدقة بناءً على الترتيب المتتالي
    starts = [0.0]
    for clip in audio_clips[:-1]:
        starts.append(starts[-1] + clip.duration)

     # اختيار خلفية "آمنة" (جبال، سحاب، صحراء) بعيداً عن التماثيل والناس
    print("🎬 [2/4] اختيار خلفية طبيعية آمنة...")
    PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
    headers = {'Authorization': PEXELS_API_KEY}
    # كلمات بحث دقيقة لمنع التماثيل
    safe_queries = ['mountains', 'clouds', 'desert', 'galaxy', 'sky night']
    query = random.choice(safe_queries)
    
    v_res = requests.get(f'https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=15', headers=headers).json()
    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)
    
    print(f"⚙️ [2/4] المونتاج...")
    bg = loop(mp.VideoFileClip("bg_v.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT), duration=dur)
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=dur).set_opacity(0.4)

    font_ar = ImageFont.truetype(FONT_PATH_AR, 95) 
    font_en = ImageFont.truetype(FONT_PATH_EN, 45)
    font_s = ImageFont.truetype(FONT_PATH_AR, 140)

    text_clips = []
    for i in range(len(audio_clips)):
        c_start = starts[i]
        c_end = starts[i+1] if i < len(starts)-1 else dur
        if c_start >= dur: break

        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        
        ar_lines = safe_wrap(text_parts_ar[i], width=40)
        en_lines = safe_wrap(text_parts_en[i], width=35)
        
        y_off = (HEIGHT - (len(ar_lines)*130 + 50 + len(en_lines)*60)) / 2
        for line in ar_lines:
            draw_text_with_shadow(d, (WIDTH/2, y_off), process_ar_new(line), font_ar, "white")
            y_off += 130
        y_off += 50
        for line in en_lines:
            d.text((WIDTH/2, y_off), line, font=font_en, fill="#F0F0F0", anchor="mm", stroke_width=2, stroke_fill="black")
            y_off += 60
        
        t_clip = mp.ImageClip(np.array(img)).set_start(c_start).set_end(min(c_end, dur))
        text_clips.append(t_clip)

    title_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_text_with_shadow(ImageDraw.Draw(title_img), (WIDTH/2, 250), process_ar_new(s_name), font_s, "white")
    title_clip = mp.ImageClip(np.array(title_img)).set_duration(dur)

    final = mp.CompositeVideoClip([bg, dark, title_clip] + text_clips).set_audio(final_audio)

    print("⏳ [3/4] رندر سريع (1080p)...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="10000k", preset="ultrafast", logger=None, threads=4)

    print("📡 [4/4] الرفع...")
    youtube = youtube_authenticate()
    body = {'snippet': {'title': f'تلاوة خاشعة - {s_name} #shorts #quran', 'description': f'سورة {s_name}', 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)).execute()
    print(f"✅ تم بنجاح بجودة 1080p!")

if __name__ == "__main__":
    if not is_uploaded_today() or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        try:
            build_shorts_video()
            mark_uploaded_today()
        except Exception as e:
            print("🔥 خطأ:", e); sys.exit(1)

