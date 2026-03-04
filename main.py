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

# ================== أدوات المعالجة ==================
configuration = {'delete_harakat': False, 'support_ligatures': True, 'delete_taatweel': True}
reshaper_new = arabic_reshaper.ArabicReshaper(configuration=configuration)

def clean_quran_text(text):
    unsupported_chars = r'[\u0610-\u0615\u06D6-\u06ED]'
    return re.sub(unsupported_chars, '', text)

def process_ar(t):
    try:
        t = clean_quran_text(t)
        reshaped = reshaper_new.reshape(t)
        return get_display(reshaped)[::-1]
    except: return t

def draw_text_with_shadow(draw, pos, text, font, fill_color, opacity=255):
    x, y = pos
    # رسم الظل
    for ox, oy in [(3,3), (-3,3), (3,-3), (-3,-3)]:
        draw.text((x+ox, y+oy), text, font=font, fill=(0,0,0, opacity), anchor="mm")
    # رسم النص الأساسي
    draw.text((x, y), text, font=font, fill=(*fill_color, opacity), anchor="mm")

# ================== المحرك الرئيسي ==================
def build_shorts_video():
    print("🚀 [1/6] بدء التجهيز...")
    reciter = random.choice(RECITERS_DATA)
    s_id = random.randint(78, 114)
    
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{reciter['api_id']}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    mp3_url = f"{reciter['base_url']}{s_id:03}.mp3"
    with open("temp_audio.mp3", 'wb') as f: f.write(requests.get(mp3_url).content)
    full_audio = mp.AudioFileClip("temp_audio.mp3")
    
    ayahs_data = []
    current_time = 0.0
    for i in range(len(res_ar['ayahs'])):
        dur = 6.5 # توقيت افتراضي للسكرول
        if current_time + dur > 58: break
        ayahs_data.append({"ar": res_ar['ayahs'][i]['text'], "en": res_en['ayahs'][i]['text'], "start": current_time, "end": current_time + dur})
        current_time += dur

    final_audio = full_audio.subclip(0, current_time)

    # 1. الخلفية (سوداء سادة عشان نتجنب أي تعارض قنوات)
    bg = mp.ColorClip(size=(WIDTH, HEIGHT), color=(15, 15, 15), duration=current_time)
    
    # 2. نظام الـ Scroll (معدل ليعيد RGB فقط)
    def make_scroll_frame(t):
        # بننشئ صورة بخلفية سوداء (RGB) مش شفافة عشان نتفادى الخطأ
        img = Image.new('RGB', (WIDTH, HEIGHT), (15, 15, 15))
        d = ImageDraw.Draw(img)
        f_ar = ImageFont.truetype(FONT_PATH_AR, 95)
        f_en = ImageFont.truetype(FONT_PATH_EN, 45)
        
        center_y = HEIGHT // 2 + 100
        for i, ayah in enumerate(ayahs_data):
            dist = abs(t - (ayah['start'] + 3.25))
            alpha = int(max(60, 255 - (dist * 45)))
            y_offset = center_y - (t * 180) + (i * 350)
            
            if -300 < y_offset < HEIGHT + 300:
                draw_text_with_shadow(d, (WIDTH/2, y_offset), process_ar(ayah['ar']), f_ar, (255,255,255), alpha)
                d.text((WIDTH/2, y_offset + 110), ayah['en'], font=f_en, fill=(200, 200, 200), anchor="mm")
        
        return np.array(img)

    scroll_clip = mp.VideoClip(make_scroll_frame, duration=current_time)

    # 3. العنوان الثابت (معدل ليكون RGB)
    def make_title_frame(t):
        img = Image.new('RGB', (WIDTH, HEIGHT), (0, 0, 0))
        d = ImageDraw.Draw(img)
        draw_text_with_shadow(d, (WIDTH/2, 280), process_ar(s_name), ImageFont.truetype(FONT_PATH_AR, 170), (255, 215, 0))
        draw_text_with_shadow(d, (WIDTH/2, 440), process_ar(reciter['name']), ImageFont.truetype(FONT_PATH_AR, 85), (255, 255, 255))
        return np.array(img)

    title_clip = mp.VideoClip(make_title_frame, duration=current_time)
    # جعل العنوان شفاف ودمجه
    title_mask = mp.VideoClip(lambda t: make_title_frame(t)[:,:,0]/255.0, duration=current_time, ismask=True)
    title_clip = title_clip.set_mask(title_mask)

    # 4. الشريط المتحرك (Waveform)
    def make_wave_frame(t):
        img = Image.new('RGB', (WIDTH, 160), (0,0,0))
        d = ImageDraw.Draw(img)
        for i in range(50):
            h = int(abs(math.sin(t*8 + i*0.5)*55)) + 15
            x = (WIDTH // 2) - (50 * 10) + (i * 20)
            d.rounded_rectangle([x, 80-h, x+6, 80+h], radius=3, fill=(255,255,255))
        return np.array(img)

    wave_mask = mp.VideoClip(lambda t: make_wave_frame(t)[:,:,0]/255.0, duration=current_time, ismask=True)
    wave_clip = mp.VideoClip(make_wave_frame, duration=current_time).set_mask(wave_mask).set_position(('center', HEIGHT-400))

    # التجميع النهائي
    final = mp.CompositeVideoClip([bg, scroll_clip, title_clip, wave_clip]).set_audio(final_audio)
    
    print("⏳ [6/6] جاري الرندر...")
    final.write_videofile("final_shorts.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="8000k", preset="ultrafast", logger=None)
    
    # الرفع
    youtube = youtube_authenticate()
    body = {
        'snippet': {'title': f'تلاوة خاشعة - {s_name} بصوت {reciter["name"]}', 'description': 'Quran Shorts', 'categoryId': '22'},
        'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
    }
    youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload("final_shorts.mp4", chunksize=-1, resumable=True)).execute()
    print("✅ تم الرفع بنجاح!")

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

if __name__ == "__main__":
    try:
        build_shorts_video()
    except Exception as e:
        print("🔥 خطأ:", e)
        sys.exit(1)
