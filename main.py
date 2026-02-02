import os, sys, requests, random, time, textwrap, json, base64
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
AUDIO_EDITION = 'ar.minshawi' 
FONT_PATH = "ArabicFont.ttf" # تأكد من رفع ملف الخط في المستودع بنفس الاسم

def process_ar(t): 
    return get_display(arabic_reshaper.reshape(t))

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def upload_video(file_path, title, description):
    youtube = youtube_authenticate()
    body = {
        'snippet': {
            'title': title, 'description': description,
            'tags': ['Quran', 'Islam', 'راحة_نفسية', 'Minshawi'],
            'categoryId': '22'
        },
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    response = request.execute()
    print(f"✅ تم النشر بنجاح! ID: {response['id']}")

def build_steel_video():
    print("🛠️ [1/5] اختيار الآيات...")
    s_id = random.randint(1, 114)
    res = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    s_name = res['name']
    all_ayahs = res['ayahs']
    
    start_idx = random.randint(0, max(0, len(all_ayahs) - 6))
    selected_ayahs = all_ayahs[start_idx : start_idx + 5]

    print("📥 [2/5] تحميل الصوت...")
    audio_clips = []
    text_content = []
    for a in selected_ayahs:
        f_path = f"temp_{a['number']}.mp3"
        r = requests.get(a['audio']) 
        with open(f_path, 'wb') as f: f.write(r.content)
        audio_clips.append(mp.AudioFileClip(f_path))
        text_content.append(a['text'])

    final_audio = mp.concatenate_audioclips(audio_clips)
    duration = final_audio.duration + 2
    full_text = " ۞ ".join(text_content)

    # خلفية Pexels
    headers = {'Authorization': PEXELS_API_KEY}
    v_queries = ["clouds sky vertical", "nature calm vertical", "stars night vertical"]
    v_res = requests.get(f'https://api.pexels.com/videos/search?query={random.choice(v_queries)}&orientation=portrait&per_page=5', headers=headers).json()
    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg_v.mp4", "wb") as f: f.write(requests.get(v_url).content)

    print(f"⚙️ [3/5] تصميم الجرافيك...")
    bg = mp.VideoFileClip("bg_v.mp4").resize(height=1280).crop(x1=0, y1=0, width=720, height=1280).loop(duration=duration)
    dark = mp.ColorClip(size=(720, 1280), color=(0,0,0), duration=duration).set_opacity(0.3)

    # البطاقة الشفافة
    win_w, win_h = 580, 700 
    win_y = (1280 - win_h) // 2
    ui_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ui_canvas)
    draw.rounded_rectangle([((720-win_w)//2), win_y, ((720+win_w)//2), win_y+win_h], radius=35, fill=(0,0,0,140), outline=(255,255,255,100), width=2)
    
    # اسم السورة
    font_title = ImageFont.truetype(FONT_PATH, 70)
    draw.text((360, win_y - 60), process_ar(s_name), font=font_title, fill="#FFFFFF", anchor="mm")
    ui_clip = mp.ImageClip(np.array(ui_canvas)).set_duration(duration)

    # النص المتحرك
    lines = textwrap.wrap(full_text, width=30)
    line_h = 90
    canvas_h = (len(lines) * line_h) + win_h
    txt_img = Image.new('RGBA', (win_w, canvas_h), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(txt_img)
    font_ayah = ImageFont.truetype(FONT_PATH, 42)
    for i, line in enumerate(lines):
        d_t.text((win_w//2, i*line_h + (win_h//2)), process_ar(line), font=font_ayah, fill="white", anchor="mm")

    txt_clip = mp.ImageClip(np.array(txt_img)).set_duration(duration)
    def scroll_func(t):
        speed = (canvas_h - win_h + 100) / duration
        return ('center', (win_y) - (t * speed) + 50)

    moving_txt = txt_clip.set_position(scroll_func)
    text_area = mp.CompositeVideoClip([moving_txt], size=(720, 1280)).crop(y1=win_y+10, y2=win_y+win_h-10, x1=50, x2=670).set_position(('center', win_y+10))

    final = mp.CompositeVideoClip([bg, dark, text_area, ui_clip]).set_audio(final_audio)
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", preset="ultrafast")

    print("🌐 [5/5] رفع لليوتيوب...")
    upload_video("final.mp4", f"راحة نفسية - سورة {s_name}", f"تلاوة هادئة من سورة {s_name}\n#Quran #قرآن")

if __name__ == "__main__":
    build_steel_video()
