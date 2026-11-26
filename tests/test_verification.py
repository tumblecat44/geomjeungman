import argparse
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory
import unittest
from zlib import compress, crc32

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "geomjeungman" / "scripts"))
from capture import required_selector
from finish import finish
from preview import screenshot_size


def chunk(kind, payload):
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc32(kind + payload))


def png(width, height):
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    pixels = compress(bytes((width + 1) * height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


class VerificationTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name).resolve()
        self.image = self.folder / "01-390x900.png"
        self.image.write_bytes(png(390, 900))
        self.entry = {
            "requested": [390, 900], "viewport": [390, 900], "screenshot": str(self.image),
            "status": "captured", "layout": {"page_overflow_px": 0, "text": []}, "issues": [],
        }
        self.report = {"target": "viewport", "stage": "awaiting_review", "captures": [self.entry]}

    def test_generic_screen_selector_is_rejected(self):
        for selector in ("main", "body", "#root", "body > main", "#language-menu, main"):
            with self.subTest(selector=selector), self.assertRaises(argparse.ArgumentTypeError):
                required_selector(selector)

    def test_only_reviewed_photo_gets_verdict_zero(self):
        self.assertIn("미완료", finish(self.report, self.folder))
        self.assertEqual(self.entry["verdict"], 2)
        self.entry["review"] = {"status": "clear", "summary": "사진과 수치를 확인했습니다."}
        finish(self.report, self.folder)
        self.assertEqual(self.entry["verdict"], 0)
        self.assertEqual(self.report["stage"], "finished")

    def test_confirmed_issue_requires_problem_details(self):
        self.entry["review"] = {"status": "issue", "summary": "글자가 잘립니다."}
        finish(self.report, self.folder)
        self.assertEqual(self.entry["verdict"], 2)
        self.entry["issues"] = [{"box": [10, 10, 50, 30], "problem": "글자가 잘립니다.", "suggestion": "칸을 넓힙니다."}]
        finish(self.report, self.folder)
        self.assertEqual(self.entry["verdict"], 1)

    def test_ignored_overflow_requires_an_explanation(self):
        self.entry["layout"]["page_overflow_px"] = 79
        self.entry["review"] = {"status": "clear", "summary": "확인했습니다."}
        finish(self.report, self.folder)
        self.assertEqual(self.entry["verdict"], 2)
        self.entry["review"]["measurement_note"] = "이 화면은 오른쪽까지 스크롤해서 쓰도록 만든 디자인입니다."
        finish(self.report, self.folder)
        self.assertEqual(self.entry["verdict"], 0)

    def test_truncated_image_cannot_be_verified(self):
        self.assertEqual(screenshot_size(self.image), [390, 900])
        self.image.write_bytes(self.image.read_bytes()[:24])
        self.assertIsNone(screenshot_size(self.image))
        self.entry["review"] = {"status": "clear", "summary": "사진을 확인했습니다."}
        finish(self.report, self.folder)
        self.assertEqual(self.entry["verdict"], 2)

    def test_size_mismatch_uses_reference_photo(self):
        self.entry.update(viewport=[420, 900], status="size_mismatch")
        self.entry["screenshot"] = str(self.folder / "01-420x900.png")
        Path(self.entry["screenshot"]).write_bytes(png(420, 900))
        findings = finish(self.report, self.folder)
        self.assertEqual(self.entry["verdict"], 2)
        self.assertIn("[참고 사진](01-420x900.png)", findings)

    def test_interrupted_capture_remains_incomplete(self):
        self.report["stage"] = "capturing"
        self.report["captures"].append({"requested": [390, 600], "status": "pending", "issues": []})
        self.assertIn("미완료", finish(self.report, self.folder))
        self.assertEqual(self.report["stage"], "capturing")
        self.assertEqual([entry["verdict"] for entry in self.report["captures"]], [2, 2])


if __name__ == "__main__":
    unittest.main()
