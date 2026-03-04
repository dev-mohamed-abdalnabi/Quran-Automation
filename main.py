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

# ================== إعدادات الأبعاد (Shorts) ==================

WIDTH = 1080
HEIGHT = 1920

# ================== إعدادات القراء (ملفات كاملة) ==================
# هنا نربط معرف القارئ في API النصوص برابط تحميل السورة كاملة
# لضمان أن الصوت ملف واحد متصل (Gapless)
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

# ================== دوال مساعدة للنصوص ==================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
FONT_PATH_AR = "Amiri-Regular.ttf"
FONT_PATH_EN = "Roboto-Regular.ttf"

reshaper_new = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})

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

# ================== الوظيفة الرئيسية ==================

def build_shorts_video():
    print("🚀 [1/5] اختيار القارئ والسورة...")
    
    reciter = random.choice(RECITERS_DATA)
    print(f"🎙️ القارئ: {reciter['name']}")

    # نختار من السور القصيرة والمتوسطة (آخر المصحف) لضمان جودة الصوت والتلاوة
    # من سورة النبأ (78) إلى الناس (114)
    s_id = random.randint(78, 114)
    
    # 1. جلب بيانات التوقيت والنص (Metadata)
    print(f"📥 جلب بيانات سورة رقم {s_id}...")
    api_url = f"http://api.alquran.cloud/v1/surah/{s_id}/{reciter['api_id']}"
    res_ar = requests.get(api_url).json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    # 2. تحميل ملف السورة كاملاً (ملف واحد MP3)
    # صيغة الرابط في mp3quran تتطلب 3 أرقام (مثال: 001, 010, 114)
    s_id_str = f"{s_id:03}"
    mp3_url = f"{reciter['base_url']}{s_id_str}.mp3"
    
    print(f"⬇️ تحميل ملف الصوت الأصلي الكامل: {mp3_url}")
    audio_filename = "full_surah.mp3"
    with open(audio_filename, 'wb') as f:
        f.write(requests.get(mp3_url).content)
        
    # 3. حساب نقطة التوقف (القفلة)
    # نقوم بجمع مدة الآيات من الـ API لنعرف أين نقطع الملف الأصلي
    # يجب أن يكون المجموع أقل من 59 ثانية
    
    ayahs_to_include = []
    total_time = 0.0
    
    # تحميل الصوت الأصلي لمعالجته
    original_audio = mp.AudioFileClip(audio_filename)
    
    # البسملة (الآية 1 في الفاتحة، أو آية 0 في API لبعض السور)
    # لتبسيط الأمر، سنبدأ الفيديو من بداية ملف الصوت، ونعرض النصوص بناء على الترتيب
    
    current_timestamp = 0.0
    
    for i, ayah in enumerate(res_ar['ayahs']):
        # نحتاج مدة تقديرية للآية. الـ API لا يعطي المدة، لذا سنعتمد على ملف الصوت المنفصل من ال API
        # *فقط* لحساب المدة، لكن لن نستخدمه في الفيديو
        # هذا حل ذكي لضمان التزامن مع الملف الكامل
        temp_ayah_url = ayah['audio']
        temp_file = f"temp_timer_{i}.mp3"
        with open(temp_file, 'wb') as f:
            f.write(requests.get(temp_ayah_url).content)
        
        clip_checker = mp.AudioFileClip(temp_file)
        duration = clip_checker.duration
        clip_checker.close()
        os.remove(temp_file)
        
        if total_time + duration > 59.0:
            break
            
        ayahs_to_include.append({
            "text_ar": ayah['text'],
            "text_en": res_en['ayahs'][i]['text'],
            "start": current_timestamp,
            "end": current_timestamp + duration
        })
        
        current_timestamp += duration
        total_time += duration

    # 4. قص الجزء المطلوب من الملف الكامل
    print(f"✂️ قص {len(ayahs_to_include)} آيات (المدة: {total_time:.2f} ثانية)...")
    final_audio = original_audio.subclip(0, total_time)
    
    # 5. المونتاج
    print("⚙️ [3/5] معالجة الفيديو...")
    
    # خلفية
    headers = {'Authorization': PEXELS_API_KEY}
    try:
        v_res = requests.get('https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15', headers=headers).json()
        v_url = random.choice(v_res['videos'])['video_files'][0]['link']
        with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)
        bg_clip = mp.VideoFileClip("bg_v.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT)
        bg = loop(bg_clip, duration=total_time)
    except:
        # خلفية احتياطية سوداء
        bg = mp.ColorClip(size=(WIDTH, HEIGHT), color=(20, 20, 20), duration=total_time)

    dark_layer = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=total_time).set_opacity(0.5)

    font_ar = ImageFont.truetype(FONT_PATH_AR, 90)
    font_en = ImageFont.truetype(FONT_PATH_EN, 40)
    font_title = ImageFont.truetype(FONT_PATH_AR, 130)

    text_clips = []
    
    for item in ayahs_to_include:
        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # تجهيز النص العربي
        ar_text = process_ar(item['text_ar'])
        ar_lines = safe_wrap(item['text_ar'], width=40) # استخدام النص الأصلي للتقسيم ثم التشكيل
        
        # تجهيز النص الإنجليزي
        en_lines = safe_wrap(item['text_en'], width=45)

        # حساب المواقع
        block_h = len(ar_lines)*120 + 60 + len(en_lines)*50
        y_start = (HEIGHT - block_h) / 2

        current_y = y_start
        for line in ar_lines:
            draw_text_with_shadow(d, (WIDTH/2, current_y), process_ar(line), font_ar, "white")
            current_y += 120
        
        current_y += 40
        for line in en_lines:
            d.text((WIDTH/2, current_y), line, font=font_en, fill="#E0E0E0", anchor="mm", stroke_width=1, stroke_fill="black")
            current_y += 55

        txt_clip = mp.ImageClip(np.array(img)).set_start(item['start']).set_end(item['end'])
        text_clips.append(txt_clip)

    # عنوان السورة
    title_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_text_with_shadow(ImageDraw.Draw(title_img), (WIDTH/2, 250), process_ar(s_name), font_title, "#FFD700")
    title_clip = mp.ImageClip(np.array(title_img)).set_duration(total_time)

    final = mp.CompositeVideoClip([bg, dark_layer, title_clip] + text_clips).set_audio(final_audio)

    print("⏳ [4/5] تصدير الفيديو (Full HD)...")
    final.write_videofile("final_shorts.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast", logger=None, threads=4)
    
    # تنظيف
    original_audio.close()
    if os.path.exists("full_surah.mp3"): os.remove("full_surah.mp3")

    print("📡 [5/5] الرفع لليوتيوب...")
    youtube = youtube_authenticate()
    
    desc = f"""تلاوة مريحة للقلب من سورة {s_name}
    القارئ: {reciter['name']}
    
    اللهم اجعل هذا العمل صدقة جارية.
    #quran #قرآن #shorts #تلاوة #islam
    """
    
    body = {
        'snippet': {
            'title': f'تلاوة تأخذك لعالم آخر - {s_name} 🤍 #shorts',
            'description': desc,
            'categoryId': '22'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload("final_shorts.mp4", chunksize=-1, resumable=True)
    ).execute()
    print("✅ تم الرفع بنجاح!")

if __name__ == "__main__":
    if not is_uploaded_today() or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        try:
            build_shorts_video()
            mark_uploaded_today()
        except Exception as e:
            print("🔥 حدث خطأ:", e)
            sys.exit(1)
    else:
        print("⚠️ تم رفع فيديو اليوم بالفعل.")
