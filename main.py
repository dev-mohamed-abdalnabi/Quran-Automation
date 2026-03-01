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

# ================== إعدادات الأبعاد الجديدة (4K) ==================
WIDTH = 2160
HEIGHT = 3840

BOX_X = 150
BOX_Y = 840
BOX_W = 1860
BOX_H = 2250
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

reshaper_old = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': True, 'support_ligatures': True})
reshaper_new = arabic_reshaper.ArabicReshaper(configuration={'delete_harakat': False, 'support_ligatures': True})

def process_ar_old(t):
    try: return get_display(reshaper_old.reshape(t))[::-1]
    except: return t

def process_ar_new(t):
    try: return get_display(reshaper_new.reshape(t))[::-1]
    except: return t

# ================== دوال مساعدة ==================
def safe_wrap(text, width):
    words = text.split()
    lines = []
    current_line = []
    current_length = 0
    for word in words:
        if current_length + len(word) <= width:
            current_line.append(word)
            current_length += len(word) + 1
        else:
            if current_line: lines.append(" ".join(current_line))
            current_line = [word]
            current_length = len(word) + 1
    if current_line: lines.append(" ".join(current_line))
    return lines

def format_ayah_text(text):
    if text.startswith("بِسْمِ اللَّهِ"):
        targets = ["الرَّحِيمِ ", "الرحيم "]
        for target in targets:
            if target in text[:60]:
                return text.replace(target, target.strip() + "\n", 1)
    return text

