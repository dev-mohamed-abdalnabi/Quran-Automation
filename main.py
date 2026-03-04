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
from scipy.io import wavfile
import subprocess

# ================== إعدادات الأبعاد (Shorts 1080p) ==================
WIDTH = 1080
HEIGHT = 1920

# ================== إعدادات القراء ==================
# كل قارئ له API خاص بيرجع الآيات بدون بسملة/استعاذة
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

LOG_FILE = "daily_log.txt"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
FONT_PATH_AR = "Thuluth.ttf"       # خط الثلث للعنوان
FONT_PATH_BODY = "Amiri-Regular.ttf"  # خط الجسم للآيات
FONT_PATH_EN = "Roboto-Regular.ttf"

# ================== إعداد المشكّل العربي ==================
# نقلل التشكيل: نبقي فقط الفتحة والكسرة والضمة والسكون والشدة
HARAKAT_TO_KEEP = set('\u064E\u064F\u0650\u0652\u0651')  # فتحة ضمة كسرة سكون شدة
ALL_HARAKAT = set('\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u0653\u0654\u0655\u0670')

reshaper_cfg = arabic_reshaper.ArabicReshaper(configuration={
    'delete_harakat': False,
    'support_ligatures': True
})

def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def is_uploaded_today():
    if not os.path.exists(LOG_FILE): return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return f.read().strip() == today_str()

def mark_uploaded_today():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(today_str())

def reduce_harakat(text):
    """يبقي فقط الفتحة والكسرة والضمة والسكون والشدة ويحذف الباقي"""
    result = []
    for ch in text:
        if ch in ALL_HARAKAT:
            if ch in HARAKAT_TO_KEEP:
                result.append(ch)
            # غير ذلك نحذفها
        else:
            result.append(ch)
    return "".join(result)

def process_ar(t):
    """معالجة النص العربي للعرض الصحيح"""
    try:
        t = reduce_harakat(t)
        reshaped = reshaper_cfg.reshape(t)
        return get_display(reshaped)
    except:
        return t

def safe_wrap(text, max_chars=36):
    """تقسيم النص لأسطر بحد أقصى"""
    words = text.split()
    lines, current_line, current_len = [], [], 0
    for word in words:
        if current_len + len(word) <= max_chars:
            current_line.append(word)
            current_len += len(word) + 1
        else:
            if current_line: lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word) + 1
    if current_line: lines.append(" ".join(current_line))
    return lines

def draw_text_with_shadow(draw, pos, text, font, fill_color, shadow_color=(0,0,0,200)):
    """رسم النص مع ظل"""
    x, y = pos
    for ox, oy in [(3,3),(-3,3),(3,-3),(-3,-3),(0,4),(0,-4),(4,0),(-4,0)]:
        draw.text((x+ox, y+oy), text, font=font, fill=shadow_color, anchor="mm")
    draw.text((x, y), text, font=font, fill=fill_color, anchor="mm")

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

# ================== تحليل الصوت لاستخراج Amplitudes ==================

def extract_waveform_data(audio_path, num_bars=60, fps=24, duration=None):
    """
    يحلل ملف MP3 ويستخرج amplitude لكل frame
    يرجع: dict بـ timestamps -> amplitude values
    """
    # تحويل MP3 إلى WAV للتحليل
    wav_path = audio_path.replace(".mp3", "_analysis.wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", audio_path,
        "-ar", "22050", "-ac", "1", wav_path
    ], capture_output=True)
    
    sample_rate, data = wavfile.read(wav_path)
    if data.dtype != np.float32:
        data = data.astype(np.float32) / np.iinfo(data.dtype).max
    
    os.remove(wav_path)
    
    total_frames = int(duration * fps) if duration else len(data) // (sample_rate // fps)
    
    # لكل frame، نحسب RMS amplitude
    frame_amplitudes = []
    samples_per_frame = sample_rate // fps
    
    for i in range(total_frames):
        start_s = i * samples_per_frame
        end_s = min(start_s + samples_per_frame, len(data))
        if start_s >= len(data):
            frame_amplitudes.append(0.0)
            continue
        chunk = data[start_s:end_s]
        rms = np.sqrt(np.mean(chunk**2))
        frame_amplitudes.append(float(rms))
    
    # Normalize
    max_amp = max(frame_amplitudes) if max(frame_amplitudes) > 0 else 1
    frame_amplitudes = [a / max_amp for a in frame_amplitudes]
    
    return frame_amplitudes

