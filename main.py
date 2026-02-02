import os
import base64
import json
import pickle
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# دالة تسجيل الدخول لليوتيوب (المعدلة للـ JSON)
def youtube_authenticate():
    TOKEN_B64 = os.environ.get("TOKEN_BASE64")
    if not TOKEN_B64:
        raise ValueError("TOKEN_BASE64 is not set in Secrets!")
    
    # فك تشفير التوكن وقراءته كـ JSON
    token_data = json.loads(base64.b64decode(TOKEN_B64).decode('utf-8'))
    creds = Credentials.from_authorized_user_info(token_data)
    
    return build("youtube", "v3", credentials=creds)

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
    print(f"✅ Video uploaded! ID: {response['id']}")

# تأكد أن دالة build_steel_video بتنتهي بطلب الرفع:
# upload_video("final.mp4", "عنوان الفيديو", "وصف الفيديو")
