"""JPEG selection, source preservation, and shared content-addressed cache tests."""

import base64
import importlib.util
from io import BytesIO
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("document_images", ROOT / "scripts" / "prepare-document-images.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def encoded(image, image_format="PNG"):
    stream = BytesIO()
    image.save(stream, format=image_format)
    return stream.getvalue()


class DocumentImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deterministic full-color artwork, unlike a limited-palette diagram.
        cls.photo = Image.frombytes("RGB", (400, 600), random.Random(42).randbytes(400 * 600 * 3))
        cls.png = encoded(cls.photo)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.assets = self.root / "shared assets"

    def prepare(self, data=None, image_format=b"png", **settings):
        return MODULE.prepare_image(self.png if data is None else data, image_format,
                                    self.assets, **settings)

    def test_jpeg_is_smaller_and_resized_proportionally(self):
        target = self.prepare(max_dimension=300)
        self.assertEqual(target.suffix, ".jpg")
        self.assertLess(target.stat().st_size, len(self.png))
        with Image.open(target) as result:
            self.assertEqual(result.format, "JPEG")
            self.assertEqual(result.size, (200, 300))
            self.assertEqual(result.mode, "RGB")

    def test_never_upscales(self):
        target = self.prepare(max_dimension=1600)
        with Image.open(target) as result:
            self.assertEqual(result.size, self.photo.size)

    def test_keeps_transparency_lossless(self):
        image = self.photo.convert("RGBA")
        image.putpixel((0, 0), (10, 20, 30, 128))
        data = encoded(image)
        target = self.prepare(data)
        self.assertEqual(target.suffix, ".png")
        self.assertEqual(target.read_bytes(), data)

    def test_fully_opaque_alpha_can_be_compressed(self):
        target = self.prepare(encoded(self.photo.convert("RGBA")))
        self.assertEqual(target.suffix, ".jpg")

    def test_palette_transparency_is_preserved(self):
        image = Image.new("P", (50, 50))
        image.info["transparency"] = 0
        data = encoded(image)
        self.assertEqual(self.prepare(data).read_bytes(), data)

    def test_simple_graphics_stay_lossless(self):
        data = encoded(Image.new("RGB", (400, 600), "blue"))
        target = self.prepare(data)
        self.assertEqual(target.suffix, ".png")
        self.assertEqual(target.read_bytes(), data)

    def test_rejects_jpeg_if_it_is_larger_than_original(self):
        image = Image.new("RGB", (100, 100))
        image.putdata([(x, y, 100) for y in range(100) for x in range(100)])
        self.assertIsNone(image.getcolors(maxcolors=256))
        data = encoded(image)
        self.assertIsNone(MODULE.jpeg_candidate(data, 85, 1600))
        self.assertEqual(self.prepare(data).read_bytes(), data)

    def test_preserves_animated_png(self):
        stream = BytesIO()
        self.photo.save(stream, format="PNG", save_all=True,
                        append_images=[self.photo.transpose(Image.Transpose.FLIP_LEFT_RIGHT)], duration=100)
        data = stream.getvalue()
        self.assertEqual(self.prepare(data).read_bytes(), data)

    def test_existing_jpeg_is_not_recompressed(self):
        data = encoded(self.photo, "JPEG")
        with patch.object(MODULE, "jpeg_candidate", side_effect=AssertionError("Unexpected recompression")):
            self.assertEqual(self.prepare(data, b"jpeg").read_bytes(), data)

    def test_svg_and_gif_are_preserved(self):
        for image_format, data in [(b"svg+xml", b'<svg xmlns="http://www.w3.org/2000/svg"/>'),
                                   (b"gif", encoded(Image.new("P", (20, 20)), "GIF"))]:
            with self.subTest(image_format=image_format):
                self.assertEqual(self.prepare(data, image_format).read_bytes(), data)

    def test_cache_reuses_conversion_and_changes_with_settings(self):
        first = self.prepare()
        before = first.stat().st_mtime_ns
        with patch.object(MODULE, "jpeg_candidate", side_effect=AssertionError("Cache miss")):
            self.assertEqual(self.prepare(), first)
        self.assertEqual(first.stat().st_mtime_ns, before)
        self.assertNotEqual(self.prepare(quality=70), first)
        self.assertNotEqual(self.prepare(max_dimension=300), first)
        self.assertNotEqual(self.prepare(quality=None), first)
        with patch.object(MODULE, "CACHE_VERSION", MODULE.CACHE_VERSION + 1):
            self.assertNotEqual(self.prepare(), first)

    def test_repairs_missing_or_corrupt_cached_files(self):
        first = self.prepare()
        expected = first.read_bytes()
        first.write_bytes(b"corrupt")
        self.assertEqual(self.prepare().read_bytes(), expected)
        self.assertEqual(first.resolve().parent, self.assets.resolve())
        first.unlink()
        self.assertEqual(self.prepare().read_bytes(), expected)
        record = first.with_suffix(".json")
        record.write_text("not valid JSON")
        self.assertEqual(self.prepare().read_bytes(), expected)

    def test_both_html_destinations_share_one_image_and_preserve_source(self):
        source = self.root / "book.html"
        url = b"data:image/png;base64," + base64.b64encode(self.png)
        document = b'<p>Unchanged prose</p><img alt="Scene" src="' + url + b'" width="70%">'
        source.write_bytes(document)
        outputs = [self.root / "output" / "book.html", self.root / "output" / "odt-input" / "chapter.html"]
        shared = []
        for destination in outputs:
            used = MODULE.externalize(source, destination, assets=self.assets, dependencies=True)
            self.assertEqual(len(used), 1)
            shared.append(used[0])
            text = destination.read_bytes()
            self.assertNotIn(b"data:image", text)
            relative = text.split(b'src="')[1].split(b'"')[0].decode()
            self.assertEqual((destination.parent / unquote(relative)).resolve(), used[0].resolve())
            self.assertEqual(text.replace(relative.encode(), url), document)
            self.assertIn(MODULE.make_escape(used[0]), Path(str(destination) + ".d").read_text())
        self.assertEqual(shared[0], shared[1])
        self.assertEqual(source.read_bytes(), document)
        self.assertEqual(len(list(self.assets.glob("*.jpg"))), 1)

    def test_cover_path_uses_jpeg_or_lossless_extension_as_appropriate(self):
        source = self.root / "cover.png"
        source.write_bytes(self.png)
        destination = self.root / "output" / "cover.path"
        result = MODULE.prepare_file(source, destination, assets=self.assets, dependencies=True)
        self.assertEqual(result.suffix, ".jpg")
        self.assertEqual(destination.read_text().strip(), str(result))
        self.assertEqual(source.read_bytes(), self.png)
        transparent = self.photo.convert("RGBA")
        transparent.putpixel((0, 0), (0, 0, 0, 0))
        source.write_bytes(encoded(transparent))
        result = MODULE.prepare_file(source, destination, assets=self.assets)
        self.assertEqual(result.suffix, ".png")
        self.assertEqual(result.read_bytes(), source.read_bytes())

    def test_invalid_settings_fail_early(self):
        for settings in [{"quality": 100}, {"quality": True}, {"max_dimension": 0},
                         {"max_dimension": "1600"}]:
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.prepare(**settings)


if __name__ == "__main__":
    unittest.main()
