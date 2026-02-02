import os, requests, random, json, base64, textwrap
import numpy as np
import moviepy.editor as mp
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 1. الإعدادات الأساسية ---
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
AUDIO_EDITION = 'ar.alafasy' 
FONT_PATH = "ArabicFont.ttf" 

def process_ar(t):
    """معالجة النص العربي لليونكس وجيت هب أكسشنز"""
    reshaped = arabic_reshaper.reshape(t)
    bidi_text = get_display(reshaped)
    return bidi_text[::-1] # العكس اليدوي لضبط المنطق المعكوس في المونتاج

def youtube_authenticate():
    """تسجيل الدخول لليوتيوب باستخدام التوكن"""
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🚀 [1/4] جاري تحضير موارد فيديو Shorts...")
    s_id = random.randint(1, 114)
    res = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    s_name = res['name']
    
    # اختيار مقطع قصير لضمان وقت الشورتس (بحد أقصى 50 ثانية)
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
    dur = min(50, final_audio.duration) # إجبار الفيديو يكون شورتس
    final_audio = final_audio.subclip(0, dur)
    full_text = " ۞ ".join(text_parts)

    # خلفية Pexels راسية (Shorts)
    headers = {'Authorization': PEXELS_API_KEY}
    v_res = requests.get(f'https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15', headers=headers).json()
    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f:
        f.write(requests.get(v_url).content)

    print(f"⚙️ [2/4] جاري المونتاج لسورة {s_name}...")
    bg = mp.VideoFileClip("bg_v.mp4").resize(height=1280).crop(x1=0, y1=0, width=720, height=1280).set_duration(dur)
    dark = mp.ColorClip(size=(720, 1280), color=(0,0,0), duration=dur).set_opacity(0.5)

    # تصميم البطاقة (UI)
    ui_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ui_canvas)
    # رسم مستطيل شفاف خلف النص
    draw.rounded_rectangle([60, 300, 660, 1000], radius=40, fill=(0,0,0,180))
    
    # اسم السورة
    font_s = ImageFont.truetype(FONT_PATH, 85)
    draw.text((360, 220), process_ar(s_name), font=font_s, fill="#FFD700", anchor="mm")
    ui_clip = mp.ImageClip(np.array(ui_canvas)).set_duration(dur)

    # معالجة النص الطويل
    lines = textwrap.wrap(full_text, width=28)
    line_h = 95
    canvas_h = (len(lines) + 2) * line_h
    txt_img = Image.new('RGBA', (600, canvas_h), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(txt_img)
    font_a = ImageFont.truetype(FONT_PATH, 48)
    
    for i, line in enumerate(lines):
        d_t.text((300, i*line_h + 100), process_ar(line), font=font_a, fill="white", anchor="mm")
    
    txt_clip = mp.ImageClip(np.array(txt_img)).set_duration(dur)
    # سرعة التحريك الهادئة
    moving_txt = txt_clip.set_position(lambda t: ('center', 900 - (t * (canvas_h / dur))))
    
    # قص منطقة النص لتبقى داخل البطاقة فقط
    text_area = mp.CompositeVideoClip([moving_txt], size=(720, 1280)).crop(y1=320, y2=980, x1=70, x2=650).set_position(('center', 320))

    # دمج كل الطبقات
    final = mp.CompositeVideoClip([bg, dark, text_area, ui_clip]).set_audio(final_audio)
    
    # الرندر (صامت لمنع التهنيج)
    print("⏳ [3/4] جاري الرندر النهائي (Rendering)... يرجى الانتظار")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", logger=None, threads=4)

    print("📡 [4/4] جاري الرفع لليوتيوب كـ Shorts...")
    try:
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
        print(f"✅ مبروك! الفيديو اتنشر: سورة {s_name}")
    except Exception as e:
        print(f"❌ فشل الرفع: {e}")

if __name__ == "__main__":
    build_shorts_video()
