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

# ================== إعدادات الأبعاد (Full HD 1080p) ==================
WIDTH = 1080
HEIGHT = 1920

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

# ================== الإعدادات: القراء والخلفيات ==================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

# قائمة القراء (لتنويع الأصوات)
RECITERS = [
    'ar.alafasy',           # العفاسي
    'ar.abdulbasitmurattal',# عبدالباسط (مرتل)
    'ar.hudhaify',          # الحذيفي
    'ar.husary',            # الحصري
    'ar.mahermuaiqly',      # المعيقلي
    'ar.sudais',            # السديس
    'ar.shuraim',           # الشريم
    'ar.ahmedajamy'         # العجمي
]

# كلمات بحث آمنة لضمان عدم ظهور بشر أو حيوانات
# نركز على الطبيعة الجامدة، السماء، والزخارف
SAFE_BACKGROUNDS = [
    "sky clouds timelapse", "blue sky", "dark night stars", "galaxy",
    "ocean waves aerial", "sea water texture", "calm water",
    "forest trees drone", "green leaves texture", "pine forest",
    "mosque architecture", "islamic art pattern", "mecca kaaba"
]

FONT_PATH_AR = "Amiri-Regular.ttf" 
FONT_PATH_EN = "Roboto-Regular.ttf"

reshaper_new = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})

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
    offsets = [(3,3), (-3,3), (3,-3), (-3,-3), (0,4), (0,-4), (4,0), (-4,0)]
    for ox, oy in offsets:
        draw.text((x+ox, y+oy), text, font=font, fill=shadow_color, anchor="mm")
    draw.text((x, y), text, font=font, fill=fill_color, anchor="mm")

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

# دالة لإنشاء مقطع صمت
def make_silence(duration):
    return mp.AudioClip(make_frame=lambda t: [0, 0], duration=duration)

