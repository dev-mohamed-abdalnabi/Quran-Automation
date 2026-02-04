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

# ================== إعدادات السجل (Log) ==================
LOG_FILE = "daily_log.txt"

def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def is_uploaded_today():
    if not os.path.exists(LOG_FILE):
        return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        return content == today_str()

def mark_uploaded_today():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(today_str())

# ================== الإعدادات الأساسية ==================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
AUDIO_EDITION = 'ar.alafasy'
FONT_PATH = "ArabicFont.ttf" 

# --- معالجة العربي: الطريقة الكلاسيكية (السادة) ---
def process_ar(text):
    if not text: return ""
    try:
        # 1. تشبيك الحروف ببعضها (عشان متبقاش مقطعة)
        reshaped_text = arabic_reshaper.reshape(text)
        
        # 2. قلب ترتيب الحروف للعرض (عشان Pillow بيكتب من الشمال لليمين)
        # مسحنا أي إعدادات تانية عشان نمنع اللف المزدوج
        bidi_text = get_display(reshaped_text)
        
        return bidi_text
    except Exception as e:
        print(f"Error parsing Arabic: {e}")
        return text

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    if not TOKEN_B64:
        raise ValueError("TOKEN_BASE64 secret is missing!")
    
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🚀 [1/4] جاري تحضير موارد فيديو Shorts...")

    s_id = random.randint(1, 114)
    res = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    s_name = res['name']
    
    ayahs_segment = res['ayahs'][:3]
    audio_clips = []
    text_parts = []

    for a in ayahs_segment:
        f_path = f"temp_{a['number']}.mp3"
        with open(f_path, 'wb') as f:
            f.write(requests.get(a['audio']).content)
        audio_clips.append(mp.AudioFileClip(f_path))
        text_parts.append(a['text'])

    final_audio = mp.concatenate_audioclips(audio_clips)
    dur = min(58, final_audio.duration) 
    final_audio = final_audio.subclip(0, dur)
    full_text = " ۞ ".join(text_parts)

    headers = {'Authorization': PEXELS_API_KEY}
    v_res = requests.get(
        'https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15',
        headers=headers
    ).json()

    if not v_res.get('videos'):
        raise Exception("فشل في جلب فيديو الخلفية من Pexels")

    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f:
        f.write(requests.get(v_url).content)

    print(f"⚙️ [2/4] جاري المونتاج لسورة {s_name}...")

    bg = mp.VideoFileClip("bg_v.mp4").resize(height=1280).crop(x1=0, y1=0, width=720, height=1280).set_duration(dur)
    dark = mp.ColorClip(size=(720, 1280), color=(0,0,0), duration=dur).set_opacity(0.5)

    ui_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ui_canvas)
    
    draw.rounded_rectangle([50, 250, 670, 1030], radius=30, fill=(0,0,0,160))

    try:
        font_s = ImageFont.truetype(FONT_PATH, 80)
        font_a = ImageFont.truetype(FONT_PATH, 45)
    except:
        print("⚠️ خطأ: ملف الخط ArabicFont.ttf غير موجود. تأكد من رفعه.")
        sys.exit(1)

    # طباعة تجريبية في الـ Logs عشان نتأكد
    print(f"DEBUG Text (Original): {s_name}")
    print(f"DEBUG Text (Processed): {process_ar(s_name)}")

    # كتابة العنوان
    draw.text((360, 180), process_ar(s_name), font=font_s, fill="#FFD700", anchor="mm")
    ui_clip = mp.ImageClip(np.array(ui_canvas)).set_duration(dur)

    lines = textwrap.wrap(full_text, width=35)
    line_h = 90
    canvas_h = (len(lines) + 3) * line_h
    txt_img = Image.new('RGBA', (620, canvas_h), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(txt_img)

    for i, line in enumerate(lines):
        # هنا التعديل: شلنا أي محاذاة ممكن تلخبط
        d_t.text((310, i*line_h + 50), process_ar(line), font=font_a, fill="white", anchor="mm")

    txt_clip = mp.ImageClip(np.array(txt_img)).set_duration(dur)
    
    moving_txt = txt_clip.set_position(lambda t: ('center', 950 - (t * (canvas_h / (dur + 5))))) 
    
    text_area = mp.CompositeVideoClip([moving_txt], size=(720, 1280)).crop(y1=260, y2=1020, x1=50, x2=670).set_position(('center', 0))

    final = mp.CompositeVideoClip([bg, dark, ui_clip, text_area]).set_audio(final_audio)

    print("⏳ [3/4] جاري الرندر النهائي...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", logger=None, threads=4)

    print("📡 [4/4] جاري الرفع لليوتيوب...")
    youtube = youtube_authenticate()

    body = {
        'snippet': {
            'title': f'تلاوة خاشعة - {s_name} #shorts #quran #قرآن',
            'description': f'تلاوة لسورة {s_name} بصوت مشاري العفاسي.\n\n#quran #islam #shorts',
            'categoryId': '22'
        },
        'status': {'privacyStatus': 'public'}
    }

    media = MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()

    print(f"✅ تم نشر الفيديو بنجاح: سورة {s_name}")

# ================== نقطة الدخول (Entry Point) ==================
if __name__ == "__main__":

    # جلب نوع الحدث (Schedule vs Dispatch)
    event_name = os.environ.get('GITHUB_EVENT_NAME') 

    if is_uploaded_today():
        if event_name == 'workflow_dispatch':
            print("⚠️ تنبيه: الفيديو اليومي نزل بالفعل.")
            print("▶️ تشغيل يدوي: سيتم إنشاء فيديو إضافي للاختبار.")
        else:
            print("✋ الفيديو نزل النهاردة. مفيش شغل دلوقتي.")
            sys.exit(0)
    else:
        print("📅 يوم جديد، فيديو جديد...")

    print("🎬 توكلنا على الله...")

    try:
        build_shorts_video()
        mark_uploaded_today()
        print("📝 تمت العملية بنجاح.")
        
    except Exception as e:
        print(f"🔥 الحق في مشكلة: {e}")
        sys.exit(1)
