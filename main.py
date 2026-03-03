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

# ================== الإعدادات العامة ==================
WIDTH = 1080
HEIGHT = 1920
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

# قائمة القراء بجودة عالية
RECITERS = [
    'ar.alafasy', 'ar.abdulbasitmurattal', 'ar.husary', 
    'ar.mahermuaiqly', 'ar.sudais', 'ar.ahmedajamy'
]

# خلفيات طبيعية هادئة (خالية من البشر والحيوانات)
SAFE_QUERIES = ["sky clouds", "ocean waves blue", "forest nature aerial", "stars galaxy night"]

FONT_PATH_AR = "Amiri-Regular.ttf" # خط أميري ممتاز للتشكيل
FONT_PATH_EN = "Roboto-Regular.ttf"

# إعداد معالج النصوص العربية (للمحافظة على التشكيل)
reshaper = arabic_reshaper.ArabicReshaper(configuration={
    'delete_harakat': False, 
    'support_ligatures': True,
    'use_unshaped_instead_of_isolated': True
})

def process_text(t):
    try: return get_display(reshaper.reshape(t))
    except: return t

def split_text_into_single_lines(text, words_per_line=6):
    """تقسيم النص إلى أجزاء، كل جزء سطر واحد فقط"""
    words = text.split()
    return [" ".join(words[i:i + words_per_line]) for i in range(0, len(words), words_per_line)]

def draw_single_line(text_ar, text_en, font_ar, font_en):
    """رسم سطر واحد فقط في وسط الشاشة"""
    img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # تنسيق العربي (سطر واحد)
    ar_ready = process_text(text_ar)
    # تنسيق الإنجليزي (سطر واحد)
    en_ready = text_en[:60] + "..." if len(text_en) > 60 else text_en

    # الظلال لزيادة الوضوح
    def draw_w_shadow(pos, txt, font, color):
        x, y = pos
        for ox, oy in [(-2,-2), (2,2), (-2,2), (2,-2)]:
            d.text((x+ox, y+oy), txt, font=font, fill="black", anchor="mm")
        d.text((x, y), txt, font=font, fill=color, anchor="mm")

    draw_w_shadow((WIDTH/2, HEIGHT/2 - 50), ar_ready, font_ar, "white")
    draw_w_shadow((WIDTH/2, HEIGHT/2 + 80), en_ready, font_en, "#E0E0E0")
    
    return np.array(img)

def build_video():
    print("🎬 بدء التجهيز...")
    reciter = random.choice(RECITERS)
    surah_num = random.randint(1, 114)
    
    # جلب البيانات
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{surah_num}/{reciter}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{surah_num}/en.sahih").json()['data']
    s_name = res_ar['name']

    final_audio_clips = []
    text_clips = []
    current_time = 0.0
    gap = 0.1 # فاصل زمني صغير جداً لمنع التداخل والتقطيع

    # الخطوط
    f_ar = ImageFont.truetype(FONT_PATH_AR, 85)
    f_en = ImageFont.truetype(FONT_PATH_EN, 40)
    f_title = ImageFont.truetype(FONT_PATH_AR, 120)

    for i in range(len(res_ar['ayahs'])):
        a_ar = res_ar['ayahs'][i]
        a_en = res_en['ayahs'][i]
        
        # تحميل الصوت بجودة عالية
        f_name = f"a_{i}.mp3"
        with open(f_name, "wb") as f: f.write(requests.get(a_ar['audio']).content)
        
        a_clip = mp.AudioFileClip(f_name)
        duration = a_clip.duration
        
        # تقسيم النص لسطور
        ar_lines = split_text_into_single_lines(a_ar['text'])
        en_lines = split_text_into_single_lines(a_en['text']) # تقسيم تقريبي للإنجليزي أيضاً
        
        num_splits = len(ar_lines)
        time_per_line = duration / num_splits
        
        for j in range(num_splits):
            line_start = current_time + (j * time_per_line)
            line_end = line_start + time_per_line
            
            # لضمان عدم تجاوز نهاية مقطع الصوت
            line_end = min(line_end, current_time + duration)
            
            txt_img = draw_single_line(ar_lines[j], en_lines[min(j, len(en_lines)-1)], f_ar, f_en)
            t_clip = mp.ImageClip(txt_img).set_start(line_start).set_end(line_end).set_duration(line_end-line_start)
            text_clips.append(t_clip)

        final_audio_clips.append(a_clip)
        # إضافة صمت خفيف جداً بين الآيات
        if i < len(res_ar['ayahs']) - 1:
            final_audio_clips.append(mp.AudioClip(lambda t: [0,0], duration=gap))
            current_time += duration + gap
        else:
            current_time += duration

        if current_time > 58: break

    # دمج الصوت
    full_audio = mp.concatenate_audioclips(final_audio_clips)
    if full_audio.duration > 59:
        full_audio = full_audio.subclip(0, 59)
        full_audio = audio_fadeout(full_audio, 1.5)

    v_dur = full_audio.duration

    # خلفية (Pexels)
    headers = {'Authorization': PEXELS_API_KEY}
    bg_q = random.choice(SAFE_QUERIES)
    v_data = requests.get(f'https://api.pexels.com/videos/search?query={bg_q}&orientation=portrait&per_page=10', headers=headers).json()
    v_url = random.choice(v_data['videos'])['video_files'][0]['link']
    with open("bg.mp4", "wb") as f: f.write(requests.get(v_url).content)

    bg = mp.VideoFileClip("bg.mp4").resize(height=HEIGHT)
    bg = bg.crop(x1=bg.w/2-WIDTH/2, y1=0, width=WIDTH, height=HEIGHT)
    bg = loop(bg, duration=v_dur)
    
    overlay = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=v_dur).set_opacity(0.3)

    # اسم السورة في الأعلى
    title_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(title_img)
    # رسم اسم السورة بظل
    name_reshaped = process_text(s_name)
    d_t.text((WIDTH/2, 250), name_reshaped, font=f_title, fill="white", anchor="mm", stroke_width=2, stroke_fill="black")
    title_clip = mp.ImageClip(np.array(title_img)).set_duration(v_dur)

    # تجميع الكل
    video = mp.CompositeVideoClip([bg, overlay, title_clip] + text_clips).set_audio(full_audio)

    print("🚀 رندر نهائي...")
    video.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="12000k", preset="ultrafast", threads=4, logger=None)
    
    # رفع الفيديو ليوتيوب (نفس كود الرفع السابق)
    # ... (يستكمل كود الرفع الخاص بك هنا)
    print(f"✅ تم الانتهاء! القارئ: {reciter}")

if __name__ == "__main__":
    build_video()
