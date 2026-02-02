import os, sys, requests, random, time, textwrap, pickle, base64, json
import numpy as np
import moviepy.editor as mp
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw
from proglog import ProgressBarLogger
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# استرجاع المفاتيح من GitHub Secrets
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
TOKEN_B64 = os.environ.get("TOKEN_BASE64")
CLIENT_SECRET_TXT = os.environ.get("CLIENT_SECRET")

if TOKEN_B64:
    with open("token.pickle", "wb") as f:
        f.write(base64.b64decode(TOKEN_B64))

if CLIENT_SECRET_TXT:
    with open("client_secret.json", "w") as f:
        f.write(CLIENT_SECRET_TXT)

FONT_PATH = "ArabicFont.ttf" 
AUDIO_EDITION = 'ar.minshawi' 

def process_ar(t): 
    return get_display(arabic_reshaper.reshape(t), base_dir='R')[::-1]

def youtube_authenticate():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            return None
    return build('youtube', 'v3', credentials=creds)

def upload_video(file_path, title, description):
    youtube = youtube_authenticate()
    if not youtube: return
    body = {
        'snippet': {'title': title, 'description': description, 'tags': ['Quran', 'Islam'], 'categoryId': '22'},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
    print(f"Done: https://youtu.be/{response['id']}")

def build_steel_video():
    s_id = random.randint(1, 114)
    res = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    s_name, s_english, all_ayahs = res['name'], res['englishName'], res['ayahs']
    selected_ayahs = all_ayahs[random.randint(0, max(0, len(all_ayahs) - 6)) :][:5]

    audio_clips, text_content = [], []
    for a in selected_ayahs:
        r = requests.get(a['audio'], timeout=20) 
        with open(f"temp_{a['number']}.mp3", 'wb') as f: f.write(r.content)
        audio_clips.append(mp.AudioFileClip(f"temp_{a['number']}.mp3"))
        text_content.append(a['text'])

    final_audio = mp.concatenate_audioclips(audio_clips)
    duration, full_text = final_audio.duration + 2, " ۞ ".join(text_content)

    v_res = requests.get(f'https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=5', headers={'Authorization': PEXELS_API_KEY}).json()
    with open("bg_v.mp4", 'wb') as f: f.write(requests.get(v_res['videos'][0]['video_files'][0]['link']).content)

    bg = mp.VideoFileClip("bg_v.mp4").resize(height=1280).crop(x1=0, y1=0, width=720, height=1280).loop(duration=duration)
    dark = mp.ColorClip(size=(720, 1280), color=(0,0,0), duration=duration).set_opacity(0.3)

    ui_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ui_canvas)
    draw.rounded_rectangle([70, 290, 650, 990], radius=35, fill=(0,0,0,140), outline=(255,255,255,100), width=2)
    draw.text((360, 230), process_ar(s_name), font=ImageFont.truetype(FONT_PATH, 70), fill="#FFFFFF", anchor="mm")
    
    lines = textwrap.wrap(full_text, width=30)
    canvas_h = (len(lines) * 90) + 700
    txt_img = Image.new('RGBA', (580, canvas_h), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(txt_img)
    for i, line in enumerate(lines):
        d_t.text((290, i*90 + 350), process_ar(line), font=ImageFont.truetype(FONT_PATH, 42), fill="white", anchor="mm")

    moving_txt = mp.ImageClip(np.array(txt_img)).set_duration(duration).set_position(lambda t: ('center', 290 - (t * (canvas_h-600)/duration)))
    text_area = mp.CompositeVideoClip([moving_txt], size=(720, 1280)).crop(y1=300, y2=980, x1=70, x2=650).set_position(('center', 300))

    final = mp.CompositeVideoClip([bg, dark, text_area, mp.ImageClip(np.array(ui_canvas)).set_duration(duration)]).set_audio(final_audio)
    final.write_videofile("final.mp4", fps=24, codec="libx264", preset="ultrafast")
    upload_video("final.mp4", f"تلاوة سورة {s_name}", f"تلاوة هادئة #قرآن")

if __name__ == "__main__":
    build_steel_video()
