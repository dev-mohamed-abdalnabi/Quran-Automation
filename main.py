import os, requests, random, json, base64, textwrap
import numpy as np
import moviepy.editor as mp
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- الإعدادات ---
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
AUDIO_EDITION = 'ar.alafasy' 
FONT_PATH = "ArabicFont.ttf" 

def process_ar(t):
    # النص العربي المظبوط في جيت هب
    reshaped = arabic_reshaper.reshape(t)
    return get_display(reshaped)

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🎬 [1/4] جاري تحضير موارد فيديو Shorts...")
    s_id = random.randint(1, 114)
    res = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    s_name = res['name']
    
    # اختيار مقطع قصير (حوالي 4 آيات)
    ayahs_segment = res['ayahs'][:4] 
    audio_clips = []
    text_parts = []
    
    for a in ayahs_segment:
        f_path = f"temp_{a['number']}.mp3"
        with open(f_path, 'wb') as f: f.write(requests.get(a['audio']).content)
        audio_clips.append(mp.AudioFileClip(f_path))
        text_parts.append(a['text'])

    final_audio = mp.concatenate_audioclips(audio_clips)
    dur = min(58, final_audio.duration)
    full_text = " ۞ ".join(text_parts)

    # خلفية Pexels
    headers = {'Authorization': PEXELS_API_KEY}
    v_res = requests.get(f'https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=10', headers=headers).json()
    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)

    print(f"⚙️ [2/4] جاري تصميم الجرافيك لـ {s_name}...")
    bg = mp.VideoFileClip("bg_v.mp4").resize(height=1280).crop(x1=0, y1=0, width=720, height=1280).loop(duration=dur)
    dark = mp.ColorClip(size=(720, 1280), color=(0,0,0), duration=dur).set_opacity(0.4)

    # تصميم البطاقة
    ui_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ui_canvas)
    draw.rounded_rectangle([60, 240, 660, 1040], radius=40, fill=(0,0,0,160), outline=(255,215,0,150), width=3)
    font_s = ImageFont.truetype(FONT_PATH, 80)
    draw.text((360, 180), process_ar(s_name), font=font_s, fill="#FFD700", anchor="mm")
    ui_clip = mp.ImageClip(np.array(ui_canvas)).set_duration(dur)

    # النص المتحرك
    lines = textwrap.wrap(full_text, width=25)
    line_h = 100
    canvas_h = (len(lines) + 2) * line_h
    txt_img = Image.new('RGBA', (600, canvas_h), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(txt_img)
    font_a = ImageFont.truetype(FONT_PATH, 45)
    for i, line in enumerate(lines):
        d_t.text((300, i*line_h + 100), process_ar(line), font=font_a, fill="white", anchor="mm")
    
    txt_clip = mp.ImageClip(np.array(txt_img)).set_duration(dur)
    moving_txt = txt_clip.set_position(lambda t: ('center', 800 - (t * (canvas_h / dur))))
    text_area = mp.CompositeVideoClip([moving_txt], size=(720, 1280)).crop(y1=260, y2=1020, x1=70, x2=650).set_position(('center', 260))

    # --- الرندر مع شريط تقدم نظيف ---
    print(f"🚀 [3/4] جاري الرندر النهائي ( Rendering )...")
    final = mp.CompositeVideoClip([bg, dark, text_area, ui_clip]).set_audio(final_audio)
    
    # استخدام logger='bar' يعطي شريط تقدم سطر واحد يتحدث تلقائياً
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", logger='bar')

    print("🌐 [4/4] جاري الرفع لليوتيوب...")
    try:
        youtube = youtube_authenticate()
        body = {
            'snippet': {'title': f'تلاوة خاشعة - {s_name} #shorts #quran', 'description': 'تلاوة يومية هادئة', 'categoryId': '22'},
            'status': {'privacyStatus': 'public'}
        }
        media = MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
        youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
        print(f"✅ تم الرفع بنجاح سورة {s_name}!")
    except Exception as e:
        print(f"❌ خطأ في الرفع: {e}")

if __name__ == "__main__":
    build_shorts_video()
