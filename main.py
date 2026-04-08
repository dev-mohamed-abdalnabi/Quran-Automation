import os, requests, random, json, base64, sys, glob
from datetime import datetime
import numpy as np
import moviepy.editor as mp
from moviepy.video.fx.all import loop 
from PIL import Image, ImageFont, ImageDraw
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ================== إعدادات الأبعاد ==================
WIDTH = 1080
HEIGHT = 1920

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

# ================== إعدادات الشيوخ والخطوط ==================
RECITERS = ['ar.alafasy', 'ar.husary', 'ar.minshawi']
AUDIO_EDITION = random.choice(RECITERS)

FONT_PATH_AR = "ArabicFont.ttf" 
FONT_PATH_EN = "Roboto-Regular.ttf"

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

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def fetch_quran_chunk():
    MAX_DURATION = 58.0
    print("⏳ جاري البحث عن مقطع قرآني...")
    
    while True:
        s_id = random.randint(1, 114)
        try:
            res_audio = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
            res_text_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/quran-simple").json()['data']
            res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
        except Exception:
            continue
            
        s_name = res_audio['name']
        total_ayahs = len(res_audio['ayahs'])
        start_idx = random.randint(0, total_ayahs - 1)
        
        audio_clips = []
        text_parts_ar = []
        text_parts_en = []
        current_duration = 0
        
        for i in range(start_idx, total_ayahs):
            a_audio = res_audio['ayahs'][i]
            a_ar = res_text_ar['ayahs'][i]
            a_en = res_en['ayahs'][i]
            
            ar_text = a_ar['text']
            
            basmala = "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ "
            if s_id != 1 and i == 0 and ar_text.startswith(basmala):
                ar_text = ar_text.replace(basmala, "")
            
            f_path = f"temp_{i}.mp3"
            with open(f_path, 'wb') as f:
                f.write(requests.get(a_audio['audio']).content)
            
            # 🔥 الحل الجذري: Micro-fade لمدة 0.02 ثانية (20 ملي ثانية) تمنع الطق تماماً بدون أي قطع ملحوظ في الصوت
            clip = mp.AudioFileClip(f_path)
            clip = clip.fx(mp.afx.audio_fadein, 0.02).fx(mp.afx.audio_fadeout, 0.02)
            
            if current_duration + clip.duration > MAX_DURATION:
                clip.close()
                os.remove(f_path)
                break
            else:
                audio_clips.append(clip)
                text_parts_ar.append(ar_text)
                text_parts_en.append(a_en['text'])
                current_duration += clip.duration
                
        if len(audio_clips) > 0:
            end_idx = start_idx + len(audio_clips) - 1
            return audio_clips, text_parts_ar, text_parts_en, current_duration, s_name, start_idx + 1, end_idx + 1
        else:
            continue

