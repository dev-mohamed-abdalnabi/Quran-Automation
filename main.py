import os, requests, random, json, base64, sys, math
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

# ================== إعدادات الأبعاد (Shorts 1080p) ==================

WIDTH = 1080
HEIGHT = 1920

# ================== إعدادات القراء ==================
RECITERS_DATA = [
    {
        "api_id": "ar.alafasy", 
        "name": "مشاري العفاسي", 
        "base_url": "https://server8.mp3quran.net/afs/" 
    },
    {
        "api_id": "ar.mahermuaiqly", 
        "name": "ماهر المعيقلي", 
        "base_url": "https://server12.mp3quran.net/maher/" 
    },
    {
        "api_id": "ar.abdurrahmaansudais", 
        "name": "عبدالرحمن السديس", 
        "base_url": "https://server11.mp3quran.net/sds/" 
    },
    {
        "api_id": "ar.saoodshuraym", 
        "name": "سعود الشريم", 
        "base_url": "https://server7.mp3quran.net/shur/" 
    }
]

# ================== عناوين ووصف يوتيوب متغير (إبداعي) ==================
YOUTUBE_TITLES = [
    "تلاوة خاشعة تأسر القلوب من {surah} 🤍 بصوت {reciter} #shorts",
    "عش مع القرآن دقائق - {surah} 🎧 القارئ {reciter} #shorts",
    "تلاوة هادئة تريح الأعصاب | {surah} | {reciter} #shorts",
    "حالات واتس قرآن كريم 🌸 {surah} - {reciter} #shorts",
    "روائع التلاوات 🌙 {surah} بصوت الشيخ {reciter} #shorts"
]

YOUTUBE_DESCRIPTIONS = [
    "استمع بقلبك إلى هذه التلاوة الخاشعة من {surah} بصوت الشيخ {reciter}. 🤍\n\nلا تنسَ الاشتراك في القناة والمشاركة لنشر الخير والدال على الخير كفاعله.\n\n#قرآن #تلاوة_خاشعة #shorts #quran #islam",
    "تلاوة تريح القلب وتهدئ النفس من {surah} للقارئ {reciter}. ✨\nشارك المقطع واكسب الأجر.\n\n#quran #islam #قران_كريم #shorts",
    "آيات بينات من {surah} بصوت عذب وجميل للشيخ {reciter}. اسمع بقلبك واطمئن. 🌸\n\n#تلاوات #قرآن #حالات_قران #shorts",
    "لحظات من الطمأنينة مع تلاوة هادئة من {surah} بصوت الشيخ {reciter}. شاركها مع من تحب. 🤲\n\n#تلاوة #اسلاميات #قرآن #shorts"
]

# ================== أدوات مساعدة ==================

LOG_FILE = "daily_log.txt"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
FONT_PATH_AR = "Thuluth.ttf" # تم التعديل بناءً على طلبك
FONT_PATH_EN = "Roboto-Regular.ttf"

reshaper_new = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})

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
    offsets = [(3,3), (-3,3), (3,-3), (-3,-3), (0,4), (0,-4), (4,0), (-4,0)]
    for ox, oy in offsets:
        draw.text((x+ox, y+oy), text, font=font, fill="black", anchor="mm")
    draw.text((x, y), text, font=font, fill=fill_color, anchor="mm")

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

# ================== المحرك الرئيسي ==================

