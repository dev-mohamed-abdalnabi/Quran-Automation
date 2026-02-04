import os, requests, random, json, base64, textwrap, sys
from datetime import datetime
import numpy as np
import moviepy.editor as mp
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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

# ================== الإعدادات الأساسية ==================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
AUDIO_EDITION = 'ar.alafasy'
FONT_PATH = "ArabicFont.ttf"

# معالجة العربي (الكلاسيكية المضمونة)
def process_ar(t):
    try:
        reshaped = arabic_reshaper.reshape(t)
        bidi_text = get_display(reshaped)
        return bidi_text[::-1]
    except:
        return t

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🚀 [1/4] جاري تحضير موارد فيديو Shorts...")

    s_id = random.randint(1, 114)
    res = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    s_name = res['name']
    all_ayahs = res['ayahs']

    # --- التعديل 1: تجميع الآيات بناءً على الوقت مش العدد ---
    audio_clips = []
    text_parts = []
    current_duration = 0
    TARGET_DURATION = 35  # الهدف: الفيديو يكون حوالي 35 ثانية أو أكثر

    print(f"📖 تم اختيار سورة {s_name}. جاري تجميع الآيات لتناسب الوقت...")

    for i, a in enumerate(all_ayahs):
        # بنحمل الآية
        f_path = f"temp_{i}.mp3"
        with open(f_path, 'wb') as f:
            f.write(requests.get(a['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        
        # نضيفها للقائمة
        audio_clips.append(clip)
        text_parts.append(a['text'])
        current_duration += clip.duration

        # لو وصلنا للوقت المطلوب أو عدينا 55 ثانية (عشان الشورتس آخره 60) نوقف
        if current_duration >= TARGET_DURATION:
            if current_duration > 58: # لو زاد أوي نشيل آخر آية عشان منعديش الدقيقة
                audio_clips.pop()
                text_parts.pop()
            break
    
    final_audio = mp.concatenate_audioclips(audio_clips)
    # التأكيد النهائي إن المدة لا تتخطى 59 ثانية
    dur = min(59, final_audio.duration)
    final_audio = final_audio.subclip(0, dur)
    
    full_text = " ۞ ".join(text_parts)
    print(f"⏱️ مدة الصوت النهائية: {dur:.2f} ثانية")

    # الخلفية
    headers = {'Authorization': PEXELS_API_KEY}
    v_res = requests.get(
        'https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15',
        headers=headers
    ).json()

    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f:
        f.write(requests.get(v_url).content)

    print(f"⚙️ [2/4] جاري المونتاج لسورة {s_name}...")

    bg = mp.VideoFileClip("bg_v.mp4").resize(height=1280).crop(x1=0, y1=0, width=720, height=1280).set_duration(dur)
    
    # جعل طبقة التعتيم أغمق قليلاً (0.6 بدل 0.5)
    dark = mp.ColorClip(size=(720, 1280), color=(0,0,0), duration=dur).set_opacity(0.6)

    ui_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ui_canvas)
    
    # --- التعديل 2: تغميق المربع الخلفي للنص ---
    # fill=(0,0,0,220) -> الرقم 220 ده الشفافية (من 0 لـ 255)
    # كل ما يقرب لـ 255 يبقى أسود خالص، فالكلام الأبيض يظهر أوضح
    draw.rounded_rectangle([50, 250, 670, 1030], radius=30, fill=(0,0,0,230))

    font_s = ImageFont.truetype(FONT_PATH, 85)
    draw.text((360, 200), process_ar(s_name), font=font_s, fill="#FFD700", anchor="mm")
    ui_clip = mp.ImageClip(np.array(ui_canvas)).set_duration(dur)

    lines = textwrap.wrap(full_text, width=28)
    line_h = 95
    canvas_h = (len(lines) + 2) * line_h
    txt_img = Image.new('RGBA', (600, canvas_h), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(txt_img)
    font_a = ImageFont.truetype(FONT_PATH, 48)

    for i, line in enumerate(lines):
        # جعل النص أبيض ناصع
        d_t.text((300, i*line_h + 100), process_ar(line), font=font_a, fill=(255, 255, 255, 255), anchor="mm")

    txt_clip = mp.ImageClip(np.array(txt_img)).set_duration(dur)
    
    # تعديل سرعة السكرول لتتناسب مع مدة الصوت الجديدة
    moving_txt = txt_clip.set_position(lambda t: ('center', 900 - (t * (canvas_h / (dur + 2)))))
    
    text_area = mp.CompositeVideoClip([moving_txt], size=(720, 1280)).crop(y1=320, y2=980, x1=70, x2=650).set_position(('center', 320))

    final = mp.CompositeVideoClip([bg, dark, text_area, ui_clip]).set_audio(final_audio)

    print("⏳ [3/4] جاري الرندر النهائي...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", logger=None, threads=4)

    print("📡 [4/4] جاري الرفع لليوتيوب كـ Shorts...")
    youtube = youtube_authenticate()

    body = {
        'snippet': {
            'title': f'تلاوة خاشعة - {s_name} #shorts #quran',
            'description': f'سورة {s_name} بصوت مشاري العفاسي',
            'categoryId': '22'
        },
        'status': {'privacyStatus': 'public'}
    }

    media = MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()

    print(f"✅ تم نشر الفيديو بنجاح: سورة {s_name}")

# ================== التشغيل الرئيسي ==================
if __name__ == "__main__":

    event_name = os.environ.get('GITHUB_EVENT_NAME')

    if is_uploaded_today():
        if event_name == 'workflow_dispatch':
            print("⚠️ تنبيه: الفيديو اليومي مسجل إنه نزل.")
            print("🛠️ تشغيل يدوي: جاري إنشاء فيديو إضافي طويل ومحسن...")
        else:
            print("✅ فيديو النهارده نزل خلاص. (Automatic Skip)")
            sys.exit(0)
    else:
        print("📅 مفيش فيديو نزل النهاردة. جاري العمل...")

    try:
        build_shorts_video()
        mark_uploaded_today()
        print("📝 تم تحديث السجل اليومي بنجاح.")
    except Exception as e:
        print("🔥 حصل خطأ أثناء التنفيذ أو الرفع:", e)
        sys.exit(1)