def build_shorts_video():
    print("🚀 [1/4] تحضير الموارد...")
    
    # اختيار قارئ عشوائي
    selected_audio_edition = random.choice(RECITERS)
    print(f"🎙️ القارئ المختار: {selected_audio_edition}")

    s_id = random.randint(1, 114)
    # جلب البيانات
    try:
        res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{selected_audio_edition}").json()['data']
        res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    except Exception as e:
        print(f"Error fetching Quran data: {e}")
        return

    s_name = res_ar['name']
    
    audio_clips = []
    text_data = [] # لتخزين النصوص وتوقيتاتها
    
    current_time_cursor = 0.0
    gap_duration = 0.5 # نصف ثانية صمت بين الآيات لمنع التداخل والقطع
    
    # تحديد عدد الآيات بناءً على المدة الزمنية
    for i, (a_ar, a_en) in enumerate(zip(res_ar['ayahs'], res_en['ayahs'])):
        f_path = f"temp_{i}.mp3"
        
        # تحميل ملف الصوت
        with open(f_path, 'wb') as f:
            f.write(requests.get(a_ar['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        
        # إضافة الصوت للقائمة
        audio_clips.append(clip)
        
        # تسجيل بيانات النص (وقت البداية ووقت النهاية)
        start_t = current_time_cursor
        end_t = current_time_cursor + clip.duration
        
        text_data.append({
            'ar': a_ar['text'],
            'en': a_en['text'],
            'start': start_t,
            'end': end_t
        })
        
        # تحديث المؤشر الزمني + إضافة الصمت
        current_time_cursor = end_t + gap_duration
        
        # إضافة مقطع صمت بين الآيات (إلا في الآية الأخيرة لتوفير الوقت)
        audio_clips.append(make_silence(gap_duration))
        
        # التوقف إذا تجاوزنا 58 ثانية (لضمان شروط الشورتس)
        if current_time_cursor >= 58: 
            break

    # --- دمج الصوت ---
    final_audio = mp.concatenate_audioclips(audio_clips)
    
    # قص الصوت ليكون أقل من 60 ثانية بالضبط
    max_duration = 59.5
    if final_audio.duration > max_duration:
        final_audio = final_audio.subclip(0, max_duration)
        # تطبيق Fade out في النهاية لتجنب القطع المفاجئ
        final_audio = audio_fadeout(final_audio, 2.0)
    
    actual_duration = final_audio.duration

    # --- اختيار خلفية آمنة (بدون بشر) ---
    bg_query = random.choice(SAFE_BACKGROUNDS)
    print(f"🖼️ الخلفية المختارة: {bg_query}")
    
    headers = {'Authorization': PEXELS_API_KEY}
    try:
        # نبحث عن Video Orientation Portrait
        v_res = requests.get(f'https://api.pexels.com/videos/search?query={bg_query}&orientation=portrait&size=medium&per_page=5', headers=headers).json()
        if not v_res.get('videos'):
             # fallback search if specific query fails
             v_res = requests.get('https://api.pexels.com/videos/search?query=nature sky&orientation=portrait&per_page=5', headers=headers).json()
             
        v_url = v_res['videos'][0]['video_files'][0]['link']
        with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)
    except Exception as e:
        print("Error fetching background:", e)
        # إنشاء خلفية سوداء في حالة الفشل
        mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=actual_duration).write_videofile("bg_v.mp4", fps=24)

    print(f"⚙️ [2/4] المونتاج...")
    
    # تحضير الفيديو الخلفي
    bg_clip = mp.VideoFileClip("bg_v.mp4")
    # التأكد من ملء الشاشة
    bg_clip = bg_clip.resize(height=HEIGHT)
    if bg_clip.w < WIDTH:
        bg_clip = bg_clip.resize(width=WIDTH)
    bg_clip = bg_clip.crop(x1=bg_clip.w/2 - WIDTH/2, y1=0, width=WIDTH, height=HEIGHT)
    
    bg = loop(bg_clip, duration=actual_duration)
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=actual_duration).set_opacity(0.4)

    font_ar = ImageFont.truetype(FONT_PATH_AR, 95) 
    font_en = ImageFont.truetype(FONT_PATH_EN, 45)
    font_s = ImageFont.truetype(FONT_PATH_AR, 140)

    # إنشاء كليبات النصوص
    text_clips_list = []
    
    for item in text_data:
        # التأكد أن النص لا يظهر بعد انتهاء الفيديو المقصوص
        if item['start'] >= actual_duration: continue
        
        real_end = min(item['end'], actual_duration)
        
        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        
        ar_lines = safe_wrap(item['ar'], width=40)
        en_lines = safe_wrap(item['en'], width=35)
        
        # حساب التمركز العمودي
        total_h = (len(ar_lines)*130) + 50 + (len(en_lines)*60)
        y_off = (HEIGHT - total_h) / 2
        
        # رسم العربي
        for line in ar_lines:
            draw_text_with_shadow(d, (WIDTH/2, y_off), process_ar_new(line), font_ar, "white")
            y_off += 130
        
        y_off += 50
        
        # رسم الإنجليزي
        for line in en_lines:
            d.text((WIDTH/2, y_off), line, font=font_en, fill="#F0F0F0", anchor="mm", stroke_width=2, stroke_fill="black")
            y_off += 60
        
        txt_clip = mp.ImageClip(np.array(img)).set_start(item['start']).set_end(real_end)
        text_clips_list.append(txt_clip)

    # عنوان السورة (يظهر طوال الفيديو)
    title_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_text_with_shadow(ImageDraw.Draw(title_img), (WIDTH/2, 250), process_ar_new(s_name), font_s, "white")
    title_clip = mp.ImageClip(np.array(title_img)).set_duration(actual_duration)

    # تجميع الفيديو النهائي
    final = mp.CompositeVideoClip([bg, dark, title_clip] + text_clips_list).set_audio(final_audio)

    print("⏳ [3/4] رندر سريع (1080p)...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast", logger=None, threads=4)

    print("📡 [4/4] الرفع...")
    youtube = youtube_authenticate()
    
    # اختيار اسم القارئ للعنوان (اختياري، هنا نستخدم وصف عام)
    video_title = f'تلاوة خاشعة - {s_name} #shorts #quran'
    
    body = {
        'snippet': {
            'title': video_title, 
            'description': f'سورة {s_name}\nRecitation from Holy Quran', 
            'categoryId': '22',
            'tags': ['Quran', 'Islam', 'Shorts', 'تلاوة', 'قرآن']
        }, 
        'status': {'privacyStatus': 'public'}
    }
    
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)).execute()
    print(f"✅ تم بنجاح! القارئ: {selected_audio_edition} | الخلفية: {bg_query}")

if __name__ == "__main__":
    if not is_uploaded_today() or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        try:
            build_shorts_video()
            mark_uploaded_today()
        except Exception as e:
            print("🔥 خطأ:", e); sys.exit(1)
