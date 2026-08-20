import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import main


class UploadMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_log_file = main.LOG_FILE
        main.LOG_FILE = os.path.join(self.temp_dir.name, "daily_log.txt")

    def tearDown(self):
        main.LOG_FILE = self.original_log_file
        self.temp_dir.cleanup()

    def test_legacy_daily_log_is_read_without_breaking_skip_logic(self):
        with open(main.LOG_FILE, "w", encoding="utf-8") as file:
            file.write("2026-08-14")
        log = main.load_upload_log()
        self.assertEqual(log["uploads"], [{"date": "2026-08-14", "legacy": True}])

    def test_daily_upload_limit_allows_no_more_than_five_entries_for_one_day(self):
        today = main.today_str()
        log = {"uploads": [{"date": today, "video_id": str(index)} for index in range(5)], "last_audit": []}

        self.assertEqual(main.upload_count_for_date(today, log), 5)
        self.assertEqual(main.DAILY_UPLOAD_LIMIT, 5)

        with open(main.LOG_FILE, "w", encoding="utf-8") as file:
            json.dump(log, file)
        self.assertTrue(main.daily_upload_limit_reached())

    def test_verify_uploaded_video_requires_public_video_on_authenticated_channel(self):
        youtube = Mock()
        youtube.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "video-123",
                    "snippet": {"channelId": "channel-123"},
                    "status": {"privacyStatus": "public"},
                    "processingDetails": {"processingStatus": "succeeded"},
                }
            ]
        }
        youtube.channels().list().execute.return_value = {"items": [{"id": "channel-123"}]}

        verified = main.verify_uploaded_video(youtube, "video-123")
        self.assertEqual(verified["id"], "video-123")

    def test_verify_uploaded_video_rejects_non_public_video(self):
        youtube = Mock()
        youtube.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "video-123",
                    "snippet": {"channelId": "channel-123"},
                    "status": {"privacyStatus": "private"},
                    "processingDetails": {"processingStatus": "succeeded"},
                }
            ]
        }
        youtube.channels().list().execute.return_value = {"items": [{"id": "channel-123"}]}

        with self.assertRaisesRegex(RuntimeError, "ليس عامًا"):
            main.verify_uploaded_video(youtube, "video-123")

    def test_audit_flags_low_view_public_short_after_a_day(self):
        uploaded_at = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        with open(main.LOG_FILE, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "uploads": [
                        {
                            "date": "2026-08-14",
                            "uploaded_at": uploaded_at,
                            "video_id": "video-123",
                            "url": "https://youtu.be/video-123",
                            "title": "اختبار",
                        }
                    ],
                    "last_audit": [],
                },
                file,
            )

        youtube = Mock()
        youtube.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "video-123",
                    "status": {"privacyStatus": "public"},
                    "processingDetails": {"processingStatus": "succeeded"},
                    "statistics": {"viewCount": "4"},
                }
            ]
        }

        results = main.audit_recent_uploads(youtube)
        self.assertIn("4 مشاهدة", results[0]["issue"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
