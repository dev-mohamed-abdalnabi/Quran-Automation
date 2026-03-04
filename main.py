import os, requests, random, json, base64, sys, math
from datetime import datetime
import numpy as np
import moviepy.editor as mp
from moviepy.video.fx.all import loop
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw, ImageFilter
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ================== إعدادات الأبعاد والتصميم ==================

WIDTH = 1080
HEIGHT = 1920

# الألوان
TEXT_COLOR = "#FFFFFF"     # أبيض ناصع
SHADOW_COLOR = "#000000"   # ظل أسود
GLOW_COLOR = "#FFFFFF"     # توهج أبيض

# ================== ملفات الخطوط (يجب توفيرها) ==================
# حمل خط ثلث وسمه Thuluth.ttf
# حمل خط نسخ عادي وسمه Amiri-Regular.ttf
FONT_TITLE = "Thuluth.ttf"       # لاسم السورة (خط ثلث)
FONT_TEXT = "Amiri-Regular.ttf"  # للآيات (خط نسخ واضح)
FONT_EN = "Roboto-Regular.ttf"   # للترجمة

# ================== إعدادات القراء ==================
RECITERS_DATA = [
    {"api_id": "ar.alafasy", "name": "مشاري العفاسي", "base_url": "https://server8.mp3quran.net/afs/"},
    {"api_id": "ar.mahermuaiqly", "name": "ماهر المعيقلي", "base_url": "https://server12.mp3quran.net/maher/"},
    {"api_id": "ar.abdurrahmaansudais", "name": "عبدالرحمن السديس", "base_url": "https://server11.mp3quran.net/sds/"},
    {"api_id": "ar.saoodshuraym", "name": "سعود الشريم", "base_url": "https://server7.mp3quran.net/shur/"},
    {"api_id": "ar.minshawi", "name": "محمد صديق المنشاوي", "base_url": "https://server10.mp3quran.net/minsh/"} 
]

# ================== دوال مساعدة ==================

LOG_FILE = "daily_log.txt"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

reshaper = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})

def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def is_uploaded_today():
    if not os.path.exists(LOG_FILE): return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return f.read().strip() == today_str()

def mark_uploaded_today():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(today_str())

def process_ar(t):
    try: return get_display(reshaper.reshape(t))[::-1]
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

# دالة رسم النص مع توهج (Glow) للاحترافية
def draw_text_with_glow(draw, pos, text, font, glow_color="white", text_color="white"):
    x, y = pos
    # رسم الظل/التوهج (طبقات متعددة لعمل Blur وهمي)
    offsets = [(-2,0), (2,0), (0,-2), (0,2), (-2,-2), (2,2)]
    for ox, oy in offsets:
        draw.text((x+ox, y+oy), text, font=font, fill="#000000", anchor="mm") # ظل أسود
    
    # رسم النص الأساسي
    draw.text((x, y), text, font=font, fill=text_color, anchor="mm")

# ================== دالة رسم موجات الصوت (Visualizer) ==================
def make_audio_wave(t):
    # إنشاء صورة شفافة
    w, h = 600, 100
    img = np.zeros((h, w, 4), dtype=np.uint8)
    
    # عدد الأعمدة
    num_bars = 40
    bar_width = 8
    gap = 6
    start_x = (w - (num_bars * (bar_width + gap))) // 2
    
    # محاكاة الحركة باستخدام دالة Sine مع عشوائية
    import math
    for i in range(num_bars):
        # معادلة رياضية لمحاكاة حركة الموجة بناء على الوقت t
        height_factor = (math.sin(t * 5 + i * 0.5) + 1) / 2  # قيمة بين 0 و 1
        # إضافة عشوائية لجعلها تبدو طبيعية
        randomness = np.random.uniform(0.5, 1.0)
        
        bar_height = int(20 + (height_factor * randomness * 60)) # طول العمود
        
        # إحداثيات العمود
        x1 = start_x + i * (bar_width + gap)
        y1 = (h - bar_height) // 2
        x2 = x1 + bar_width
        y2 = y1 + bar_height
        
        # رسم العمود (أبيض) يدوياً في مصفوفة Numpy
        img[y1:y2, x1:x2] = [255, 255, 255, 200] # RGBA (White + Alpha)
        
    return img

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

