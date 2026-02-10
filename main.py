import os, requests, random, json, base64, textwrap, sys
from datetime import datetime
import numpy as np
import moviepy.editor as mp
from moviepy.video.fx.all import loop 
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageFont, ImageDraw, ImageFilter
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ================== إعدادات الأبعاد ==================
BOX_X = 50
BOX_Y = 280
BOX_W = 620
BOX_H = 750
BOX_OPACITY = 160 

# ================== سجل يومي ==================
LOG_FILE = "daily_log.txt"

def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def is_uploaded_today():
    if not os.path.exists(LOG_FILE):
        return False
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        return f.read().strip() == today_str()

def mark_uploaded_today():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(today_str())

# ================== الإعدادات ==================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
AUDIO_EDITION = 'ar.alafasy'
FONT_PATH = "ArabicFont.ttf"

def process_ar(t):
    try:
        reshaped = arabic_reshaper.reshape(t)
        bidi_text = get_display(reshaped)
        return bidi_text[::-1]
    except:
        return t

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

# دالة مساعدة لرسم النص بحدود (Stroke) وظل
def draw_text_with_style(draw, text, x, y, font, text_color="white", stroke_color="#D4AF37", shadow_color="black"):
    # 1. رسم الظل (Shadow)
    draw.text((x + 4, y + 4), text, font=font, fill=shadow_color, anchor="mm")
    
    # 2. رسم الحدود (Stroke/Outline) - بنرسم النص 4 مرات حوالين المركز
    stroke_width = 2
    for off_x in range(-stroke_width, stroke_width+1):
        for off_y in range(-stroke_width, stroke_width+1):
            draw.text((x + off_x, y + off_y), text, font=font, fill=stroke_color, anchor="mm")
            
    # 3. رسم النص الأصلي في النص
    draw.text((x, y), text, font=font, fill=text_color, anchor="mm")

