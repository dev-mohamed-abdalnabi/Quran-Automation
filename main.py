
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

# ================== إعدادات الأبعاد (Shorts 1080p) ==================

WIDTH = 1080
HEIGHT = 1920

# ================== إعدادات القراء ==================
# نربط الـ API بمصدر الصوت لضمان تطابق النسخ
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

# ================== أدوات مساعدة ==================

LOG_FILE = "daily_log.txt"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
FONT_PATH_AR = "Thuluth.ttf" # تم تغيير الخط إلى الثلث
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

def safe_wrap(text, font, max_width):
    lines = []
    if not text: return lines
    words = text.split()
    current_line = []
    current_line_width = 0

    for word in words:
        word_width, _ = font.getsize(word + " ")
        if current_line_width + word_width <= max_width:
            current_line.append(word)
            current_line_width += word_width
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_line_width = font.getsize(word + " ")[0]
    if current_line:
        lines.append(" ".join(current_line))
    return lines

def draw_text_with_shadow(draw, pos, text, font, fill_color, shadow_color="black", shadow_offset=(4, 4)):
    x, y = pos
    # رسم الظل
    draw.text((x + shadow_offset[0], y + shadow_offset[1]), text, font=font, fill=shadow_color, anchor="mm")
    # رسم النص الأصلي
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

    # نختار سورة من الجزء الأخير (النبأ 78 -> الناس 114)
    # (باستثناء الفاتحة لأن الفاتحة البسملة فيها آية رقم 1 فلا تحتاج قص)
    s_id = random.randint(78, 114) 
    
    # 1. جلب البيانات (النصوص + روابط الآيات الفردية للقياس فقط)
    print(f"📥 جلب بيانات سورة {s_id}...")
    api_url = f"http://api.alquran.cloud/v1/surah/{s_id}/{reciter['api_id']}"
    res_ar = requests.get(api_url).json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    # 2. تحميل ملف السورة الكامل (MP3 Source)
    s_id_str = f"{s_id:03}"
    mp3_url = f"{reciter['base_url']}{s_id_str}.mp3"
    print(f"⬇️ تحميل الملف الكامل: {mp3_url}")
    
    full_audio_filename = "full_surah.mp3"
    with open(full_audio_filename, 'wb') as f:
        f.write(requests.get(mp3_url).content)
    
    # تحميل الملف الكامل في MoviePy لقياس مدته
    full_audio_clip = mp.AudioFileClip(full_audio_filename)
    full_duration = full_audio_clip.duration
    print(f"⏱️ مدة الملف الكامل (مع المقدمة): {full_duration:.2f} ثانية")

    # 3. حساب مدة المقدمة (الاستعاذة + البسملة) بطريقة حسابية دقيقة
    # المنطق: مدة الملف الكامل - مجموع مدد الآيات = مدة المقدمة
    print("🧮 جاري حساب مدة المقدمة (الاستعاذة/البسملة) لقصها...")
    
    total_ayahs_duration = 0.0
    ayah_durations = [] # لحفظ مدة كل آية لاستخدامها في التزامن

    for i, ayah in enumerate(res_ar['ayahs']):
        # نحمل الآية الفردية فقط لقياس مدتها ثم نحذفها
        t_url = ayah['audio']
        t_file = f"temp_measure_{i}.mp3"
        with open(t_file, 'wb') as f:
            f.write(requests.get(t_url).content)
        
        # قياس دقيق
        temp_clip = mp.AudioFileClip(t_file)
        dur = temp_clip.duration
        temp_clip.close() # إغلاق الملف
        os.remove(t_file) # حذف الملف
        
        ayah_durations.append(dur)
        total_ayahs_duration += dur

    # حساب الـ Offset (بداية الكلام الفعلي)
    # ملاحظة: نضيف هامش خطأ بسيط جدا (0.1) لضمان عدم قص أول حرف
    offset_start = max(0, full_audio_clip.duration - total_ayahs_duration)
    
    print(f"✂️ مدة المقدمة المحسوبة: {offset_start:.2f} ثانية (سيتم قصها)")

    # 4. تحديد الآيات التي ستدخل في الفيديو (بحد أقصى 59 ثانية)
    print("🎬 تحديد الآيات للفيديو...")
    
    final_video_duration = 0.0
    ayahs_to_render = []
    
    # نبدأ التوقيت من 0 لأننا سنقص الملف الصوتي ليبدأ من الآية 1
    current_cursor = 0.0 
    
    for i, dur in enumerate(ayah_durations):
        # التحقق من أننا لا نتجاوز 59 ثانية
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

    # 5. معالجة الصوت: قص المقدمة + قص النهاية عند آخر آية مختارة
    # البداية: offset_start
    # النهاية: offset_start + final_video_duration
    
    final_audio = full_audio_clip.subclip(offset_start, offset_start + final_video_duration)
    
    print(f"🔉 الصوت النهائي جاهز: من {offset_start:.2f} إلى {offset_start + final_video_duration:.2f}")

    # 6. إنشاء الفيديو
    print("⚙️ [5/6] تركيب الفيديو...")
    
    # خلفية
    headers = {'Authorization': PEXELS_API_KEY}
    try:
        v_res = requests.get('https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15', headers=headers).json()
        v_url = random.choice(v_res['videos'])['video_files'][0]['link']
        with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)
        bg = loop(mp.VideoFileClip("bg_v.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT), duration=final_video_duration)
    except:
        bg = mp.ColorClip(size=(WIDTH, HEIGHT), color=(10,10,10), duration=final_video_duration)

    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=final_video_duration).set_opacity(0.4)

    # تعريف الخطوط
    try:
        font_ar_ayah = ImageFont.truetype(FONT_PATH_AR, 90)
        font_ar_title = ImageFont.truetype(FONT_PATH_AR, 120)
    except IOError:
        print(f"⚠️ لم يتم العثور على خط الثلث: {FONT_PATH_AR}. سيتم استخدام خط افتراضي.")
        font_ar_ayah = ImageFont.load_default()
        font_ar_title = ImageFont.load_default()

    font_en = ImageFont.truetype(FONT_PATH_EN, 40)

    # إنشاء مقاطع النصوص
    text_clips = []
    for item in ayahs_to_render:
        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # استخدام safe_wrap الجديد الذي يعتمد على حجم الخط
        ar_lines = safe_wrap(item['text_ar'], font_ar_ayah, WIDTH - 100) # عرض أقل لترك هوامش
        en_lines = safe_wrap(item['text_en'], font_en, WIDTH - 100)

        # توسيط النصوص بشكل أفضل
        # تحديد نقطة البداية للنص العربي (أعلى قليلاً)
        y_ar_start = HEIGHT * 0.35 - (len(ar_lines) * font_ar_ayah.getsize("Test")[1]) / 2
        y_en_start = HEIGHT * 0.55 - (len(en_lines) * font_en.getsize("Test")[1]) / 2

        current_y = y_ar_start
        for line in ar_lines:
            draw_text_with_shadow(d, (WIDTH/2, current_y), process_ar(line), font_ar_ayah, "white")
            current_y += font_ar_ayah.getsize("Test")[1] + 20 # مسافة بين الأسطر
        
        current_y = y_en_start
        for line in en_lines:
            draw_text_with_shadow(d, (WIDTH/2, current_y), line, font_en, "#DDDDDD", shadow_offset=(2,2))
            current_y += font_en.getsize("Test")[1] + 10 # مسافة بين الأسطر

        clip = mp.ImageClip(np.array(img)).set_start(item['start']).set_end(item['end'])
        text_clips.append(clip)

    # عنوان السورة (في الأعلى)
    t_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_text_with_shadow(ImageDraw.Draw(t_img), (WIDTH/2, HEIGHT * 0.15), process_ar(s_name), font_ar_title, "#FFD700")
    title_clip = mp.ImageClip(np.array(t_img)).set_duration(final_video_duration)

    # ================== إضافة شريط ذبذبات الصوت (Waveform) ==================
    # سنقوم بإنشاء شريط ذبذبات ثابت ثم نتحكم في ظهوره أو إخفائه أو تحريكه
    # لتبسيط العملية، سنقوم بإنشاء صورة لشريط ذبذبات ونحركها أفقياً
    
    waveform_height = 100
    waveform_width = WIDTH
    waveform_color = (255, 255, 255, 180) # أبيض شبه شفاف
    waveform_bg_color = (0, 0, 0, 0) # شفاف تماما

    # إنشاء صورة شريط ذبذبات بسيط (يمكن تحسينه لاحقاً ليعكس الصوت الفعلي)
    waveform_img = Image.new('RGBA', (waveform_width * 2, waveform_height), waveform_bg_color)
    draw_wf = ImageDraw.Draw(waveform_img)
    
    # رسم خطوط عشوائية لمحاكاة الذبذبات
    for i in range(0, waveform_width * 2, 10):
        line_height = random.randint(waveform_height // 4, waveform_height)
        draw_wf.line([(i, (waveform_height - line_height) // 2), (i, (waveform_height + line_height) // 2)], fill=waveform_color, width=5)

    # تحويل الصورة إلى مقطع فيديو
    waveform_clip = mp.ImageClip(np.array(waveform_img)).set_duration(final_video_duration)
    
    # تحريك شريط الذبذبات أفقياً
    def scroll_waveform(t):
        x_pos = - (t / final_video_duration) * waveform_width # يتحرك من اليمين لليسار
        return (x_pos, HEIGHT - waveform_height - 50) # يوضع في الأسفل

    waveform_clip = waveform_clip.set_pos(scroll_waveform)
    # ========================================================================

    # التصدير
    final = mp.CompositeVideoClip([bg, dark, title_clip, waveform_clip] + text_clips).set_audio(final_audio)

    print("⏳ [6/6] جاري الرندر (Full HD)...")
    final.write_videofile("final_shorts.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast", logger=None, threads=4)
    
    # تنظيف
    full_audio_clip.close()
    if os.path.exists("full_surah.mp3"): os.remove("full_surah.mp3")
    if os.path.exists("bg_v.mp4"): os.remove("bg_v.mp4")

    # الرفع
    print("📡 جاري الرفع...")
    youtube = youtube_authenticate()
    desc = f"تلاوة من سورة {s_name} بصوت {reciter['name']}\n\n#quran #قرآن #shorts #islam"
    
    body = {
        'snippet': {'title': f'تلاوة خاشعة - {s_name} ❤️ #shorts', 'description': desc, 'categoryId': '22'},
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