def build_shorts_video():
    print("🚀 [1/6] بدء التجهيز...")
    
    reciter = random.choice(RECITERS_DATA)
    print(f"🎙️ القارئ: {reciter['name']}")

    s_id = random.randint(78, 114) 
    
    print(f"📥 جلب بيانات سورة {s_id}...")
    api_url = f"http://api.alquran.cloud/v1/surah/{s_id}/{reciter['api_id']}"
    res_ar = requests.get(api_url).json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    s_id_str = f"{s_id:03}"
    mp3_url = f"{reciter['base_url']}{s_id_str}.mp3"
    print(f"⬇️ تحميل الملف الكامل: {mp3_url}")
    
    full_audio_filename = "full_surah.mp3"
    with open(full_audio_filename, 'wb') as f:
        f.write(requests.get(mp3_url).content)
    
    full_audio_clip = mp.AudioFileClip(full_audio_filename)
    full_duration = full_audio_clip.duration
    print(f"⏱️ مدة الملف الكامل (مع المقدمة): {full_duration:.2f} ثانية")

    print("🧮 جاري حساب مدة المقدمة (الاستعاذة/البسملة) لقصها...")
    
    total_ayahs_duration = 0.0
    ayah_durations = [] 

    for i, ayah in enumerate(res_ar['ayahs']):
        t_url = ayah['audio']
        t_file = f"temp_measure_{i}.mp3"
        with open(t_file, 'wb') as f:
            f.write(requests.get(t_url).content)
        
        temp_clip = mp.AudioFileClip(t_file)
        dur = temp_clip.duration
        temp_clip.close() 
        os.remove(t_file) 
        
        ayah_durations.append(dur)
        total_ayahs_duration += dur

    offset_start = max(0, full_audio_clip.duration - total_ayahs_duration)
    
    print(f"✂️ مدة المقدمة المحسوبة: {offset_start:.2f} ثانية (سيتم قصها)")

    print("🎬 تحديد الآيات للفيديو...")
    
    final_video_duration = 0.0
    ayahs_to_render = []
    current_cursor = 0.0 
    
    for i, dur in enumerate(ayah_durations):
        if final_video_duration + dur > 59.0:
            break
            
        ayahs_to_render.append({
            "text_ar": res_ar['ayahs'][i]['text'],
            "text_en": res_en['ayahs'][i]['text'],
            "start": current_cursor,
            "end": current_cursor + dur
        })
        
        current_cursor += dur
        final_video_duration += dur

    final_audio = full_audio_clip.subclip(offset_start, offset_start + final_video_duration)
    
    print(f"🔉 الصوت النهائي جاهز: من {offset_start:.2f} إلى {offset_start + final_video_duration:.2f}")

    print("⚙️ [5/6] تركيب الفيديو...")
    
    headers = {'Authorization': PEXELS_API_KEY}
    try:
        v_res = requests.get('https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15', headers=headers).json()
        v_url = random.choice(v_res['videos'])['video_files'][0]['link']
        with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)
        bg = loop(mp.VideoFileClip("bg_v.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT), duration=final_video_duration)
    except:
        bg = mp.ColorClip(size=(WIDTH, HEIGHT), color=(10,10,10), duration=final_video_duration)

    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=final_video_duration).set_opacity(0.4)

    font_ar = ImageFont.truetype(FONT_PATH_AR, 90)
    font_en = ImageFont.truetype(FONT_PATH_EN, 40)
    
    # 1. إنشاء مقاطع النصوص (الآيات)
    text_clips = []
    for item in ayahs_to_render:
        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        ar_lines = safe_wrap(item['text_ar'], width=38)
        en_lines = safe_wrap(item['text_en'], width=40)

        total_h = len(ar_lines)*130 + 50 + len(en_lines)*60
        y = (HEIGHT - total_h) / 2

        for line in ar_lines:
            draw_text_with_shadow(d, (WIDTH/2, y), process_ar(line), font_ar, "white")
            y += 130
        
        y += 40
        for line in en_lines:
            d.text((WIDTH/2, y), line, font=font_en, fill="#DDDDDD", anchor="mm", stroke_width=2, stroke_fill="black")
            y += 60

        clip = mp.ImageClip(np.array(img)).set_start(item['start']).set_end(item['end'])
        text_clips.append(clip)

    # 2. إعداد عنوان السورة واسم القارئ (بنفس استايل الصور)
    t_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    d_title = ImageDraw.Draw(t_img)
    font_surah_title = ImageFont.truetype(FONT_PATH_AR, 160)
    font_reciter_title = ImageFont.truetype(FONT_PATH_AR, 80)
    
    surah_text = process_ar(s_name)
    reciter_text = process_ar(reciter['name'])
    
    # رسم اسم السورة وتحته اسم القارئ في الجزء العلوي
    draw_text_with_shadow(d_title, (WIDTH/2, 280), surah_text, font_surah_title, "white")
    draw_text_with_shadow(d_title, (WIDTH/2, 430), reciter_text, font_reciter_title, "white")
    
    title_clip = mp.ImageClip(np.array(t_img)).set_duration(final_video_duration)

    # 3. إعداد الشريط الصوتي المتحرك (Audio Waveform Visualizer)
    def make_waveform_frame(t):
        img_wave = Image.new('RGBA', (WIDTH, 150), (0, 0, 0, 0))
        draw_wave = ImageDraw.Draw(img_wave)
        center_x = WIDTH // 2
        center_y = 75
        num_bars = 45 # عدد الأعمدة أو النقاط
        bar_width = 4
        spacing = 12
        
        for i in range(num_bars):
            offset = i - (num_bars // 2)
            # عمل تأثير القوس (الهرمي) بحيث الموجات في النص أعلى من الأطراف
            envelope = math.exp(-0.015 * (offset ** 2))
            # حركة الموجة بناء على الوقت (t) لتكون سلسة وجميلة
            val = math.sin(t * 12 + i * 1.5) * math.sin(t * 6 - i)
            h = int(60 * envelope * abs(val)) + 6 # أقل ارتفاع للعمود
            
            x = center_x + offset * spacing
            draw_wave.rounded_rectangle([(x, center_y - h/2), (x + bar_width, center_y + h/2)], radius=2, fill="white")
            
        return np.array(img_wave)

    wave_clip = mp.VideoClip(make_waveform_frame, duration=final_video_duration)
    # نضع الشريط الصوتي في الأسفل
    wave_clip = wave_clip.set_position(('center', HEIGHT - 450))

    # التصدير بدمج كل الطبقات
    final = mp.CompositeVideoClip([bg, dark, title_clip, wave_clip] + text_clips).set_audio(final_audio)

    print("⏳ [6/6] جاري الرندر (Full HD)...")
    final.write_videofile("final_shorts.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast", logger=None, threads=4)
    
    # تنظيف
    full_audio_clip.close()
    if os.path.exists("full_surah.mp3"): os.remove("full_surah.mp3")

    # الرفع لليوتيوب بالعناوين الجديدة
    print("📡 جاري الرفع...")
    youtube = youtube_authenticate()
    
    # اختيار عنوان ووصف بشكل عشوائي
    final_title = random.choice(YOUTUBE_TITLES).format(surah=s_name, reciter=reciter['name'])
    final_desc = random.choice(YOUTUBE_DESCRIPTIONS).format(surah=s_name, reciter=reciter['name'])
    
    body = {
        'snippet': {'title': final_title, 'description': final_desc, 'categoryId': '22'},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }
    
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final_shorts.mp4", chunksize=-1, resumable=True)).execute()
    print("✅ تم!")

if __name__ == "__main__":
    if not is_uploaded_today() or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        try:
            build_shorts_video()
            mark_uploaded_today()
        except Exception as e:
            print("🔥 خطأ:", e)
            sys.exit(1)