# ================== الكود الرئيسي ==================

def build_shorts_video():
    print("🚀 [1/6] التجهيز واختيار السورة...")
    
    reciter = random.choice(RECITERS_DATA)
    # اختيار سورة من الجزء الأخير
    s_id = random.randint(78, 114) 
    
    # جلب البيانات
    api_url = f"http://api.alquran.cloud/v1/surah/{s_id}/{reciter['api_id']}"
    res_ar = requests.get(api_url).json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    # تحميل الصوت الكامل
    s_id_str = f"{s_id:03}"
    mp3_url = f"{reciter['base_url']}{s_id_str}.mp3"
    print(f"⬇️ تحميل التلاوة: {s_name} - {reciter['name']}")
    
    full_audio_filename = "full_surah.mp3"
    with open(full_audio_filename, 'wb') as f: f.write(requests.get(mp3_url).content)
    
    full_audio_clip = mp.AudioFileClip(full_audio_filename)
    
    # حساب الاستعاذة والبسملة لقصها
    print("🧮 ضبط التوقيت (Gapless)...")
    total_ayahs_duration = 0.0
    ayah_durations = []
    
    for i, ayah in enumerate(res_ar['ayahs']):
        t_file = f"temp_{i}.mp3"
        with open(t_file, 'wb') as f: f.write(requests.get(ayah['audio']).content)
        clip = mp.AudioFileClip(t_file)
        dur = clip.duration
        clip.close()
        os.remove(t_file)
        ayah_durations.append(dur)
        total_ayahs_duration += dur

    offset_start = max(0, full_audio_clip.duration - total_ayahs_duration)
    
    # تحديد الآيات (لا تتجاوز 59 ثانية)
    final_video_duration = 0.0
    ayahs_to_render = []
    current_cursor = 0.0 
    
    for i, dur in enumerate(ayah_durations):
        if final_video_duration + dur > 59.0: break
        ayahs_to_render.append({
            "text_ar": res_ar['ayahs'][i]['text'],
            "text_en": res_en['ayahs'][i]['text'],
            "start": current_cursor,
            "end": current_cursor + dur
        })
        current_cursor += dur
        final_video_duration += dur

    # قص الصوت النهائي
    final_audio = full_audio_clip.subclip(offset_start, offset_start + final_video_duration)

    # ================== المونتاج والجرافيك ==================
    print("🎨 [3/6] تصميم الفيديو (Visuals)...")
    
    # 1. الخلفية
    headers = {'Authorization': PEXELS_API_KEY}
    try:
        v_res = requests.get('https://api.pexels.com/videos/search?query=nature dark&orientation=portrait&per_page=10', headers=headers).json()
        v_url = random.choice(v_res['videos'])['video_files'][0]['link']
        with open("bg.mp4", "wb") as f: f.write(requests.get(v_url).content)
        bg = loop(mp.VideoFileClip("bg.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT), duration=final_video_duration)
    except:
        bg = mp.ColorClip(size=(WIDTH, HEIGHT), color=(15,15,20), duration=final_video_duration)

    # طبقة تغميق
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=final_video_duration).set_opacity(0.5)

    # إعداد الخطوط
    try:
        font_sura = ImageFont.truetype(FONT_TITLE, 150) # خط الثلث الكبير
    except:
        font_sura = ImageFont.truetype(FONT_TEXT, 150) # احتياطي
        print("⚠️ لم يتم العثور على خط الثلث، تم استخدام الخط العادي.")

    font_reciter = ImageFont.truetype(FONT_TEXT, 60)
    font_ayah = ImageFont.truetype(FONT_TEXT, 85)
    font_en = ImageFont.truetype(FONT_EN, 40)

    # 2. الهيدر (العنوان + القارئ) - ثابت طوال الفيديو
    header_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_h = ImageDraw.Draw(header_img)
    
    # رسم اسم السورة بخط الثلث
    draw_text_with_glow(draw_h, (WIDTH/2, 350), process_ar(s_name), font_sura, glow_color="#FFFFFF")
    # رسم اسم القارئ تحته
    draw_text_with_glow(draw_h, (WIDTH/2, 500), process_ar(reciter['name']), font_reciter, glow_color="#DDDDDD")
    
    header_clip = mp.ImageClip(np.array(header_img)).set_duration(final_video_duration)

    # 3. شريط الصوت (Wave Visualizer)
    # يتم وضعه في أسفل الفيديو فوق الآيات قليلاً أو تحتها
    wave_clip = mp.VideoClip(make_frame=make_audio_wave, duration=final_video_duration)
    wave_clip = wave_clip.set_position(("center", 1300)) # موقعه في الأسفل

    # 4. نصوص الآيات
    text_clips = []
    for item in ayahs_to_render:
        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        ar_lines = safe_wrap(item['text_ar'], width=35)
        en_lines = safe_wrap(item['text_en'], width=40)

        # توسيط النصوص في منتصف الشاشة (تحت العنوان)
        total_h = len(ar_lines)*120 + 50 + len(en_lines)*60
        y = (HEIGHT - total_h) / 2 + 100 # +100 لننزل قليلاً عن العنوان

        for line in ar_lines:
            draw_text_with_glow(d, (WIDTH/2, y), process_ar(line), font_ayah)
            y += 120
        
        y += 30
        for line in en_lines:
            d.text((WIDTH/2, y), line, font=font_en, fill="#DDDDDD", anchor="mm", stroke_width=1, stroke_fill="black")
            y += 60

        clip = mp.ImageClip(np.array(img)).set_start(item['start']).set_end(item['end'])
        text_clips.append(clip)

    # تجميع الطبقات
    final = mp.CompositeVideoClip([bg, dark, header_clip, wave_clip] + text_clips).set_audio(final_audio)

    print("⏳ [5/6] التصدير (Rendering)...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast", logger=None, threads=4)
    
    full_audio_clip.close()
    if os.path.exists("full_surah.mp3"): os.remove("full_surah.mp3")
    if os.path.exists("bg.mp4"): os.remove("bg.mp4")

    # ================== الرفع و SEO ==================
    print("📡 [6/6] الرفع لليوتيوب...")
    youtube = youtube_authenticate()
    
    # عنوان جذاب (Clickbait محترم)
    titles_list = [
        f"سورة {s_name} | {reciter['name']} | تلاوة تهتز لها القلوب 💔",
        f"أرح سمعك وقلبك 🎧 سورة {s_name} بصوت {reciter['name']}",
        f"تلاوة خاشعة من سورة {s_name} 🥺 {reciter['name']}",
        f"Beautiful Quran Recitation | Surah {s_name} | {reciter['name']}"
    ]
    title = random.choice(titles_list)
    
    # وصف محسن للبحث
    description = f"""
    تلاوة خاشعة ومؤثرة من سورة {s_name} بصوت القارئ الشيخ {reciter['name']}.
    أرح قلبك ومسمعك بكلام الله.
    
    ✅ اشترك في القناة وانشر المقطع صدقة جارية لك ولنا.
    
    📍 الكلمات المفتاحية:
    قرآن كريم، تلاوة خاشعة، {s_name}، {reciter['name']}، حالات واتس قران، مقاطع دينية قصيرة، راحة نفسية، Quran Recitation، Islam، Muslim.
    
    #quran #قرآن #shorts #تلاوة #islam #راحة_نفسية #السعودية #مصر #اكسبلور
    """

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'categoryId': '22',
            'tags': ['قرآن', 'quran', 'islam', 'تلاوة', 'shorts', s_name, reciter['name']]
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)).execute()
    print(f"✅ تم الرفع: {title}")

if __name__ == "__main__":
    if not is_uploaded_today() or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        try:
            build_shorts_video()
            mark_uploaded_today()
        except Exception as e:
            print("🔥 خطأ:", e)
            sys.exit(1)
