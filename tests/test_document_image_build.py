"""Integration regressions for the actual shared EPUB/ODT image build rules.

Every test copies the production Makefile and image preparer into an isolated
project. Real Typst, Pandoc, make, and Pillow are used when available; no command
runs against the manuscript or its generated books.
"""

from html.parser import HTMLParser
from pathlib import Path
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import unquote
import zipfile

try:
    from PIL import Image
except ImportError:
    Image = None


ROOT = Path(__file__).resolve().parents[1]
BOOK_NAME = "Test_Title"
TOOLS_AVAILABLE = all(shutil.which(tool) for tool in ("make", "typst", "pandoc"))

class ImageSources(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.sources = []
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.sources.append(dict(attrs)["src"])


@unittest.skipUnless(TOOLS_AVAILABLE and Image is not None,
                     "Shared image build tests require make, Typst, Pandoc, and Pillow")
class DocumentImageBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="document-image-build-")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name).resolve()
        for directory in ("scripts/pandoc", "chapters", "images", "styles", "docs"):
            (self.project / directory).mkdir(parents=True)
        for name in ("Makefile", "scripts/prepare-document-images.py",
                     "scripts/format-odt-images.py", "scripts/pandoc/odt-image-width.lua"):
            (self.project / name).write_bytes((ROOT / name).read_bytes())
        for chapter in (1, 2):
            self.write(f"chapters/chapter{chapter}.typ", f'''\
= Chapter {chapter}: Shared illustration

The same original image appears in both chapters and both export formats.

#figure(image("../images/scene.png", width: 50%))
''')
        self.write("story.typ", '#include "chapters/chapter1.typ"\n#include "chapters/chapter2.typ"\n')
        self.write("ebook.typ", '#set document(title: "Image build fixture")\n#include "story.typ"\n')
        self.write("print.typ", '#include "ebook.typ"\n')
        self.write("styles/metadata.yaml", 'title: "Image build fixture"\nlang: en\n')
        self.write("styles/epub.css", "img { max-width: 100%; height: auto; }\n")
        self.write("styles/image-export.json", json.dumps({"quality": 85, "max_dimension": 128}) + "\n")
        # Many distinct opaque RGB colors exercise the photograph/JPEG branch,
        # unlike a flat-color PNG which the preparer deliberately preserves.
        for filename, seed in (("scene.png", 724), ("cover.png", 911)):
            randomizer = random.Random(seed)
            pixels = bytes(randomizer.randrange(256) for _ in range(128 * 96 * 3))
            Image.frombytes("RGB", (128, 96), pixels).save(self.project / "images" / filename)
        # macOS make may compare only whole seconds. Give every fixture source a
        # definitely older timestamp without adding sleeps to the suite.
        source_time = int(time.time()) - 120
        for path in self.project.rglob("*"):
            if path.is_file():
                os.utime(path, (source_time, source_time))
        self.original_files = {path: path.read_bytes() for path in self.project.rglob("*")
                               if path.is_file()}
        self.output = self.project / "output"
        self.assets = self.output / "document-assets"
        self.epub_input = self.output / f"{BOOK_NAME}.epub-input.html"
        self.epub = self.output / f"{BOOK_NAME}.epub"
        self.chapter_inputs = [self.output / "odt-input" / f"chapter{n}.html" for n in (1, 2)]
        self.odts = [self.output / "odt" / f"chapter{n}.odt" for n in (1, 2)]
        self.raw_html = [self.output / f"{BOOK_NAME}.html"] + [
            self.output / "chapters" / f"chapter{n}.html" for n in (1, 2)]

    def write(self, name, text):
        (self.project / name).write_text(text, encoding="utf-8")

    def assert_temporary_target(self, path):
        """Verify actual resolved destinations before commands can delete them."""
        resolved = path.resolve()
        self.assertFalse(path.is_symlink(), f"Unexpected target symlink: {path}")
        self.assertNotEqual(resolved, self.project)
        self.assertTrue(resolved.is_relative_to(self.project),
                        f"Refusing operation outside isolated fixture: {resolved}")
        return resolved

    def make(self, *targets):
        if any(target in ("clean", "clean-odt") for target in targets):
            # These are the actual resolved directories referenced by the copied
            # Makefile. Assert containment for descendants before running rm.
            self.assert_temporary_target(self.output)
            for path in self.output.rglob("*"):
                self.assert_temporary_target(path)
        result = subprocess.run(
            ["make", f"PYTHON={sys.executable}", *targets], cwd=self.project,
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0,
                         f"make {' '.join(targets)} failed\n{result.stdout}\n{result.stderr}")
        return result.stdout + result.stderr

    def build(self):
        return self.make("epub", "odt")

    def image_targets(self, prepared):
        sources = ImageSources(prepared.read_text()).sources
        self.assertTrue(sources, f"No illustration in prepared input: {prepared}")
        self.assertTrue(all(not source.startswith("data:") for source in sources))
        return [(prepared.parent / unquote(source)).resolve() for source in sources]

    def jpeg_payloads(self, archive):
        with zipfile.ZipFile(archive) as document:
            self.assertIsNone(document.testzip())
            return {document.read(name) for name in document.namelist()
                    if name.lower().endswith((".jpg", ".jpeg"))}

    def snapshot(self, paths):
        return {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in paths}

    def output_files(self):
        return [path for path in self.output.rglob("*") if path.is_file()]

    def age_generated_files(self):
        # Ensure subsequent repairs/rebuilds get distinguishable timestamps even
        # under make versions with one-second timestamp resolution.
        old = int(time.time()) - 30
        for path in self.output_files():
            os.utime(path, (old, old))

    def assert_originals_unchanged(self):
        for path, data in self.original_files.items():
            with self.subTest(source=path.relative_to(self.project)):
                self.assertEqual(path.read_bytes(), data)

    def test_epub_and_odt_share_identical_jpeg_asset_without_changing_png(self):
        self.build()
        epub_targets = self.image_targets(self.epub_input)
        self.assertEqual(len(epub_targets), 2)
        scene = epub_targets[0]
        self.assertEqual(epub_targets, [scene, scene])
        self.assertEqual(scene.parent, self.assets.resolve())
        self.assertEqual(scene.suffix, ".jpg")
        for prepared in self.chapter_inputs:
            self.assertEqual(self.image_targets(prepared), [scene])
        jpeg = scene.read_bytes()
        self.assertLess(len(jpeg), len(self.original_files[self.project / "images/scene.png"]))
        self.assertIn(jpeg, self.jpeg_payloads(self.epub))
        for odt in self.odts:
            self.assertEqual(self.jpeg_payloads(odt), {jpeg})
        cover = (self.project / (self.output / "epub-cover.path").read_text().strip()).resolve()
        self.assertEqual(cover.suffix, ".jpg")
        self.assertIn(cover.read_bytes(), self.jpeg_payloads(self.epub))
        self.assertEqual(set(self.assets.glob("*.jpg")), {scene, cover})
        self.assert_originals_unchanged()

    def test_unchanged_build_preserves_all_input_output_and_cache_mtimes(self):
        self.build()
        files = list(self.original_files) + self.output_files()
        before = self.snapshot(files)
        log = self.build()
        self.assertEqual(self.snapshot(files), before)
        self.assertEqual(set(self.output_files()), set(files) - set(self.original_files))
        self.assertNotIn("Prepared HTML:", log)
        self.assertNotIn("Prepared image:", log)
        self.assertNotIn("typst compile", log)
        self.assertNotIn("--from=html", log)

    def test_config_change_invalidates_jpegs_and_both_prepared_inputs(self):
        self.build()
        self.age_generated_files()
        original_scene = self.image_targets(self.epub_input)[0]
        old_cache = self.snapshot(list(self.assets.glob("*")))
        raw_before = self.snapshot(self.raw_html)
        prepared = [self.epub_input, *self.chapter_inputs, self.output / "epub-cover.path"]
        prepared_before = self.snapshot(prepared)
        output_before = self.snapshot([self.epub, *self.odts])
        config = self.project / "styles/image-export.json"
        config.write_text(json.dumps({"quality": 42, "max_dimension": 64}) + "\n")
        changed = int(time.time()) - 10
        os.utime(config, (changed, changed))
        self.build()
        new_scene = self.image_targets(self.epub_input)[0]
        self.assertNotEqual(new_scene, original_scene)
        self.assertNotEqual(new_scene.read_bytes(), old_cache[original_scene][1])
        with Image.open(new_scene) as image:
            self.assertEqual(image.size, (64, 48))
        for chapter in self.chapter_inputs:
            self.assertEqual(self.image_targets(chapter), [new_scene])
        self.assertEqual(self.snapshot(self.raw_html), raw_before,
                         "Changing compression must not recompile standalone HTML")
        for path, (mtime, _) in prepared_before.items():
            self.assertGreater(path.stat().st_mtime_ns, mtime, f"Stale prepared input: {path}")
        for path, (mtime, _) in output_before.items():
            self.assertGreater(path.stat().st_mtime_ns, mtime, f"Stale final document: {path}")
        self.assertEqual(self.snapshot(old_cache), old_cache,
                         "New settings must not overwrite existing immutable derivatives")
        jpeg = new_scene.read_bytes()
        self.assertIn(jpeg, self.jpeg_payloads(self.epub))
        for odt in self.odts:
            self.assertEqual(self.jpeg_payloads(odt), {jpeg})
        self.assertEqual((self.project / "images/scene.png").read_bytes(),
                         self.original_files[self.project / "images/scene.png"])

    def test_missing_individual_asset_is_repaired_through_generated_dependencies(self):
        self.build()
        self.age_generated_files()
        scene = self.image_targets(self.epub_input)[0]
        expected = scene.read_bytes()
        tracked = [self.epub_input, *self.chapter_inputs, self.epub, *self.odts]
        before = self.snapshot(tracked)
        raw_before = self.snapshot(self.raw_html)
        for prepared in [self.epub_input, *self.chapter_inputs]:
            dependencies = Path(str(prepared) + ".d")
            self.assertTrue(dependencies.is_file())
            self.assertIn(scene.name, dependencies.read_text())
        resolved = self.assert_temporary_target(scene)
        self.assertEqual(resolved.parent, self.assets.resolve())
        resolved.unlink()
        self.assertFalse(scene.exists())
        self.build()
        self.assertEqual(scene.read_bytes(), expected)
        self.assertEqual(self.snapshot(self.raw_html), raw_before)
        for path, (mtime, _) in before.items():
            self.assertGreater(path.stat().st_mtime_ns, mtime,
                               f"Missing shared asset did not invalidate {path}")
        for odt in self.odts:
            self.assertEqual(self.jpeg_payloads(odt), {expected})
        self.assertIn(expected, self.jpeg_payloads(self.epub))

    def test_odt_alone_repairs_missing_shared_asset_without_epub_preparation(self):
        self.build()
        self.age_generated_files()
        scene = self.image_targets(self.chapter_inputs[0])[0]
        expected = scene.read_bytes()
        untouched_epub = self.snapshot([self.epub, self.epub_input])
        before = self.snapshot([*self.chapter_inputs, *self.odts])
        resolved = self.assert_temporary_target(scene)
        self.assertEqual(resolved.parent, self.assets.resolve())
        resolved.unlink()
        self.make("odt")
        self.assertEqual(scene.read_bytes(), expected)
        self.assertEqual(self.snapshot(untouched_epub), untouched_epub,
                         "ODT asset repair must not invoke EPUB preparation")
        for path, (mtime, _) in before.items():
            self.assertGreater(path.stat().st_mtime_ns, mtime, str(path))
        for odt in self.odts:
            self.assertEqual(self.jpeg_payloads(odt), {expected})

    def test_missing_cover_asset_is_repaired_through_cover_dependencies(self):
        self.build()
        self.age_generated_files()
        cover_path = self.output / "epub-cover.path"
        cover = (self.project / cover_path.read_text().strip()).resolve()
        expected = cover.read_bytes()
        self.assertIn(cover.name, Path(str(cover_path) + ".d").read_text())
        unchanged = self.snapshot([self.epub_input, *self.chapter_inputs, *self.odts])
        before = self.snapshot([cover_path, self.epub])
        resolved = self.assert_temporary_target(cover)
        self.assertEqual(resolved.parent, self.assets.resolve())
        resolved.unlink()
        self.make("epub")
        self.assertEqual(cover.read_bytes(), expected)
        self.assertIn(expected, self.jpeg_payloads(self.epub))
        self.assertEqual(self.snapshot(unchanged), unchanged)
        for path, (mtime, _) in before.items():
            self.assertGreater(path.stat().st_mtime_ns, mtime, str(path))

    def test_parallel_exports_share_valid_cached_images(self):
        self.make("-j4", "epub", "odt")
        scene = self.image_targets(self.epub_input)[0]
        jpeg = scene.read_bytes()
        self.assertIn(jpeg, self.jpeg_payloads(self.epub))
        for prepared, odt in zip(self.chapter_inputs, self.odts):
            self.assertEqual(self.image_targets(prepared), [scene])
            self.assertEqual(self.jpeg_payloads(odt), {jpeg})
        self.assert_originals_unchanged()

    def test_entire_cache_removal_recovers_both_exports(self):
        self.build()
        self.age_generated_files()
        expected = self.image_targets(self.epub_input)[0].read_bytes()
        raw_before = self.snapshot(self.raw_html)
        target = self.assert_temporary_target(self.assets)
        self.assertEqual(target, self.output.resolve() / "document-assets")
        for path in target.rglob("*"):
            self.assert_temporary_target(path)
        shutil.rmtree(target)
        self.build()
        self.assertEqual(self.image_targets(self.epub_input)[0].read_bytes(), expected)
        self.assertEqual(self.snapshot(self.raw_html), raw_before)
        self.assertIn(expected, self.jpeg_payloads(self.epub))
        for odt in self.odts:
            self.assertEqual(self.jpeg_payloads(odt), {expected})

    def test_image_edit_rebuilds_exports_without_touching_original(self):
        self.build()
        self.age_generated_files()
        old_scene = self.image_targets(self.epub_input)[0]
        image = self.project / "images/scene.png"
        with Image.open(image) as original:
            original.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(image)
        changed = image.read_bytes()
        self.build()
        scene = self.image_targets(self.epub_input)[0]
        self.assertNotEqual(scene, old_scene)
        self.assertEqual(image.read_bytes(), changed)
        self.assertIn(scene.read_bytes(), self.jpeg_payloads(self.epub))
        for odt in self.odts:
            self.assertEqual(self.jpeg_payloads(odt), {scene.read_bytes()})

    def test_filter_edit_rebuilds_only_odt_outputs(self):
        self.build()
        self.age_generated_files()
        unchanged = self.snapshot([self.epub, self.epub_input, *self.raw_html,
                                   *self.chapter_inputs, *self.assets.glob("*")])
        before = self.snapshot(self.odts)
        script = self.project / "scripts/pandoc/odt-image-width.lua"
        script.write_text(script.read_text() + "\n-- Dependency regression.\n")
        self.build()
        self.assertEqual(self.snapshot(unchanged), unchanged)
        for path, (mtime, _) in before.items():
            self.assertGreater(path.stat().st_mtime_ns, mtime)

    def test_clean_odt_preserves_shared_cache_and_epub(self):
        self.build()
        preserved_paths = [self.epub, self.epub_input, Path(str(self.epub_input) + ".d"),
                           self.output / "epub-cover.path", self.output / "epub-cover.path.d",
                           self.raw_html[0], *self.assets.glob("*")]
        preserved = self.snapshot(preserved_paths)
        unrelated = self.output / "odt" / "reader-notes.txt"
        unrelated.write_text("Not a generated chapter document.\n")
        self.make("clean-odt")
        for path in [*self.odts, *self.chapter_inputs, *self.raw_html[1:],
                     *(Path(str(path) + ".d") for path in self.chapter_inputs)]:
            self.assertFalse(path.exists(), f"Generated chapter artifact remains: {path}")
        self.assertEqual(self.snapshot(preserved_paths), preserved)
        self.assertEqual(unrelated.read_text(), "Not a generated chapter document.\n")
        self.make("odt")
        self.assertEqual(self.snapshot(preserved_paths), preserved)
        self.assertTrue(all(path.is_file() for path in self.odts))

    def test_clean_removes_only_generated_files_within_isolated_project(self):
        self.build()
        self.make("pdf")
        generated = self.output_files()
        unrelated = [self.output / "reader-notes.txt", self.assets / "keep-me.txt",
                     self.output / "odt" / "reader-notes.txt",
                     self.output / "chapters" / "reader-notes.txt"]
        for path in unrelated:
            path.write_text("Unrelated contents must survive clean.\n")
        untouched = self.snapshot(unrelated)
        self.make("clean")
        for path in generated:
            self.assertFalse(path.exists(), f"Generated file remains after clean: {path}")
        self.assertEqual(self.snapshot(unrelated), untouched)
        self.assertEqual(set(self.output_files()), set(unrelated))
        self.assert_originals_unchanged()


if __name__ == "__main__":
    unittest.main()
