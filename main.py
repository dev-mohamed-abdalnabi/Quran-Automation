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

# ================== [1] الإعدادات الأساسية ==================
WIDTH, HEIGHT = 1080, 1920
MAX_SHORT_DURATION = 58.0  # أمان عشان ميتخطاش الدقيقة
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

# قراء أصواتهم نقية وقليلة المشاكل في الحقوق للشورتس
RECITERS = ['ar.alafasy', 'ar.husary', 'ar.mahermuaiqly', 'ar.ahmedajamy']
SAFE_QUERIES = ["nature drone", "ocean sea waves", "galaxy stars", "mountain sky", "forest aerial"]

FONT_PATH_AR = "Amiri-Regular.ttf"
FONT_PATH_EN = "Roboto-Regular.ttf"

reshaper = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})

# ================== [2] دوال المعالجة ==================

def process_text(t):
    """تعديل اتجاه النص العربي عشان يظهر معدول"""
    try: return get_display(reshaper.reshape(t))[::-1]
    except: return t

def split_text_to_single_lines(text, max_chars=42):
    """تقسيم الآية لسطر واحد فقط"""
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

# ================== [3] المحرك الرئيسي ==================

def build_video():
    print("🚀 جاري تحضير فيديو شورتس احترافي...")
    reciter = random.choice(RECITERS)
    surah_id = random.randint(1, 114)
    
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{surah_id}/{reciter}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{surah_id}/en.sahih").json()['data']
    s_name = res_ar['name']

    audio_clips, text_clips = [], []
    curr_t, gap = 0.0, 0.1
    f_ar, f_en = ImageFont.truetype(FONT_PATH_AR, 90), ImageFont.truetype(FONT_PATH_EN, 45)

    for i in range(len(res_ar['ayahs'])):
        a_ar, a_en = res_ar['ayahs'][i], res_en['ayahs'][i]
        f_path = f"a_{i}.mp3"
        with open(f_path, 'wb') as f: f.write(requests.get(a_ar['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        if curr_t + clip.duration > MAX_SHORT_DURATION: break
        
        lines = split_text_to_single_lines(a_ar['text'])
        en_words = a_en['text'].split()
        n = len(lines)
        en_lines = [" ".join(en_words[j*len(en_words)//n : (j+1)*len(en_words)//n]) for j in range(n)]
        
        l_dur = clip.duration / n
        for j in range(n):
            img_arr = draw_frame(lines[j], en_lines[j], f_ar, f_en)
            t_clip = mp.ImageClip(img_arr).set_start(curr_t + j*l_dur).set_duration(l_dur)
            text_clips.append(t_clip)

        audio_clips.append(clip)
        curr_t += clip.duration + gap
        audio_clips.append(mp.AudioClip(lambda t: [0,0], duration=gap))

    # --- معالجة الخلفية (3 فيديوهات مختلفة لمنع الملل) ---
    print("🎬 جاري جلب 3 خلفيات متنوعة...")
    headers = {'Authorization': PEXELS_API_KEY}
    bg_video_files = []
    for _ in range(3):
        v_res = requests.get(f'https://api.pexels.com/videos/search?query={random.choice(SAFE_QUERIES)}&orientation=portrait&per_page=15', headers=headers).json()
        v_url = random.choice(v_res['videos'])['video_files'][0]['link']
        v_name = f"bg_{_}.mp4"
        with open(v_name, "wb") as f: f.write(requests.get(v_url).content)
        bg_video_files.append(mp.VideoFileClip(v_name).resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT))

    bg_combined = mp.concatenate_videoclips(bg_video_files, method="compose")
    bg_final = loop(bg_combined, duration=curr_t).subclip(0, curr_t)
    
    # دمج الصوت والرندر
    final_audio = mp.concatenate_audioclips(audio_clips).subclip(0, curr_t)
    final_audio = audio_fadeout(final_audio, 1.0)
    
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=curr_t).set_opacity(0.3)
    
    video = mp.CompositeVideoClip([bg_final, dark] + text_clips).set_audio(final_audio)
    
    print(f"⏳ رندر نهائي (المدة: {curr_t:.2f} ثانية)...")
    video.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", threads=4, logger=None)
    print("✅ تم بنجاح! الفيديو جاهز للرفع وآمن تماماً.")

if __name__ == "__main__":
    build_video()
