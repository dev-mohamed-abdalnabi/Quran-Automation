import os, requests, random, json, base64, textwrap, sys
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

# ================== الإعدادات والخطوط ==================
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
AUDIO_EDITION = 'ar.alafasy'

FONT_PATH_AR = "Amiri-Regular.ttf" 
FONT_PATH_EN = "Roboto-Regular.ttf"

def download_fonts():
    """تحميل الخطوط بروابط مباشرة وصحيحة 100% من سيرفرات جوجل"""
    fonts = {
        # روابط Raw مباشرة لتجنب خطأ 404
        FONT_PATH_AR: "https://raw.githubusercontent.com/google/fonts/main/ofl/amiri/Amiri-Regular.ttf",
        FONT_PATH_EN: "https://raw.githubusercontent.com/google/fonts/main/apache/roboto/static/Roboto-Regular.ttf"
    }
    for font_name, url in fonts.items():
        if not os.path.exists(font_name):
            print(f"⬇️ جاري تحميل الخط: {font_name} ...")
            try:
                response = requests.get(url, timeout=15)
                response.raise_for_status()
                with open(font_name, 'wb') as f:
                    f.write(response.content)
                print(f"✅ تم تحميل {font_name} بنجاح!")
            except Exception as e:
                print(f"🔥 خطأ في تحميل {font_name}: {e}")
                
    # التأكد من وجود الخطوط لمنع ظهور المربعات وخطأ latin-1
    if not os.path.exists(FONT_PATH_AR) or not os.path.exists(FONT_PATH_EN):
        print("❌ فشل تحميل الخطوط. سيتم إيقاف السكربت لتجنب خروج فيديو بمربعات غير مفهومة.")
        sys.exit(1)

