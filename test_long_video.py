import os
import random
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from unittest import mock

import long_prompts as prompts
import long_render as render
import long_video as lv


class PromptTests(unittest.TestCase):
    def test_many_combinations(self):
        self.assertGreaterEqual(prompts.total_combinations(), 100)

    def test_plan_is_unique_and_safe(self):
        plan = prompts.plan_video(random.Random(1), 26)
        ids = [i["id"] for i in plan["items"]] + [plan["thumb"]["id"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len({i["prompt"] for i in plan["items"]}), 26)
        for item in plan["items"]:
            self.assertIn("no people", item["prompt"])
            self.assertIn("no text", item["prompt"])

    def test_avoids_used_ids(self):
        rng = random.Random(2)
        first = prompts.plan_video(rng, 10)
        used = [i["id"] for i in first["items"]]
        second = prompts.plan_video(rng, 10, used_ids=used)
        self.assertFalse(set(used) & {i["id"] for i in second["items"]})


class ScheduleTests(unittest.TestCase):
    def test_due_rules(self):
        log = lv.default_log()
        self.assertTrue(lv.is_due(log, date(2026, 9, 24)))
        log["uploads"].append({"date": "2026-09-23"})
        self.assertFalse(lv.is_due(log, date(2026, 9, 24)))
        self.assertTrue(lv.is_due(log, date(2026, 9, 25)))

    def test_order_starts_at_baqarah_and_wraps(self):
        self.assertEqual(lv.default_log()["next_surah"], 2)
        self.assertEqual(lv.following_surah(2), 3)
        self.assertEqual(lv.following_surah(114), 2)


class TextTests(unittest.TestCase):
    def test_clean_name(self):
        self.assertEqual(lv.clean_name("سُورَةُ ٱلْبَقَرَةِ"), "سورة البقرة")
        self.assertEqual(lv.clean_name("آل عمران"), "سورة آل عمران")

    def test_timestamps_and_chapters(self):
        self.assertEqual(lv.fmt_ts(65), "1:05")
        self.assertEqual(lv.fmt_ts(3725), "1:02:05")
        starts = [3.5 + i * 60 for i in range(60)]
        ayahs = [{"number": i + 1} for i in range(60)]
        chapters = lv.build_chapters(starts, ayahs)
        self.assertTrue(chapters.startswith("0:00 "))
        self.assertGreaterEqual(len(chapters.splitlines()), 3)
        self.assertEqual(lv.build_chapters([3.5, 10], [{"number": 1}, {"number": 2}]), "")

    def test_metadata_limits(self):
        title, desc, tags, _ = lv.build_metadata(random.Random(3), "سورة البقرة", "مشاري العفاسي", 7900, "0:00 x")
        self.assertLessEqual(len(title), 100)
        self.assertLessEqual(len(desc), 5000)
        self.assertLessEqual(sum(len(t) for t in tags), 450)


class RenderTests(unittest.TestCase):
    def test_longest_ayah_fits(self):
        ar = "يَٰٓأَيُّهَا ٱلَّذِينَ ءَامَنُوٓاْ " * 22
        en = "O you who have believed, when you contract a debt for a specified term, write it down. " * 6
        fit = render.fit_text(ar, en, 1460, 620)
        self.assertLessEqual(fit["total"], 620)

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg غير موجود")
    def test_end_to_end_offline(self):
        work = tempfile.mkdtemp()
        try:
            def fake_download(url, path, retries=4):
                subprocess.run(
                    ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5", path],
                    check=True,
                )

            ayahs = [
                {"number": i + 1, "audio": "x", "ar": "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ " * (i + 1), "en": "In the name of God. " * (i + 1)}
                for i in range(4)
            ]
            with mock.patch.object(lv, "download", fake_download):
                wav, durations = lv.build_audio(ayahs, work)
            starts, total = lv.build_timeline(durations)
            self.assertAlmostEqual(total, lv.INTRO_SEC + sum(durations), places=3)

            with mock.patch.dict(os.environ, {"IMAGE_PROVIDER": "none"}):
                plan = prompts.plan_video(random.Random(4), 2)
                bgs = []
                for k, item in enumerate(plan["items"]):
                    img, source = lv.long_images.generate_image(item["prompt"], k, render.W, render.H, plan["palette"])
                    self.assertIn(source, ("gradient", "pexels"))
                    p = os.path.join(work, f"bg_{k}.jpg")
                    render.prepare_background(img).save(p, "JPEG")
                    bgs.append(p)
            frames = lv.make_frames(ayahs, starts, durations, total, bgs, "سورة البقرة", "مشاري العفاسي", "٤ دقيقة", work)
            out = os.path.join(work, "out.mp4")
            render.build_video(frames, wav, out, work)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertAlmostEqual(float(probe), total, delta=0.5)

            thumb = os.path.join(work, "t.jpg")
            render.make_thumbnail(img, "سورة البقرة", "مشاري العفاسي", "2:12", thumb)
            self.assertLess(os.path.getsize(thumb), 2_000_000)
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