def draw_text_with_shadow(draw, pos, text, font, fill_color):
    x, y = pos
    shadow_color = "black"
    # تكبير الظل ليتناسب مع جودة 4K
    offsets = [(6,6), (-6,6), (6,-6), (-6,-6), (0,6), (0,-6), (6,0), (-6,0)]
    for ox, oy in offsets:
        draw.text((x+ox, y+oy), text, font=font, fill=shadow_color, anchor="mm")
    draw.text((x, y), text, font=font, fill=fill_color, anchor="mm")

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🚀 [1/4] تحضير الموارد لجودة 4K...")
    
    if not os.path.exists(FONT_PATH_AR) or not os.path.exists(FONT_PATH_EN):
        print(f"❌ خطأ: ملفات الخطوط غير موجودة! تأكد من رفع Amiri-Regular.ttf و Roboto-Regular.ttf")
        sys.exit(1)

    s_id = random.randint(1, 114)
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    s_name = res_ar['name']
    
    VIDEO_STYLE = random.choice(['scrolling', 'static_sync'])
    print(f"🎨 الستايل المختار لهذا الفيديو: {VIDEO_STYLE}")

    audio_clips = []
    text_parts_ar = []
    text_parts_en = []
    current_duration = 0
    TARGET_DURATION = 50 

    for i, (a_ar, a_en) in enumerate(zip(res_ar['ayahs'], res_en['ayahs'])):
        f_path = f"temp_{i}.mp3"
        with open(f_path, 'wb') as f:
            f.write(requests.get(a_ar['audio']).content)
        
        clip = mp.AudioFileClip(f_path)
        audio_clips.append(clip)
        
        formatted_ar_text = format_ayah_text(a_ar['text'])
        text_parts_ar.append(formatted_ar_text)
        text_parts_en.append(a_en['text'])
        
        current_duration += clip.duration
        if current_duration >= TARGET_DURATION:
            if current_duration > 59: 
                audio_clips.pop()
                text_parts_ar.pop()
                text_parts_en.pop()
            break
    
    overlap_sec = 0.15
    starts = [0]
    for clip in audio_clips[:-1]:
        starts.append(max(0, starts[-1] + clip.duration - overlap_sec))
        
    for i in range(len(audio_clips)):
        audio_clips[i] = audio_clips[i].set_start(starts[i])
        
    final_audio = mp.CompositeAudioClip(audio_clips)
    dur = min(59, final_audio.duration)
    final_audio = final_audio.subclip(0, dur)

    print("🎨 جاري اختيار خلفية عالية الجودة...")
    headers = {'Authorization': PEXELS_API_KEY}
    search_queries = ["nature", "sky", "clouds", "mosque", "islamic architecture", "forest", "mountain", "ocean", "waterfall"]
    query = random.choice(search_queries)
    page_num = random.randint(1, 5) 
    
    try:
        v_res = requests.get(f'https://api.pexels.com/videos/search?query={query}&orientation=portrait&per_page=40&page={page_num}', headers=headers).json()
        videos_list = v_res.get('videos', [])
        long_videos = [v for v in videos_list if v['duration'] >= 15]
        selection_pool = long_videos if long_videos else videos_list

        if not selection_pool: raise Exception("No videos found")
        chosen_video = random.choice(selection_pool)
        v_url = chosen_video['video_files'][0]['link']
        
        # محاولة سحب أعلى جودة ممكنة من بيسكلز
        for file in chosen_video['video_files']:
            if file['height'] >= 2160:
                v_url = file['link']
                break
    except Exception as e:
        v_res = requests.get('https://api.pexels.com/videos/search?query=nature&orientation=portrait&per_page=15', headers=headers).json()
        v_url = random.choice(v_res['videos'])['video_files'][0]['link']

    with open("bg_v.mp4", "wb") as f:
        f.write(requests.get(v_url).content)

    print(f"⚙️ [2/4] المونتاج (4K Resolution)...")

    # تكبير الخلفية لتناسب 4K
    bg_source = mp.VideoFileClip("bg_v.mp4").resize(height=HEIGHT).crop(x1=0, y1=0, width=WIDTH, height=HEIGHT)
    bg = loop(bg_source, duration=dur)
    dark = mp.ColorClip(size=(WIDTH, HEIGHT), color=(0,0,0), duration=dur).set_opacity(0.4)

    # تكبير الخطوط 3 أضعاف
    font_ar = ImageFont.truetype(FONT_PATH_AR, 180) 
    font_en = ImageFont.truetype(FONT_PATH_EN, 90)
    font_s = ImageFont.truetype(FONT_PATH_AR, 270)

    overlays = []

    if VIDEO_STYLE == 'scrolling':
        box_canvas = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        box_draw = ImageDraw.Draw(box_canvas)
        box_draw.rounded_rectangle([BOX_X, BOX_Y, BOX_X + BOX_W, BOX_Y + BOX_H], radius=90, fill=(0,0,0,BOX_OPACITY))
        box_bg_clip = mp.ImageClip(np.array(box_canvas)).set_duration(dur)

        full_text_flat = " ۞ ".join([t.replace('\n', ' ') for t in text_parts_ar])
        lines = safe_wrap(full_text_flat, width=35) 
        line_h = 285 # تكبير المسافة بين السطور
        text_img_h = (len(lines) + 2) * line_h
        
        txt_img = Image.new('RGBA', (BOX_W, text_img_h), (0, 0, 0, 0))
        d_t = ImageDraw.Draw(txt_img)

        for i, line in enumerate(lines):
            processed_line = process_ar_old(line)
            draw_text_with_shadow(d_t, (BOX_W/2, i*line_h + 240), processed_line, font_ar, "white")

        raw_txt_clip = mp.ImageClip(np.array(txt_img)).set_duration(dur)

        def scroll_func(t):
            progress = t / dur
            start_pos = BOX_H
            end_pos = -text_img_h
            return ('center', start_pos - (progress * (start_pos - end_pos)))

        moving_txt = raw_txt_clip.set_position(scroll_func)
        text_container = mp.CompositeVideoClip([moving_txt], size=(BOX_W, BOX_H)).set_position((BOX_X, BOX_Y))

        title_canvas = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        title_draw = ImageDraw.Draw(title_canvas)
        draw_text_with_shadow(title_draw, (WIDTH/2, BOX_Y - 240), process_ar_old(s_name), font_s, "white")
        title_clip = mp.ImageClip(np.array(title_canvas)).set_duration(dur)

        overlays.extend([box_bg_clip, text_container, title_clip])

    else:
        text_clips = []
        for i in range(len(audio_clips)):
            clip_start = starts[i]
            clip_end = starts[i+1] if i < len(starts)-1 else dur
            clip_dur = clip_end - clip_start
            
            if clip_dur <= 0: continue
            
            img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            
            ar_lines = []
            for part in text_parts_ar[i].split('\n'):
                if part.strip():
                    ar_lines.extend(safe_wrap(part, width=45)) 
                    
            en_text_clean = text_parts_en[i].strip()
            en_lines = safe_wrap(en_text_clean, width=40)
            
            # تعديل المسافات لتناسب 4K
            total_text_height = (len(ar_lines) * 240) + 75 + (len(en_lines) * 120)
            y_offset = (HEIGHT - total_text_height) / 2
            
            for line in ar_lines:
                processed_line = process_ar_new(line)
                draw_text_with_shadow(d, (WIDTH/2, y_offset), processed_line, font_ar, "white")
                y_offset += 240
                
            y_offset += 75 
            
            for line in en_lines:
                d.text((WIDTH/2, y_offset), line, font=font_en, fill="#E0E0E0", anchor="mm", stroke_width=3, stroke_fill="black")
                y_offset += 120
            
            txt_clip = mp.ImageClip(np.array(img)).set_start(clip_start).set_duration(clip_dur).crossfadein(0.2).crossfadeout(0.2)
            text_clips.append(txt_clip)
            
        final_text_overlay = mp.CompositeVideoClip(text_clips, size=(WIDTH, HEIGHT))
        
        title_canvas = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
        title_draw = ImageDraw.Draw(title_canvas)
        draw_text_with_shadow(title_draw, (WIDTH/2, 600), process_ar_new(s_name), font_s, "white")
        title_clip = mp.ImageClip(np.array(title_canvas)).set_duration(dur)
        
        overlays.extend([final_text_overlay, title_clip])

    final = mp.CompositeVideoClip([bg, dark] + overlays).set_audio(final_audio)

    print("⏳ [3/4] الرندر (جاري التصدير بجودة 4K، قد يستغرق وقتاً أطول)...")
    # رفع البت ريت لـ 20000k عشان جودة الـ 4K تظهر صح
    final.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", bitrate="20000k", logger=None, threads=4)

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