def build_shorts_video():
    print("🚀 [1/4] تحضير الموارد (1080p)...")
    
    audio_clips, text_parts_ar, text_parts_en, dur, s_name, start_ayah, end_ayah = fetch_quran_chunk()
    
    final_audio = mp.concatenate_audioclips(audio_clips)
    final_audio = final_audio.fx(mp.afx.audio_fadein, 1.0).fx(mp.afx.audio_fadeout, 1.0)
    
    starts = [0.0]
    for clip in audio_clips[:-1]:
        starts.append(starts[-1] + clip.duration)

    print("🎬 [2/4] اختيار خلفية طبيعية...")
    PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
    headers = {'Authorization': PEXELS_API_KEY}
    
    safe_queries = ['empty desert nature', 'clouds in sky', 'dark starry night sky', 'mountain landscape empty', 'ocean waves aerial']
    query = random.choice(safe_queries)
    
    v_res = requests.get(f'https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=30', headers=headers).json()
    videos = v_res.get('videos', [])
    valid_videos = [v for v in videos if v.get('duration', 0) >= dur]
    
    if valid_videos:
        selected_video = random.choice(valid_videos)
    elif videos:
        selected_video = max(videos, key=lambda x: x.get('duration', 0))
    else:
        raise Exception("لم يتم العثور على فيديوهات من Pexels!")

    v_url = selected_video['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)
    
    print(f"⚙️ [3/4] المونتاج...")
    bg = loop(mp.VideoFileClip("bg_v.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT), duration=dur)
    bg = bg.subclip(0, dur) 
    
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=dur).set_opacity(0.35) 

    font_s = ImageFont.truetype(FONT_PATH_AR, 110)

    text_clips = []
    for i in range(len(audio_clips)):
        c_start = starts[i]
        c_end = starts[i+1] if i < len(starts)-1 else dur

        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        
        ar_char_count = len(text_parts_ar[i])
        if ar_char_count < 60:
            f_size, w_wrap, y_space = 110, 35, 140
        elif ar_char_count < 140:
            f_size, w_wrap, y_space = 90, 40, 115
        elif ar_char_count < 200:
            f_size, w_wrap, y_space = 75, 45, 95
        else:
            f_size, w_wrap, y_space = 65, 50, 85
            
        font_ar_dynamic = ImageFont.truetype(FONT_PATH_AR, f_size)
        font_en_dynamic = ImageFont.truetype(FONT_PATH_EN, int(f_size * 0.45))
        
        ar_lines = safe_wrap(text_parts_ar[i], width=w_wrap)
        en_lines = safe_wrap(text_parts_en[i], width=w_wrap)
        
        total_h = (len(ar_lines) * y_space) + 50 + (len(en_lines) * (int(f_size * 0.45) + 15))
        y_off = max(400, (HEIGHT - total_h) / 2) 
        
        for line in ar_lines:
            d.text((WIDTH/2, y_off), line, font=font_ar_dynamic, fill="white", anchor="mm", stroke_width=4, stroke_fill="black", direction="rtl", language="ar")
            y_off += y_space
            
        y_off += 50
        for line in en_lines:
            d.text((WIDTH/2, y_off), line, font=font_en_dynamic, fill="#E0E0E0", anchor="mm", stroke_width=2, stroke_fill="black")
            y_off += int(f_size * 0.45) + 15
        
        t_clip = mp.ImageClip(np.array(img)).set_start(c_start).set_end(c_end)
        text_clips.append(t_clip)

    title_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    d_title = ImageDraw.Draw(title_img)
    
    if start_ayah == end_ayah:
        title_text = f"{s_name}\nآية {start_ayah}"
    else:
        title_text = f"{s_name}\nالآيات {start_ayah} - {end_ayah}"
        
    d_title.multiline_text((WIDTH/2, 220), title_text, font=font_s, fill="#FFD700", anchor="mm", align="center", spacing=30, stroke_width=4, stroke_fill="black", direction="rtl", language="ar")
    
    title_clip = mp.ImageClip(np.array(title_img)).set_duration(dur)
    final = mp.CompositeVideoClip([bg, dark, title_clip] + text_clips).set_audio(final_audio)

    print("⏳ [4/4] رندر سريع (1080p)...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast", logger=None, threads=4)

    for f in glob.glob("temp_*.mp3"):
        os.remove(f)
    if os.path.exists("bg_v.mp4"):
        os.remove("bg_v.mp4")

    print("📡 الرفع لليوتيوب...")
    youtube = youtube_authenticate()
    
    ayah_range_str = f"الآيات {start_ayah}-{end_ayah}" if start_ayah != end_ayah else f"آية {start_ayah}"
    reciter_names = {'ar.alafasy': 'مشاري العفاسي', 'ar.husary': 'محمود خليل الحصري', 'ar.minshawi': 'محمد صديق المنشاوي'}
    current_reciter = reciter_names.get(AUDIO_EDITION, "الشيخ")

    title_templates = [
        "تلاوة خاشعة تريح القلب 🤍 {s_name} ({ayah_range_str}) #shorts #quran",
        "الشيخ {current_reciter} | {s_name} ({ayah_range_str}) تلاوة هادئة 🌿 #قرآن",
        "آيات تريح النفس والقلب 🎧 {s_name} ({ayah_range_str}) #shorts",
        "تلاوة من سورة {s_name} بصوت {current_reciter} 🤍 #quran_shorts",
        "اسمع وتأمل.. {s_name} ({ayah_range_str}) تلاوة خاشعة ✨ #قرآن_كريم",
        "عطر مسامعك بالقرآن الكريم 🕊️ {s_name} ({ayah_range_str}) #shorts",
        "روعة التلاوة بصوت {current_reciter} | {s_name} 🤍 #quran"
    ]
    
    desc_templates = [
        "تلاوة تريح القلب من سورة {s_name} بصوت الشيخ {current_reciter}.\n\n#قرآن #تلاوة #quran #راحة_نفسية",
        "استمع إلى آيات من {s_name} بصوت عذب يريح الأعصاب للشيخ {current_reciter}.\n\n#القرآن_الكريم #shorts #تلاوة_خاشعة",
        "مقطع قرآني قصير من {s_name} لتريح قلبك وعقلك. القارئ: {current_reciter}.\n\n#quran #قرآن #تلاوات",
        "لا تنس ذكر الله. تلاوة هادئة من {s_name} بصوت {current_reciter}.\n\n#صدقة_جارية #القرآن #shorts",
        "تلاوة مميزة من {s_name}، {ayah_range_str} بصوت الشيخ {current_reciter}.\n\n#quran_karim #تلاوة #راحة",
        "آيات من كتاب الله (سورة {s_name}) تتلى على مسامعكم بصوت {current_reciter}.\n\n#القرآن #quran #تلاوات_قصيرة",
        "شارك المقطع لتنال الأجر 🤍 تلاوة خاشعة من {s_name} بصوت {current_reciter}.\n\n#قرآن #quran #اجر"
    ]

    v_title = random.choice(title_templates).format(s_name=s_name, ayah_range_str=ayah_range_str, current_reciter=current_reciter)
    v_desc = random.choice(desc_templates).format(s_name=s_name, ayah_range_str=ayah_range_str, current_reciter=current_reciter)
    
    body = {'snippet': {'title': v_title, 'description': v_desc, 'categoryId': '22'}, 'status': {'privacyStatus': 'public'}}
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)).execute()
    print(f"✅ تم بنجاح بجودة 1080p! (المدة: {dur:.1f} ثانية)")

if __name__ == "__main__":
    if not is_uploaded_today() or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        try:
            build_shorts_video()
            mark_uploaded_today()
        except Exception as e:
            print("🔥 خطأ:", e); sys.exit(1)
    
