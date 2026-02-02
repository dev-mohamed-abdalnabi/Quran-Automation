import os
import base64
import json
import pickle
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. دالة الدخول لليوتيوب
def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    return build("youtube", "v3", credentials=creds)

# 2. دالة رفع الفيديو
def upload_video(file_path, title, description):
    youtube = youtube_authenticate()
    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "22"
            },
            "status": {"privacyStatus": "public"}
        },
        media_body=MediaFileUpload(file_path, chunksize=-1, resumable=True)
    )
    response = request.execute()
    print(f"✅ تم رفع الفيديو بنجاح! ID: {response['id']}")

# 3. دالة بناء الفيديو (تأكد أن اسم الدالة صحيح)
def build_steel_video():
    # هنا كود صنع الفيديو الخاص بك (moviepy)
    # ...
    # في نهاية الكود وبعد ما الفيديو final.mp4 يجهز، بننادي دالة الرفع:
    print("Moviepy - Done !")
    upload_video("final.mp4", "تلاوة خاشعة", "وصف الفيديو #قرآن")

# 4. المحرك الأساسي (بدون السطرين دول الكود مش هيشتغل)
if __name__ == "__main__":
    build_steel_video()
