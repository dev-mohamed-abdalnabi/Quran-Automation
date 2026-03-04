import os, requests, random, json, base64, sys, math, re
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

# ================== إعدادات الأبعاد والشكل ==================
WIDTH = 1080
HEIGHT = 1920
FONT_PATH_AR = "Thuluth.ttf"
FONT_PATH_EN = "Roboto-Regular.ttf"

# ================== القراء والعناوين المتغيرة ==================
RECITERS_DATA = [
    {"api_id": "ar.alafasy", "name": "مشاري العفاسي", "base_url": "https://server8.mp3quran.net/afs/"},
    {"api_id": "ar.mahermuaiqly", "name": "ماهر المعيقلي", "base_url": "https://server12.mp3quran.net/maher/"},
    {"api_id": "ar.abdurrahmaansudais", "name": "عبدالرحمن السديس", "base_url": "https://server11.mp3quran.net/sds/"}
]

YOUTUBE_TITLES = [
    "تلاوة خاشعة لراحة البال - سورة {surah} بصوت {reciter} ✨",
    "تلاوة هادئة تأخذك لعالم آخر 🌸 {surah} | {reciter}",
    "من أجمل تلاوات {reciter} ❤️ {surah}"
]

YOUTUBE_DESCRIPTIONS = [
    "تلاوة خاشعة ومؤثرة من سورة {surah} بصوت الشيخ {reciter}. \n\n#قرآن #islam #تلاوات #shorts"
]

# ================== أدوات المعالجة ==================

# إعداد الـ Reshaper عشان يتعامل مع التشكيل بشكل أفضل ويمنع المربعات
configuration = {
    'delete_harakat': False, # هنخلي التشكيل الأساسي
    'support_ligatures': True,
    'delete_taatweel': True
}
reshaper_new = arabic_reshaper.ArabicReshaper(configuration=configuration)

def clean_quran_text(text):
    # الفلتر ده بيشيل الرموز القرآنية الخاصة اللي الخطوط العادية مش بتفهمها وبتطلع مربعات
    # زي علامات السجدة، وعلامات الحزب، وبعض زخارف الآيات
    unsupported_chars = r'[\u0610-\u0615\u06D6-\u06ED]'
    cleaned = re.sub(unsupported_chars, '', text)
    return cleaned

def process_ar(t):
    try:
        t = clean_quran_text(t)
        reshaped = reshaper_new.reshape(t)
        return get_display(reshaped)[::-1]
    except:
        return t

def draw_text_with_shadow(draw, pos, text, font, fill_color, opacity=255):
    x, y = pos
    shadow_rgba = (0, 0, 0, int(opacity * 0.8))
    # التأكد من أن fill_color بصيغة RGBA
    if isinstance(fill_color, str):
        if fill_color.lower() == "white": fill_rgba = (255, 255, 255, opacity)
        elif fill_color.lower() == "gold": fill_rgba = (255, 215, 0, opacity)
        else: fill_rgba = (255, 255, 255, opacity)
    else:
        fill_rgba = (*fill_color[:3], opacity)

    # رسم الظل بشكل احترافي (أربع اتجاهات لعمق النص)
    offsets = [(3,3), (-3,3), (3,-3), (-3,-3)]
    for ox, oy in offsets:
        draw.text((x+ox, y+oy), text, font=font, fill=shadow_rgba, anchor="mm")
    draw.text((x, y), text, font=font, fill=fill_rgba, anchor="mm")

