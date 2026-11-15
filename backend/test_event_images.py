"""Event imagery: curated, attributed, and served from the local cache.

These tests never touch the network. They pin the two properties that matter
for a presentation: an image address must be servable offline once cached, and
every picture must carry the licence and author it is shown with.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import event_images


class TestManifest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(
            (event_images.MANIFEST).read_text(encoding="utf-8"))["events"]

    def test_every_catalogue_event_has_two_to_five_images(self):
        import event_network
        data = event_network.load_catalogue()
        for event in data["events"]:
            rows = self.manifest.get(event["id"], [])
            self.assertGreaterEqual(len(rows), 2, f"{event['id']} needs at least 2 images")
            self.assertLessEqual(len(rows), 5, f"{event['id']} has more than 5 images")

    def test_every_image_is_attributed_and_licensed(self):
        for event_id, rows in self.manifest.items():
            for row in rows:
                self.assertTrue(row.get("caption"), f"{event_id}: missing caption")
                self.assertTrue(row.get("page", "").startswith("https://commons.wikimedia.org/"),
                                f"{event_id}: not a Commons page")
                self.assertTrue(row.get("licence"), f"{event_id}: missing licence")
                self.assertTrue(row.get("url", "").startswith(
                    "https://commons.wikimedia.org/wiki/Special:FilePath/"),
                    f"{event_id}: unstable image address")

    def test_images_are_addressed_through_the_local_route(self):
        rows = event_images.for_event("el_nino_2023_2024")
        self.assertGreaterEqual(len(rows), 2)
        for row in rows:
            self.assertTrue(row["src"].startswith("/api/event-image/el_nino_2023_2024/"))
            self.assertNotIn("commons.wikimedia.org", row["src"])

    def test_unknown_event_has_no_images_rather_than_an_error(self):
        self.assertEqual(event_images.for_event("not_an_event"), [])
        self.assertFalse(event_images.has_images("not_an_event"))

    def test_out_of_range_index_is_rejected(self):
        with self.assertRaises(KeyError):
            event_images.image_bytes("el_nino_2023_2024", 99)


class TestCache(unittest.TestCase):
    def test_a_cached_file_is_served_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            url = "https://example.test/x.png"
            stored = cache / "x.png"
            stored.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
            with patch.object(event_images, "CACHE", cache), \
                 patch.object(event_images, "_cache_path", return_value=stored), \
                 patch.object(event_images, "_load", return_value={
                     "ev": [{"url": url}]}), \
                 patch.object(event_images.urllib.request, "urlopen",
                              side_effect=AssertionError("network must not be used")):
                raw, ctype = event_images.image_bytes("ev", 0)
            self.assertEqual(ctype, "image/png")
            self.assertTrue(raw.startswith(b"\x89PNG"))

    def test_format_is_detected_from_the_bytes(self):
        self.assertEqual(event_images._content_type(b"\xff\xd8\xff\xe0"), "image/jpeg")
        self.assertEqual(event_images._content_type(b"GIF89a"), "image/gif")
        self.assertEqual(event_images._content_type(b"\x89PNG\r\n"), "image/png")
        self.assertEqual(event_images._content_type(b"nonsense"), "application/octet-stream")


if __name__ == "__main__":
    unittest.main()
