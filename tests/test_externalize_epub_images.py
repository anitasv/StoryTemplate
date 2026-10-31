"""Regression tests for lossless extraction within shared image preparation."""

import base64
import binascii
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare-document-images.py"
SPEC = importlib.util.spec_from_file_location("externalizer", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExternalizeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "book.html"
        self.output = self.root / "output" / "book.epub-input.html"

    def convert(self, document):
        self.source.write_bytes(document)
        self.used = MODULE.externalize(self.source, self.output, quality=None)
        self.assertEqual(self.source.read_bytes(), document)
        return self.output.read_bytes()

    def test_lossless_html_and_deduplicated_images(self):
        image = b"\x89PNG\r\n\x1a\n\x00test bytes"
        encoded = base64.b64encode(image)
        url = b"data:image/png;base64," + encoded
        document = (b'<!doctype html><p>Book &amp; text</p><img alt="a" src="' + url
                    + b'" width="70%"><img src=\'' + url + b"'></body>")
        result = self.convert(document)
        name = self.used[0].name
        self.assertEqual(result, document.replace(url, f"document-assets/{name}".encode()))
        assets = list((self.output.parent / "document-assets").glob("*.png"))
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0].read_bytes(), image)
        before = assets[0].stat().st_mtime_ns
        MODULE.externalize(self.source, self.output, quality=None)
        self.assertEqual(assets[0].stat().st_mtime_ns, before)

    def test_plain_html_and_other_urls_are_untouched(self):
        document = (b'<p>No embedded images</p><img src="../images/cover.png">'
                    b'<img src="https://example.com/image.png">'
                    b'<a href="data:text/plain;base64,SGk=">Hi</a>')
        self.assertEqual(self.convert(document), document)

    def test_formats_and_wrapped_base64(self):
        for mime, extension in MODULE.EXTENSIONS.items():
            with self.subTest(mime=mime):
                encoded = base64.b64encode(b"image bytes")
                encoded = encoded[:4] + b"\r\n " + encoded[4:]
                result = self.convert(b'<img src="data:image/' + mime
                                      + b';base64,' + encoded + b'">')
                name = self.used[0].name
                self.assertTrue(name.endswith(extension))
                self.assertEqual(result, f'<img src="document-assets/{name}">'.encode())
                self.assertEqual((self.output.parent / "document-assets" / name).read_bytes(),
                                 b"image bytes")

    def test_invalid_base64_does_not_write_html(self):
        self.source.write_bytes(b'<img src="data:image/png;base64,!!!">')
        with self.assertRaises(binascii.Error):
            MODULE.externalize(self.source, self.output, quality=None)
        self.assertFalse(self.output.exists())

    def test_refuses_to_overwrite_source(self):
        self.source.write_bytes(b"original")
        with self.assertRaises(ValueError):
            MODULE.externalize(self.source, self.source)
        self.assertEqual(self.source.read_bytes(), b"original")

    def test_repairs_corrupt_cached_image(self):
        document = b'<img src="data:image/png;base64,aW1hZ2U=">'
        self.convert(document)
        asset = self.used[0]
        asset.write_bytes(b"corrupt")
        MODULE.externalize(self.source, self.output, quality=None)
        self.assertEqual(asset.read_bytes(), b"image")


if __name__ == "__main__":
    unittest.main()