# ================== المحرك الرئيسي ==================
def build_shorts_video():
    print("🚀 بدء التجهيز...")
    reciter = random.choice(RECITERS_DATA)
    s_id = random.randint(78, 114)
    
    # جلب البيانات
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{reciter['api_id']}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    # تحميل الصوت
    mp3_url = f"{reciter['base_url']}{s_id:03}.mp3"
    with open("temp_audio.mp3", 'wb') as f: f.write(requests.get(mp3_url).content)
    full_audio = mp.AudioFileClip("temp_audio.mp3")
    
    ayahs_data = []
    current_time = 0.0
    # حساب توقيت تقريبي أو استخدم منطقك السابق للقياس الدقيق
    for i in range(len(res_ar['ayahs'])):
        dur = 6.5 
        if current_time + dur > 58: break
        ayahs_data.append({
            "ar": res_ar['ayahs'][i]['text'],
            "en": res_en['ayahs'][i]['text'],
            "start": current_time,
            "end": current_time + dur
        })
        current_time += dur

    final_audio = full_audio.subclip(0, current_time)

    # 1. الخلفية (ممكن تغيرها لـ Pexels لو عايز)
    bg = mp.ColorClip(size=(WIDTH, HEIGHT), color=(10, 10, 10), duration=current_time)
    
    # 2. نظام الـ Scroll (الحركة من أسفل لأعلى)
    def make_scroll_frame(t):
        img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        f_ar = ImageFont.truetype(FONT_PATH_AR, 95)
        f_en = ImageFont.truetype(FONT_PATH_EN, 45)
        
        center_y = HEIGHT // 2 + 100
        for i, ayah in enumerate(ayahs_data):
            # الآية اللي شغالة دلوقتي تكون زاهية، اللي فوق وتحت شفافين
            dist = abs(t - (ayah['start'] + 3.25)) # البعد عن منتصف وقت الآية
            alpha = int(max(50, 255 - (dist * 40))) 
            
            # حركة السكرول
            y_offset = center_y - (t * 180) + (i * 350)
            
            if -300 < y_offset < HEIGHT + 300:
                draw_text_with_shadow(d, (WIDTH/2, y_offset), process_ar(ayah['ar']), f_ar, "white", alpha)
                # النص الإنجليزي
                en_alpha = int(alpha * 0.7)
                d.text((WIDTH/2, y_offset + 110), ayah['en'], font=f_en, fill=(220, 220, 220, en_alpha), anchor="mm")
        
        return np.array(img)

    scroll_clip = mp.VideoClip(make_scroll_frame, duration=current_time)

    # 3. العنوان الثابت الفخم (سورة كذا وتحتها القارئ)
    t_img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(t_img)
    f_title_big = ImageFont.truetype(FONT_PATH_AR, 170)
    f_title_small = ImageFont.truetype(FONT_PATH_AR, 85)
    
    draw_text_with_shadow(d_t, (WIDTH/2, 280), process_ar(s_name), f_title_big, "gold")
    draw_text_with_shadow(d_t, (WIDTH/2, 440), process_ar(reciter['name']), f_title_small, "white")
    title_clip = mp.ImageClip(np.array(t_img)).set_duration(current_time)

    # 4. الشريط المتحرك (Waveform) في الأسفل
    def make_wave_frame(t):
        img = Image.new('RGB', (WIDTH, 160), (0,0,0))
        d = ImageDraw.Draw(img)
        num_bars = 60
        for i in range(num_bars):
            # حركة عشوائية متزنة للموجات
            h = int(abs(math.sin(t*8 + i*0.5)*55)) + 15
            x = (WIDTH // 2) - (num_bars * 10) + (i * 20)
            d.rounded_rectangle([x, 80-h, x+6, 80+h], radius=3, fill="white")
        return np.array(img)

    wave_mask = mp.VideoClip(lambda t: make_wave_frame(t)[:,:,0]/255.0, duration=current_time, ismask=True)
    wave_clip = mp.VideoClip(make_wave_frame, duration=current_time).set_mask(wave_mask).set_position(('center', HEIGHT-400))

    # التجميع
    final = mp.CompositeVideoClip([bg, scroll_clip, title_clip, wave_clip]).set_audio(final_audio)
    
    print("⏳ جاري الرندر...")
    final.write_videofile("final_shorts.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast")
    
    # الرفع
    youtube = youtube_authenticate()
    final_title = random.choice(YOUTUBE_TITLES).format(surah=s_name, reciter=reciter['name'])
    final_desc = random.choice(YOUTUBE_DESCRIPTIONS).format(surah=s_name, reciter=reciter['name'])
    body = {
        'snippet': {'title': final_title, 'description': final_desc, 'categoryId': '22'},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final_shorts.mp4", chunksize=-1, resumable=True)).execute()
    print("✅ تم الرفع!")

if __name__ == "__main__":
    build_shorts_video()