# ================== رسم شريط الصوت المتحرك ==================

def make_waveform_frame(t, frame_amplitudes, fps=24, width=WIDTH, height=HEIGHT):
    """
    يرسم frame لشريط الصوت المتحرك بناءً على amplitude الفعلي
    النتيجة: numpy array RGBA
    """
    frame_idx = min(int(t * fps), len(frame_amplitudes) - 1)
    current_amp = frame_amplitudes[frame_idx]
    
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # إعدادات الشريط
    num_bars = 35
    bar_area_w = 700  # عرض منطقة الشريط
    bar_spacing = bar_area_w // num_bars
    bar_w = max(8, bar_spacing - 6)
    start_x = (width - bar_area_w) // 2
    center_y = height - 280  # موقع الشريط في الأسفل
    max_bar_h = 120
    min_bar_h = 8
    
    # نأخذ window من الـ amplitudes حول الـ frame الحالي للتموج
    window_size = num_bars
    half_w = window_size // 2
    
    for i in range(num_bars):
        # نأخذ amplitude من frames قريبة لإنشاء شكل موجي
        f_idx = frame_idx - half_w + i
        f_idx = max(0, min(f_idx, len(frame_amplitudes) - 1))
        amp = frame_amplitudes[f_idx]
        
        # نضيف smoothing
        bar_h = int(min_bar_h + amp * (max_bar_h - min_bar_h))
        bar_h = max(min_bar_h, bar_h)
        
        x = start_x + i * bar_spacing + bar_spacing // 2
        
        # نقاط الدائرة الصغيرة على الجانبين (نقاط الـ dotted)
        if i == 0 or i == num_bars - 1:
            dot_x = x
            for dot_y_offset in range(-3, 4, 1):
                dot_cy = center_y + dot_y_offset * 18
                draw.ellipse([dot_x-3, dot_cy-3, dot_x+3, dot_cy+3], fill=(200,200,200,180))
            continue
        
        # رسم الشريط مع تدرج لوني (أبيض في المنتصف، رمادي في الأطراف)
        y1 = center_y - bar_h
        y2 = center_y + bar_h
        
        # اللون بناءً على الموقع
        alpha = int(150 + 105 * amp)
        color = (255, 255, 255, alpha)
        
        # رسم المستطيل المدور
        draw.rounded_rectangle([x - bar_w//2, y1, x + bar_w//2, y2], 
                                radius=bar_w//2, fill=color)
    
    return np.array(img)

# ================== رسم العنوان بخط الثلث ==================

def make_title_image(surah_name, reciter_name, width=WIDTH, height=HEIGHT):
    """
    يرسم عنوان السورة بخط الثلث بنفس ستايل الصورة المرجعية
    """
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font_title = ImageFont.truetype(FONT_PATH_AR, 150)  # خط الثلث للعنوان
        font_reciter = ImageFont.truetype(FONT_PATH_BODY, 70)
    except:
        font_title = ImageFont.load_default()
        font_reciter = ImageFont.load_default()
    
    title_y = 200  # موقع العنوان في الأعلى مثل الصورة
    
    # رسم اسم السورة بالذهبي مع ظل كثيف (نفس ستايل الصورة)
    surah_display = process_ar(surah_name)
    draw_text_with_shadow(draw, (width//2, title_y), surah_display, font_title, 
                          fill_color="#FFD700",
                          shadow_color=(0,0,0,230))
    
    # رسم اسم القارئ تحت العنوان بالأبيض (نفس الصورة)
    reciter_display = process_ar(reciter_name)
    draw_text_with_shadow(draw, (width//2, title_y + 180), reciter_display, font_reciter,
                          fill_color="white",
                          shadow_color=(0,0,0,200))
    
    return np.array(img)

# ================== جلب الآيات بدون بسملة/استعاذة ==================

def fetch_ayahs_no_basmala(surah_id, reciter):
    """
    يجلب كل آية كملف منفصل مباشرة من mp3quran
    بدون بسملة/استعاذة لأننا نجمع الآيات الفردية
    """
    print(f"📥 جلب بيانات النص للسورة {surah_id}...")
    
    # نص عربي + ترجمة
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{surah_id}/{reciter['api_id']}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{surah_id}/en.sahih").json()['data']
    
    surah_name = res_ar['name']
    ayahs_ar = res_ar['ayahs']
    ayahs_en = res_en['ayahs']
    
    print(f"📖 السورة: {surah_name} - عدد الآيات: {len(ayahs_ar)}")
    
    # تحميل كل آية منفصلة + قياس مدتها
    # هذا يضمن 100% عدم وجود بسملة/استعاذة في الصوت
    ayahs_data = []
    current_time = 0.0
    audio_segments = []
    
    print("⬇️ تحميل الآيات الفردية...")
    for i, (a_ar, a_en) in enumerate(zip(ayahs_ar, ayahs_en)):
        ayah_url = a_ar['audio']
        ayah_file = f"ayah_{i:03d}.mp3"
        
        try:
            content = requests.get(ayah_url, timeout=15).content
            with open(ayah_file, 'wb') as f:
                f.write(content)
            
            clip = mp.AudioFileClip(ayah_file)
            dur = clip.duration
            clip.close()
            
            ayahs_data.append({
                "text_ar": a_ar['text'],
                "text_en": a_en['text'],
                "number": a_ar['numberInSurah'],
                "audio_file": ayah_file,
                "duration": dur,
                "start": current_time,
                "end": current_time + dur
            })
            audio_segments.append(ayah_file)
            current_time += dur
            
            if i % 5 == 0:
                print(f"  ✅ آية {i+1}/{len(ayahs_ar)}")
                
        except Exception as e:
            print(f"  ⚠️ خطأ في آية {i+1}: {e}")
            if os.path.exists(ayah_file):
                os.remove(ayah_file)
    
    return surah_name, ayahs_data, audio_segments

def build_final_audio(ayahs_data, max_duration=59.0):
    """
    يختار الآيات المناسبة ويدمجها في ملف صوتي واحد
    بدون أي صوت إضافي (لا بسملة لا استعاذة)
    """
    selected = []
    total_dur = 0.0
    
    for ayah in ayahs_data:
        if total_dur + ayah['duration'] > max_duration:
            break
        selected.append(ayah)
        total_dur += ayah['duration']
    
    print(f"🎵 {len(selected)} آية، مدة: {total_dur:.2f}ث")
    
    # دمج الآيات بـ ffmpeg concat
    concat_file = "concat_list.txt"
    with open(concat_file, 'w') as f:
        for ayah in selected:
            f.write(f"file '{ayah['audio_file']}'\n")
    
    output_audio = "final_audio.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file, "-c", "copy", output_audio
    ], capture_output=True)
    
    os.remove(concat_file)
    
    return selected, total_dur, output_audio

# ================== المحرك الرئيسي ==================

def build_shorts_video():
    print("🚀 [1/7] بدء التجهيز...")
    
    reciter = random.choice(RECITERS_DATA)
    print(f"🎙️ القارئ: {reciter['name']}")
    
    # سور من الجزء الأخير (78 الى 114)
    s_id = random.randint(78, 114)
    
    # 1. جلب الآيات الفردية (بدون بسملة/استعاذة)
    surah_name, ayahs_data, audio_segments = fetch_ayahs_no_basmala(s_id, reciter)
    
    # 2. بناء الصوت النهائي (آيات مختارة فقط بحد 59 ثانية)
    print("🔧 [2/7] بناء الصوت النهائي...")
    selected_ayahs, final_duration, audio_path = build_final_audio(ayahs_data)
    
    # 3. تحليل الصوت لاستخراج amplitudes
    print("📊 [3/7] تحليل الصوت...")
    frame_amplitudes = extract_waveform_data(audio_path, fps=24, duration=final_duration)
    
    # 4. تحميل خلفية من Pexels
    print("🌄 [4/7] تحميل الخلفية...")
    headers = {'Authorization': PEXELS_API_KEY}
    try:
        v_res = requests.get(
            'https://api.pexels.com/videos/search?query=nature+sky&orientation=portrait&per_page=15',
            headers=headers
        ).json()
        v_url = random.choice(v_res['videos'])['video_files'][0]['link']
        with open("bg_v.mp4", "wb") as f:
            f.write(requests.get(v_url).content)
        bg = loop(
            mp.VideoFileClip("bg_v.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT),
            duration=final_duration
        )
    except Exception as e:
        print(f"⚠️ خلفية افتراضية ({e})")
        bg = mp.ColorClip(size=(WIDTH, HEIGHT), color=(10, 15, 30), duration=final_duration)
    
    # 5. تحميل الخطوط
    try:
        font_title = ImageFont.truetype(FONT_PATH_AR, 150)   # خط الثلث للعنوان
        font_body = ImageFont.truetype(FONT_PATH_BODY, 85)   # خط الجسم للآيات
        font_en = ImageFont.truetype(FONT_PATH_EN, 40)
    except Exception as e:
        print(f"⚠️ خطأ في الخطوط: {e}")
        font_title = font_body = font_en = ImageFont.load_default()
    
    print("⚙️ [5/7] إنشاء مقاطع الفيديو...")
    
    # تعتيم الخلفية
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0, 0, 0), duration=final_duration).set_opacity(0.45)
    
    # --- العنوان الثابت ---
    title_img = make_title_image(surah_name, reciter['name'])
    title_clip = mp.ImageClip(title_img).set_duration(final_duration)
    
    # --- مقاطع الآيات ---
    text_clips = []
    for item in selected_ayahs:
        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        
        # الآيات العربية
        ar_lines = safe_wrap(item['text_ar'], max_chars=30)
        en_lines = safe_wrap(item['text_en'], max_chars=45)
        
        total_h = len(ar_lines) * 130 + 60 + len(en_lines) * 58
        y = (HEIGHT - total_h) / 2 + 100  # تحريك للأسفل قليلاً (العنوان في الأعلى)
        
        for line in ar_lines:
            draw_text_with_shadow(d, (WIDTH//2, y), process_ar(line), font_body, "white")
            y += 130
        
        y += 50
        for line in en_lines:
            d.text((WIDTH//2, y), line, font=font_en, fill="#CCCCCC", 
                   anchor="mm", stroke_width=2, stroke_fill="black")
            y += 58
        
        # رقم الآية
        ayah_num = f"({item['number']})"
        d.text((WIDTH//2, y + 30), process_ar(ayah_num), font=font_en, 
               fill="#FFD700", anchor="mm")
        
        clip = (mp.ImageClip(np.array(img))
                .set_start(item['start'])
                .set_end(item['end'])
                .crossfadein(0.3)
                .crossfadeout(0.3))
        text_clips.append(clip)
    
    # --- شريط الصوت المتحرك الحقيقي ---
    print("🎵 [6/7] إنشاء شريط الصوت المتحرك...")
    
    # نمرر الـ amplitudes للـ lambda
    _amps = frame_amplitudes  # reference محلية
    waveform_clip = mp.VideoClip(
        lambda t: make_waveform_frame(t, _amps, fps=24, width=WIDTH, height=HEIGHT),
        duration=final_duration
    ).set_fps(24)
    
    # --- الصوت النهائي ---
    final_audio = mp.AudioFileClip(audio_path)
    
    # --- التجميع ---
    final = mp.CompositeVideoClip([
        bg, dark, title_clip, waveform_clip
    ] + text_clips).set_audio(final_audio)
    
    print("⏳ [7/7] جاري الرندر...")
    final.write_videofile(
        "final_shorts.mp4",
        fps=24,
        codec="libx264",
        audio_codec="aac",
        bitrate="8000k",
        preset="ultrafast",
        logger=None,
        threads=4
    )
    
    # ================== تنظيف الملفات المؤقتة ==================
    print("🧹 تنظيف...")
    for f in audio_segments:
        if os.path.exists(f): os.remove(f)
    if os.path.exists(audio_path): os.remove(audio_path)
    if os.path.exists("bg_v.mp4"): os.remove("bg_v.mp4")
    
    # ================== الرفع على يوتيوب ==================
    print("📡 رفع على يوتيوب...")
    youtube = youtube_authenticate()
    
    desc = (
        f"تلاوة خاشعة من سورة {surah_name}\n"
        f"بصوت {reciter['name']}\n\n"
        f"#quran #القرآن_الكريم #تلاوة #shorts #islam"
    )
    body = {
        'snippet': {
            'title': f'تلاوة خاشعة ❤️ {surah_name} | {reciter["name"]} #shorts',
            'description': desc,
            'categoryId': '22',
            'tags': ['quran', 'قرآن', 'تلاوة', 'shorts', 'islam', surah_name]
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
    
    print("✅ تم بنجاح!")

if __name__ == "__main__":
    if not is_uploaded_today() or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch':
        try:
            build_shorts_video()
            mark_uploaded_today()
        except Exception as e:
            print(f"🔥 خطأ: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
