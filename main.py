import os, requests, random, json, base64, sys
from datetime import datetime
import numpy as np
import moviepy.editor as mp
from moviepy.video.fx.all import loop 
from moviepy.audio.fx.all import audio_fadeout
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ================== [1] الإعدادات ==================
WIDTH, HEIGHT = 1080, 1920
MAX_SHORT_DURATION = 58.0 
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
LOG_FILE = "daily_log.txt"

RECITERS = ['ar.alafasy', 'ar.husary', 'ar.mahermuaiqly', 'ar.ahmedajamy']
SAFE_QUERIES = ["nature drone", "ocean sea waves", "galaxy stars", "mountain sky"]

FONT_PATH_AR = "Amiri-Regular.ttf"
FONT_PATH_EN = "Roboto-Regular.ttf"

reshaper = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})

# ================== [2] وظائف المساعدة ==================

def today_str(): return datetime.utcnow().strftime("%Y-%m-%d")

def mark_uploaded_today():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(today_str())

def process_text(t):
    try: return get_display(reshaper.reshape(t))[::-1]
    except: return t

def split_text_to_single_lines(text, max_chars=42):
    words = text.split()
    lines, current_line = [], []
    curr_len = 0
    for w in words:
        if curr_len + len(w) <= max_chars:
            current_line.append(w)
            curr_len += len(w) + 1
        else:
            lines.append(" ".join(current_line))
            current_line, curr_len = [w], len(w) + 1
    if current_line: lines.append(" ".join(current_line))
    return lines

def draw_frame(text_ar, text_en, font_ar, font_en):
    img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ar_ready = process_text(text_ar)
    en_ready = text_en[:65] + "..." if len(text_en) > 65 else text_en
    def draw_sh(pos, txt, font, col):
        x, y = pos
        for ox, oy in [(-3,-3), (3,3), (-3,3), (3,-3), (0,4)]:
            d.text((x+ox, y+oy), txt, font=font, fill="black", anchor="mm")
        d.text((x, y), txt, font=font, fill=col, anchor="mm")
    draw_sh((WIDTH/2, HEIGHT/2 - 60), ar_ready, font_ar, "white")
    draw_sh((WIDTH/2, HEIGHT/2 + 80), en_ready, font_en, "#D0D0D0")
    return np.array(img)

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    if not TOKEN_B64: raise Exception("TOKEN_BASE64 missing!")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

# ================== [3] المحرك والرفع ==================

def build_and_upload():
    print("🚀 بدء تحضير الفيديو والرفع...")
    reciter = random.choice(RECITERS)
    surah_id = random.randint(1, 114)
    
    # 1. جلب البيانات
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{surah_id}/{reciter}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{surah_id}/en.sahih").json()['data']
    s_name = res_ar['name']

    audio_clips, text_clips = [], []
    curr_t, gap = 0.0, 0.1
    f_ar, f_en = ImageFont.truetype(FONT_PATH_AR, 90), ImageFont.truetype(FONT_PATH_EN, 45)

    # 2. معالجة الآيات
    for i in range(len(res_ar['ayahs'])):
        a_ar, a_en = res_ar['ayahs'][i], res_en['ayahs'][i]
        f_path = f"a_{i}.mp3"
        with open(f_path, 'wb') as f: f.write(requests.get(a_ar['audio']).content)
        clip = mp.AudioFileClip(f_path)
        if curr_t + clip.duration > MAX_SHORT_DURATION: break
        
        lines = split_text_to_single_lines(a_ar['text'])
        n = len(lines)
        l_dur = clip.duration / n
        for j in range(n):
            img_arr = draw_frame(lines[j], a_en['text'][:50], f_ar, f_en) # تبسيط الإنجليزي للسطر
            t_clip = mp.ImageClip(img_arr).set_start(curr_t + j*l_dur).set_duration(l_dur)
            text_clips.append(t_clip)

        audio_clips.append(clip)
        curr_t += clip.duration + gap
        audio_clips.append(mp.AudioClip(lambda t: [0,0], duration=gap))

    # 3. دمج الخلفيات
    headers = {'Authorization': PEXELS_API_KEY}
    v_files = []
    for _ in range(3):
        v_res = requests.get(f'https://api.pexels.com/videos/search?query={random.choice(SAFE_QUERIES)}&orientation=portrait&per_page=5', headers=headers).json()
        v_url = v_res['videos'][0]['video_files'][0]['link']
        with open(f"bg_{_}.mp4", "wb") as f: f.write(requests.get(v_url).content)
        v_files.append(mp.VideoFileClip(f"bg_{_}.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT))
    
    bg_final = loop(mp.concatenate_videoclips(v_files, method="compose"), duration=curr_t).subclip(0, curr_t)
    final_audio = audio_fadeout(mp.concatenate_audioclips(audio_clips).subclip(0, curr_t), 1.0)
    
    # 4. الرندر
    video = mp.CompositeVideoClip([bg_final, mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=curr_t).set_opacity(0.3)] + text_clips).set_audio(final_audio)
    video.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", threads=4, logger=None)

    # 5. الرفع (الخطوة اللي كانت ناقصة تتنادى)
    print("📡 جاري الرفع لليوتيوب...")
    youtube = youtube_authenticate()
    body = {
        'snippet': {
            'title': f'تلاوة خاشعة - سورة {s_name} #shorts #quran',
            'description': f'سورة {s_name} بصوت {reciter}',
            'categoryId': '22'
        },
        'status': {'privacyStatus': 'public'}
    }
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final.mp4", chunksize=-1, resumable=True)).execute()
    
    # 6. التوثيق (عشان الـ GitHub Action يشتغل صح)
    mark_uploaded_today()
    print("✅ تم الرندر والرفع وتحديث السجل!")

if __name__ == "__main__":
    try:
        build_and_upload()
    except Exception as e:
        print(f"🔥 خطأ فادح: {e}")
        sys.exit(1)