def build_shorts_video():
    print("🚀 [1/4] تحضير الموارد...")

    # --- اختيار السورة ---
    s_id = random.randint(1, 114)
    res = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    s_name = res['name']
    all_ayahs = res['ayahs']

    # --- تجميع الصوت ---
    audio_clips = []
    text_parts = []
    current_duration = 0
    TARGET_DURATION = 40 

    for i, a in enumerate(all_ayahs):
        f_path = f"temp_{i}.mp3"
        with open(f_path, 'wb') as f:
            f.write(requests.get(a['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        audio_clips.append(clip)
        text_parts.append(a['text'])
        current_duration += clip.duration

        if current_duration >= TARGET_DURATION:
            if current_duration > 59: 
                audio_clips.pop()
                text_parts.pop()
            break
    
    final_audio = mp.concatenate_audioclips(audio_clips)
    dur = min(59, final_audio.duration)
    final_audio = final_audio.subclip(0, dur)
    full_text = " ۞ ".join(text_parts)

    # --- اختيار الخلفية السينمائية ---
    print("🎨 جاري اختيار خلفية سينمائية...")
    headers = {'Authorization': PEXELS_API_KEY}
    
    # كلمات بحث قوية جداً لجذب الانتباه
    cinematic_queries = [
        "cinematic nature", "drone shot", "aerial view", "slow motion water", 
        "epic clouds", "galaxy timelapse", "mountain peak", "desert sunset 4k",
        "ocean waves slow motion", "forest sunlight", "stars night sky", "islamic geometric"
    ]
    query = random.choice(cinematic_queries)
    page_num = random.randint(1, 10) # وسعنا نطاق البحث
    
    print(f"🔎 البحث عن: {query}")
    
    try:
        v_res = requests.get(
            f'https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=20&page={page_num}',
            headers=headers
        ).json()

        videos_list = v_res.get('videos', [])
        # نفضل الفيديوهات اللي جودتها عالية ومدتها كويسة
        best_videos = [v for v in videos_list if v['duration'] >= 10 and v['width'] >= 1080]
        
        selection_pool = best_videos if best_videos else videos_list
        if not selection_pool: raise Exception("No videos")

        chosen_video = random.choice(selection_pool)
        v_url = chosen_video['video_files'][0]['link']
        
        # اختيار رابط الجودة العالية
        for file in chosen_video['video_files']:
             # بنحاول نجيب HD عشان الصورة تبقى كريستال
            if file['height'] >= 1280:
                v_url = file['link']
                break

    except:
        # Fallback
        v_res = requests.get(
            'https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15',
            headers=headers
        ).json()
        v_url = random.choice(v_res['videos'])['video_files'][0]['link']

    with open("bg_v.mp4", "wb") as f:
        f.write(requests.get(v_url).content)

    print(f"⚙️ [2/4] المونتاج والإخراج الفني...")

    # 1. الخلفية
    bg_source = mp.VideoFileClip("bg_v.mp4").resize(height=1280).crop(x1=0, y1=0, width=720, height=1280)
    bg = loop(bg_source, duration=dur)
    
    # زيادة التغميق سنة بسيطة (0.5) عشان العنوان الجديد ينور
    dark = mp.ColorClip(size=(720, 1280), color=(0,0,0), duration=dur).set_opacity(0.5)

    # 2. المربع الشفاف (زي ما هو ممتاز)
    box_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    box_draw = ImageDraw.Draw(box_canvas)
    box_draw.rounded_rectangle(
        [BOX_X, BOX_Y, BOX_X + BOX_W, BOX_Y + BOX_H], 
        radius=30, 
        fill=(0,0,0,BOX_OPACITY)
    )
    box_bg_clip = mp.ImageClip(np.array(box_canvas)).set_duration(dur)

    # 3. النص القرآني
    lines = textwrap.wrap(full_text, width=28)
    line_h = 95
    text_img_h = (len(lines) + 2) * line_h
    
    txt_img = Image.new('RGBA', (BOX_W, text_img_h), (0, 0, 0, 0))
    d_t = ImageDraw.Draw(txt_img)
    font_a = ImageFont.truetype(FONT_PATH, 48)

    for i, line in enumerate(lines):
        d_t.text((BOX_W/2, i*line_h + 80), process_ar(line), font=font_a, fill="white", anchor="mm")

    raw_txt_clip = mp.ImageClip(np.array(txt_img)).set_duration(dur)

    # 4. حركة السكرول
    def scroll_func(t):
        progress = t / dur
        start_pos = BOX_H
        end_pos = -text_img_h
        current_y = start_pos - (progress * (start_pos - end_pos))
        return ('center', current_y)

    moving_txt = raw_txt_clip.set_position(scroll_func)
    text_container = mp.CompositeVideoClip([moving_txt], size=(BOX_W, BOX_H)).set_position((BOX_X, BOX_Y))

    # 5. العنوان الجديد (التغيير الكبير هنا)
    title_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    title_draw = ImageDraw.Draw(title_canvas)
    font_s = ImageFont.truetype(FONT_PATH, 90) # كبرنا الخط شوية لـ 90
    
    # استخدام دالة الرسم الجديدة (أبيض بحدود ذهبية وظل)
    draw_text_with_style(
        title_draw, 
        process_ar(s_name), 
        360,           # x (منتصف الشاشة)
        BOX_Y - 90,    # y (فوق المربع بمسافة كويسة)
        font_s,
        text_color="white",      # لون النص
        stroke_color="#D4AF37",  # لون الحدود (ذهبي)
        shadow_color="#000000"   # لون الظل (أسود)
    )
    
    title_clip = mp.ImageClip(np.array(title_canvas)).set_duration(dur)

    # الترتيب النهائي
    final = mp.CompositeVideoClip([bg, dark, box_bg_clip, text_container, title_clip]).set_audio(final_audio)

    print("⏳ [3/4] جاري الرندر بجودة عالية...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="5500k", logger=None, threads=4)

    print("📡 [4/4] جاري الرفع...")
    youtube = youtube_authenticate()

    body = {
        'snippet': {
            'title': f'تلاوة تأسر القلوب - {s_name} 🎧 #shorts #قرآن',
            'description': f'سورة {s_name} بصوت مشاري العفاسي.\nاستمع بقلبك.\n\n#quran #islam #recitation #راحة_نفسية',
            'categoryId': '22'
        },
        'status': {'privacyStatus': 'public'}
    }

    media = MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()

    print(f"✅ تم النشر: {s_name}")

if __name__ == "__main__":
    event_name = os.environ.get('GITHUB_EVENT_NAME')

    if is_uploaded_today():
        if event_name == 'workflow_dispatch':
            print("⚠️ تشغيل يدوي للتجربة...")
        else:
            print("✅ تم النشر اليوم. إغلاق.")
            sys.exit(0)
    
    try:
        build_shorts_video()
        mark_uploaded_today()
        print("📝 تم.")
    except Exception as e:
        print("🔥 خطأ:", e)
        sys.exit(1)
