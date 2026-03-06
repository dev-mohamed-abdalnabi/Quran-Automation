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

# ================== إعدادات الأبعاد والجودة ==================
WIDTH, HEIGHT = 1080, 1920
RECITER_IDS = ['ar.alhusary', 'ar.abdulbasitmurattal', 'ar.minshawi', 'ar.mustafaismail']

def process_ar(t):
    reshaper = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})
    try: return get_display(reshaper.reshape(t))[::-1]
    except: return t

def safe_wrap(text, width):
    words = text.split()
    lines = []
    curr = []
    length = 0
    for w in words:
        if length + len(w) <= width:
            curr.append(w); length += len(w) + 1
        else:
            if curr: lines.append(" ".join(curr))
            curr = [w]; length = len(w) + 1
    if curr: lines.append(" ".join(curr))
    return lines

def build_shorts_video():
    print("🚀 [1/4] جلب البيانات والمعالجة الصوتية...")
    
    s_id = random.randint(1, 114)
    reciter = random.choice(RECITER_IDS)
    
    # جلب الداتا
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/quran-uthmani").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    audio_clips = []
    text_parts_ar = []
    text_parts_en = []
    total_dur = 0

    for i, ayah in enumerate(res_ar['ayahs']):
        txt_ar = ayah['text']
        txt_en = res_en['ayahs'][i]['text']
        
        # إزالة البسملة من أول آية (إلا الفاتحة)
        if s_id != 1 and i == 0:
            basmala = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
            if txt_ar.startswith(basmala):
                txt_ar = txt_ar.replace(basmala, "").strip()
        
        # تحميل الصوت
        a_url = f"https://cdn.islamic.network/quran/audio/128/{reciter}/{ayah['number']}.mp3"
        f_path = f"t_{i}.mp3"
        with open(f_path, 'wb') as f: f.write(requests.get(a_url).content)
        
        # معالجة الصوت لإزالة "الفرقعة" باستخدام Fade In/Out خفيف جداً
        clip = mp.AudioFileClip(f_path).audio_fadein(0.05).audio_fadeout(0.05)
        
        if total_dur + clip.duration > 57: # نضمن إننا مخرجناش عن الدقيقة ولا قطعنا آية
            break
            
        audio_clips.append(clip)
        text_parts_ar.append(txt_ar)
        text_parts_en.append(txt_en)
        total_dur += clip.duration

    # دمج الصوت بشكل احترافي (Seamless)
    final_audio = mp.concatenate_audioclips(audio_clips)
    dur = final_audio.duration

    print("🎬 [2/4] اختيار فيديو خلفية آمن تماماً...")
    # فلترة صارمة: مجرات، سحاب، صحراء، نجوم
    safe_queries = ['galaxy', 'starry sky', 'desert dunes', 'clouds timelapse']
    q = random.choice(safe_queries)
    headers = {'Authorization': os.environ.get("PEXELS_API_KEY")}
    v_res = requests.get(f'https://api.pexels.com/videos/search?query={q}&orientation=portrait&per_page=10', headers=headers).json()
    v_url = random.choice(v_res['videos'])['video_files'][0]['link']
    with open("bg.mp4", "wb") as f: f.write(requests.get(v_url).content)

    bg = loop(mp.VideoFileClip("bg.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT), duration=dur)
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=dur).set_opacity(0.5)

    # المونتاج والنص
    font_ar = ImageFont.truetype("Amiri-Regular.ttf", 90)
    font_en = ImageFont.truetype("Roboto-Regular.ttf", 45)
    
    starts = [0.0]
    for c in audio_clips: starts.append(starts[-1] + c.duration)

    text_clips = []
    for i in range(len(audio_clips)):
        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        
        ar_lines = safe_wrap(text_parts_ar[i], 35)
        en_lines = safe_wrap(text_parts_en[i], 45)
        
        y = HEIGHT/2 - 150
        for line in ar_lines:
            d.text((WIDTH/2, y), process_ar(line), font=font_ar, fill="white", anchor="mm", stroke_width=2, stroke_fill="black")
            y += 120
        y += 50
        for line in en_lines:
            d.text((WIDTH/2, y), line, font=font_en, fill="#F0F0F0", anchor="mm", stroke_width=1, stroke_fill="black")
            y += 60
            
        t_clip = mp.ImageClip(np.array(img)).set_start(starts[i]).set_end(starts[i+1])
        text_clips.append(t_clip)

    # إضافة اسم السورة
    title_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(title_img).text((WIDTH/2, 200), process_ar(f"سورة {s_name}"), font=font_ar, fill="white", anchor="mm", stroke_width=3, stroke_fill="black")
    title_clip = mp.ImageClip(np.array(title_img)).set_duration(dur)

    final = mp.CompositeVideoClip([bg, dark, title_clip] + text_clips).set_audio(final_audio)
    
    print("⏳ [3/4] رندر سريع...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast", logger=None)
    print("✅ جاهز للرفع!")

if __name__ == "__main__":
    build_shorts_video()