def process_ar(t):
    try:
        reshaped = arabic_reshaper.reshape(t)
        bidi_text = get_display(reshaped)
        return bidi_text
    except:
        return t

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🚀 [1/4] تحضير الموارد...")
    
    # تحميل الخطوط أولاً
    download_fonts()

    # --- اختيار السورة ---
    s_id = random.randint(1, 114)
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    
    s_name = res_ar['name']
    all_ayahs_ar = res_ar['ayahs']
    all_ayahs_en = res_en['ayahs']

    # --- اختيار ستايل الفيديو ---
    VIDEO_STYLE = random.choice(['scrolling', 'static_sync'])
    print(f"🎨 الستايل المختار لهذا الفيديو: {VIDEO_STYLE}")

    # --- تجميع الصوت ---
    audio_clips = []
    text_parts_ar = []
    text_parts_en = []
    current_duration = 0
    TARGET_DURATION = 50 

    for i, (a_ar, a_en) in enumerate(zip(all_ayahs_ar, all_ayahs_en)):
        f_path = f"temp_{i}.mp3"
        with open(f_path, 'wb') as f:
            f.write(requests.get(a_ar['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        audio_clips.append(clip)
        text_parts_ar.append(a_ar['text'])
        text_parts_en.append(a_en['text'])
        current_duration += clip.duration

        if current_duration >= TARGET_DURATION:
            if current_duration > 59: 
                audio_clips.pop()
                text_parts_ar.pop()
                text_parts_en.pop()
            break
    
    # دمج الصوت مع تداخل لمنع التقطيع
    overlap_sec = 0.15
    starts = [0]
    for clip in audio_clips[:-1]:
        starts.append(max(0, starts[-1] + clip.duration - overlap_sec))
        
    for i in range(len(audio_clips)):
        audio_clips[i] = audio_clips[i].set_start(starts[i])
        
    final_audio = mp.CompositeAudioClip(audio_clips)
    dur = min(59, final_audio.duration)
    final_audio = final_audio.subclip(0, dur)
    
    full_text = " ۞ ".join(text_parts_ar)

    # --- اختيار الخلفية ---
    print("🎨 جاري اختيار خلفية متنوعة...")
    headers = {'Authorization': PEXELS_API_KEY}
    
    search_queries = [
        "nature", "sky", "clouds", "mosque", "islamic architecture", 
        "forest", "river", "mountain", "stars", "galaxy", 
        "flowers", "rain", "desert", "sunset", "ocean", "waterfall"
    ]
    query = random.choice(search_queries)
    page_num = random.randint(1, 5) 
    
    try:
        v_res = requests.get(
            f'https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=40&page={page_num}',
            headers=headers
        ).json()

        videos_list = v_res.get('videos', [])
        long_videos = [v for v in videos_list if v['duration'] >= 15]
        selection_pool = long_videos if long_videos else videos_list

        if not selection_pool: raise Exception("No videos found")

        chosen_video = random.choice(selection_pool)
        v_url = chosen_video['video_files'][0]['link']
        
        for file in chosen_video['video_files']:
            if file['height'] >= 1280 and file['height'] <= 2160:
                v_url = file['link']
                break

    except Exception as e:
        print(f"⚠️ الخلفية الاحتياطية ({e})...")
        v_res = requests.get('https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15', headers=headers).json()
        v_url = random.choice(v_res['videos'])['video_files'][0]['link']

    with open("bg_v.mp4", "wb") as f:
        f.write(requests.get(v_url).content)

    print(f"⚙️ [2/4] المونتاج...")

    bg_source = mp.VideoFileClip("bg_v.mp4").resize(height=1280).crop(x1=0, y1=0, width=720, height=1280)
    bg = loop(bg_source, duration=dur)
    dark = mp.ColorClip(size=(720, 1280), color=(0,0,0), duration=dur).set_opacity(0.4)

    # تعيين الخطوط
    font_ar = ImageFont.truetype(FONT_PATH_AR, 60) 
    font_en = ImageFont.truetype(FONT_PATH_EN, 30)
    font_s = ImageFont.truetype(FONT_PATH_AR, 90)

    overlays = []

    if VIDEO_STYLE == 'scrolling':
        box_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
        box_draw = ImageDraw.Draw(box_canvas)
        box_draw.rounded_rectangle([BOX_X, BOX_Y, BOX_X + BOX_W, BOX_Y + BOX_H], radius=30, fill=(0,0,0,BOX_OPACITY))
        box_bg_clip = mp.ImageClip(np.array(box_canvas)).set_duration(dur)

        lines = textwrap.wrap(full_text, width=28)
        line_h = 95
        text_img_h = (len(lines) + 2) * line_h
        
        txt_img = Image.new('RGBA', (BOX_W, text_img_h), (0, 0, 0, 0))
        d_t = ImageDraw.Draw(txt_img)

        for i, line in enumerate(lines):
            d_t.text((BOX_W/2, i*line_h + 80), process_ar(line), font=font_ar, fill="white", anchor="mm", stroke_width=2, stroke_fill="black")

        raw_txt_clip = mp.ImageClip(np.array(txt_img)).set_duration(dur)

        def scroll_func(t):
            progress = t / dur
            start_pos = BOX_H
            end_pos = -text_img_h
            return ('center', start_pos - (progress * (start_pos - end_pos)))

        moving_txt = raw_txt_clip.set_position(scroll_func)
        text_container = mp.CompositeVideoClip([moving_txt], size=(BOX_W, BOX_H)).set_position((BOX_X, BOX_Y))

        title_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
        title_draw = ImageDraw.Draw(title_canvas)
        title_draw.text((360, BOX_Y - 80), process_ar(s_name), font=font_s, fill="white", anchor="mm", stroke_width=5, stroke_fill="black")
        title_clip = mp.ImageClip(np.array(title_canvas)).set_duration(dur)

        overlays.extend([box_bg_clip, text_container, title_clip])

    else:
        text_clips = []

        for i in range(len(audio_clips)):
            clip_start = starts[i]
            clip_end = starts[i+1] if i < len(starts)-1 else dur
            clip_dur = clip_end - clip_start
            
            if clip_dur <= 0: continue
            
            img = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            
            ar_lines = textwrap.wrap(text_parts_ar[i], width=26)
            en_text_clean = text_parts_en[i].strip()
            en_lines = textwrap.wrap(en_text_clean, width=45)
            
            y_offset = 550 - (len(ar_lines) * 20) 
            
            for line in ar_lines:
                d.text((360, y_offset), process_ar(line), font=font_ar, fill="white", anchor="mm", stroke_width=4, stroke_fill="black")
                y_offset += 80
                
            y_offset += 25 
            
            for line in en_lines:
                d.text((360, y_offset), line, font=font_en, fill="#E0E0E0", anchor="mm", stroke_width=2, stroke_fill="black")
                y_offset += 40
            
            txt_clip = mp.ImageClip(np.array(img)).set_start(clip_start).set_duration(clip_dur).crossfadein(0.2).crossfadeout(0.2)
            text_clips.append(txt_clip)
            
        final_text_overlay = mp.CompositeVideoClip(text_clips, size=(720,1280))
        
        title_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
        title_draw = ImageDraw.Draw(title_canvas)
        title_draw.text((360, 200), process_ar(s_name), font=font_s, fill="white", anchor="mm", stroke_width=5, stroke_fill="black")
        title_clip = mp.ImageClip(np.array(title_canvas)).set_duration(dur)
        
        overlays.extend([final_text_overlay, title_clip])

    final = mp.CompositeVideoClip([bg, dark] + overlays).set_audio(final_audio)

    print("⏳ [3/4] الرندر...")
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="5000k", logger=None, threads=4)

    print("📡 [4/4] الرفع...")
    youtube = youtube_authenticate()

    body = {
        'snippet': {
            'title': f'تلاوة خاشعة - {s_name} #shorts #quran',
            'description': f'سورة {s_name} بصوت مشاري العفاسي \n. \n. \n#quran #قرآن #تلاوة #راحة_نفسية',
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
