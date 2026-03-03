import os, requests, random, json, base64, sys
from datetime import datetime
import numpy as np
import moviepy.editor as mp
from moviepy.video.fx.all import loop 
from moviepy.audio.fx.all import audio_fadeout
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ================== 1. الإعدادات الأساسية (1080p) ==================
WIDTH = 1080
HEIGHT = 1920
LOG_FILE = "daily_log.txt"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

# قائمة القراء (أعلى جودة متاحة من API)
RECITERS = [
    'ar.alafasy', 'ar.abdulbasitmurattal', 'ar.husary', 
    'ar.mahermuaiqly', 'ar.sudais', 'ar.ahmedajamy'
]

# كلمات البحث (طبيعة صامتة فقط - لا بشر ولا حيوانات)
SAFE_QUERIES = [
    "dark sky stars clouds", "ocean sea waves blue", 
    "forest trees aerial", "galaxy nebula cosmos", 
    "abstract islamic patterns", "mecca kaaba close up"
]

# الخطوط (تأكد من وجود الملفات في نفس المجلد)
FONT_PATH_AR = "Amiri-Regular.ttf" 
FONT_PATH_EN = "Roboto-Regular.ttf"

# إعداد معالج النصوص العربية للمحافظة على التشكيل
reshaper = arabic_reshaper.ArabicReshaper(configuration={
    'delete_harakat': False, 
    'support_ligatures': True,
    'use_unshaped_instead_of_isolated': True
})

# ================== 2. دوال المساعدة ==================

def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def is_uploaded_today():
    if not os.path.exists(LOG_FILE): return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return f.read().strip() == today_str()

def mark_uploaded_today():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(today_str())

def process_text(t):
    try: return get_display(reshaper.reshape(t))
    except: return t

def split_text_into_single_lines(text, max_chars=45):
    """تقسيم الآية لسطر واحد فقط بناءً على عدد الحروف"""
    words = text.split()
    lines = []
    current_line = []
    current_length = 0
    for word in words:
        if current_length + len(word) <= max_chars:
            current_line.append(word)
            current_length += len(word) + 1
        else:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word) + 1
    if current_line: lines.append(" ".join(current_line))
    return lines

def draw_frame(text_ar, text_en, font_ar, font_en):
    """رسم المشهد (سطر واحد عربي وسطر واحد إنجليزي)"""
    img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    ar_ready = process_text(text_ar)
    en_ready = text_en[:65] + "..." if len(text_en) > 65 else text_en

    def draw_w_shadow(pos, txt, font, color):
        x, y = pos
        # ظل ناعم لزيادة الوضوح
        offsets = [(-2,-2), (2,2), (-2,2), (2,-2), (0,3), (0,-3)]
        for ox, oy in offsets:
            d.text((x+ox, y+oy), txt, font=font, fill="black", anchor="mm")
        d.text((x, y), txt, font=font, fill=color, anchor="mm")

    draw_w_shadow((WIDTH/2, HEIGHT/2 - 60), ar_ready, font_ar, "white")
    draw_w_shadow((WIDTH/2, HEIGHT/2 + 80), en_ready, font_en, "#D0D0D0")
    
    return np.array(img)

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

# ================== 3. محرك صناعة الفيديو ==================

def build_shorts_video():
    print("🚀 [1/4] جلب البيانات والصوت عالي الجودة...")
    reciter = random.choice(RECITERS)
    s_id = random.randint(1, 114)
    
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{reciter}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']

    audio_clips = []
    text_clips = []
    current_time = 0.0
    gap = 0.1 # فاصل صغير جداً لمنع التقطيع

    f_ar = ImageFont.truetype(FONT_PATH_AR, 90)
    f_en = ImageFont.truetype(FONT_PATH_EN, 45)
    f_title = ImageFont.truetype(FONT_PATH_AR, 130)

    for i in range(len(res_ar['ayahs'])):
        a_ar = res_ar['ayahs'][i]
        a_en = res_en['ayahs'][i]
        
        # تحميل الصوت
        f_path = f"temp_{i}.mp3"
        with open(f_path, 'wb') as f: f.write(requests.get(a_ar['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        
        # تقسيم الآية لسطور أحادية متزامنة
        ar_lines = split_text_into_single_lines(a_ar['text'])
        # تقسيم مماثل للإنجليزي لضمان التزامن
        en_words = a_en['text'].split()
        n = len(ar_lines)
        en_lines = [" ".join(en_words[i*len(en_words)//n : (i+1)*len(en_words)//n]) for i in range(n)]
        
        line_dur = clip.duration / n
        for j in range(n):
            start_t = current_time + (j * line_dur)
            end_t = start_t + line_dur
            
            img_arr = draw_frame(ar_lines[j], en_lines[j], f_ar, f_en)
            t_clip = mp.ImageClip(img_arr).set_start(start_t).set_end(end_t)
            text_clips.append(t_clip)

        audio_clips.append(clip)
        current_time += clip.duration + gap
        if i < len(res_ar['ayahs'])-1:
            audio_clips.append(mp.AudioClip(lambda t: [0,0], duration=gap))

        if current_time >= 58: break

    print("⚙️ [2/4] معالجة الخلفية والمونتاج...")
    final_audio = mp.concatenate_audioclips(audio_clips)
    dur = min(59.0, final_audio.duration)
    final_audio = audio_fadeout(final_audio.subclip(0, dur), 1.5)

    # جلب خلفية "جمادات" فقط من Pexels
    headers = {'Authorization': PEXELS_API_KEY}
    v_res = requests.get(f'https://api.pexels.com/videos/search?query={random.choice(SAFE_QUERIES)}&orientation=portrait&per_page=10', headers=headers).json()
    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)

    bg_clip = mp.VideoFileClip("bg_v.mp4").resize(height=HEIGHT)
    bg_clip = bg_clip.crop(x1=bg_clip.w/2-WIDTH/2, y1=0, width=WIDTH, height=HEIGHT)
    bg = loop(bg_clip, duration=dur)
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=dur).set_opacity(0.4)

    # عنوان السورة الثابت
    title_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    d_title = ImageDraw.Draw(title_img)
    d_title.text((WIDTH/2, 250), process_text(s_name), font=f_title, fill="white", anchor="mm", stroke_width=2, stroke_fill="black")
    title_clip = mp.ImageClip(np.array(title_img)).set_duration(dur)

    # التجميع النهائي
    final_video = mp.CompositeVideoClip([bg, dark, title_clip] + text_clips).set_audio(final_audio)

    print("⏳ [3/4] رندر بجودة 12Mbps...")
    final_video.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="12000k", preset="ultrafast", logger=None, threads=4)

    print("📡 [4/4] الرفع إلى يوتيوب...")
    youtube = youtube_authenticate()
    body = {
        'snippet': {
            'title': f'تلاوة خاشعة - سورة {s_name} #shorts #quran',
            'description': f'سورة {s_name} بصوت القارئ {reciter}',
            'categoryId': '22'
        },
        'status': {'privacyStatus': 'public'}
    }
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)).execute()
    print(f"✅ تم الرفع بنجاح! القارئ: {reciter}")

# ================== 4. التشغيل الرئيسي ==================
if __name__ == "__main__":
    if not is_uploaded_today() or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        try:
            build_shorts_video()
            mark_uploaded_today()
        except Exception as e:
            print(f"🔥 خطأ فادح: {e}")
            sys.exit(1)
