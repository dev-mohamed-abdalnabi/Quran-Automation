import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent
SOURCE = PROJECT_ROOT / "main.py"


class RenderProfileTests(unittest.TestCase):
    def setUp(self):
        self.source_text = SOURCE.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source_text)

    def test_vertical_render_dimensions_remain_unchanged(self):
        assignments = {
            node.targets[0].id: node.value.value
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
        }
        self.assertEqual(assignments["WIDTH"], 1080)
        self.assertEqual(assignments["HEIGHT"], 1920)

    def test_render_command_keeps_the_channel_video_profile(self):
        self.assertIn('fps=24', self.source_text)
        self.assertIn('codec="libx264"', self.source_text)
        self.assertIn('audio_codec="aac"', self.source_text)
        self.assertIn('bitrate="8000k"', self.source_text)
        self.assertIn('preset="ultrafast"', self.source_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
