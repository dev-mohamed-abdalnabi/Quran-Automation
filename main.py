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

# ================== ضبط مكتبة العربي للحفاظ على التشكيل ==================
reshaper_config = {
    'delete_harakat': False,
    'support_ligatures': True,
    'delete_tatweel': False
}
reshaper = arabic_reshaper.ArabicReshaper(configuration=reshaper_config)

def process_ar(t):
    try:
        reshaped = reshaper.reshape(t)
        bidi_text = get_display(reshaped)
        return bidi_text[::-1]
    except Exception as e:
        print(f"⚠️ خطأ في معالجة النص العربي: {e}")
        return t

def format_ayah_text(text):
    """دالة قوية لفصل البسملة عن الآية الأولى باستخدام النص القياسي"""
    if text.startswith("بِسْمِ اللَّهِ"):
        targets = ["الرَّحِيمِ ", "الرحيم "]
        for target in targets:
            if target in text[:60]:
                return text.replace(target, target.strip() + "\n", 1)
    return text

def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('youtube', 'v3', credentials=creds)

def build_shorts_video():
    print("🚀 [1/4] تحضير الموارد...")
    
    if not os.path.exists(FONT_PATH_AR) or not os.path.exists(FONT_PATH_EN):
        print(f"❌ خطأ: ملفات الخطوط غير موجودة! تأكد من رفع Amiri-Regular.ttf و Roboto-Regular.ttf")
        sys.exit(1)

    # --- اختيار السورة ---
    s_id = random.randint(1, 114)
    
    # جلب النص القياسي بالتشكيل المضبوط (يمنع مشكلة التشكيل الطاير)
    res_ar = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/{AUDIO_EDITION}").json()['data']
    res_en = requests.get(f"http://api.alquran.cloud/v1/surah/{s_id}/en.sahih").json()['data']
    
    s_name = res_ar['name']
    
    # تم تثبيت الستايل الجديد لأنه الأفضل وإلغاء الستايل القديم
    print("🎨 الستايل المختار لهذا الفيديو: static_sync (متزامن واحترافي)")

    # --- تجميع الصوت ---
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
        
        # معالجة النص العربي لفصل البسملة
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

    font_ar = ImageFont.truetype(FONT_PATH_AR, 60) 
    font_en = ImageFont.truetype(FONT_PATH_EN, 30)
    font_s = ImageFont.truetype(FONT_PATH_AR, 90)

    overlays = []
    text_clips = []

    for i in range(len(audio_clips)):
        clip_start = starts[i]
        clip_end = starts[i+1] if i < len(starts)-1 else dur
        clip_dur = clip_end - clip_start
        
        if clip_dur <= 0: continue
        
        img = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        
        ar_lines = []
        for part in text_parts_ar[i].split('\n'):
            if part.strip():
                ar_lines.extend(textwrap.wrap(part, width=45))
                
        en_text_clean = text_parts_en[i].strip()
        en_lines = textwrap.wrap(en_text_clean, width=40)
        
        total_text_height = (len(ar_lines) * 80) + 25 + (len(en_lines) * 40)
        y_offset = (1280 - total_text_height) / 2
        
        for line in ar_lines:
            d.text((360, y_offset), process_ar(line), font=font_ar, fill="white", anchor="mm", stroke_width=2, stroke_fill="black")
            y_offset += 80
            
        y_offset += 25 
        
        for line in en_lines:
            d.text((360, y_offset), line, font=font_en, fill="#E0E0E0", anchor="mm", stroke_width=1, stroke_fill="black")
            y_offset += 40
        
        txt_clip = mp.ImageClip(np.array(img)).set_start(clip_start).set_duration(clip_dur).crossfadein(0.2).crossfadeout(0.2)
        text_clips.append(txt_clip)
        
    final_text_overlay = mp.CompositeVideoClip(text_clips, size=(720,1280))
    
    title_canvas = Image.new('RGBA', (720, 1280), (0, 0, 0, 0))
    title_draw = ImageDraw.Draw(title_canvas)
    title_draw.text((360, 200), process_ar(s_name), font=font_s, fill="white", anchor="mm", stroke_width=2, stroke_fill="black")
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
