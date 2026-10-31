"""Check real Pandoc ODT image centering without altering prose or image bytes."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('odt_images', ROOT / 'scripts/format-odt-images.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

@unittest.skipUnless(shutil.which('pandoc'), 'Pandoc required')
class AlignmentTests(unittest.TestCase):
    def test_centered_scaled_images_preserve_prose_and_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            from PIL import Image
            image = root / 'scene.png'
            Image.new('RGB', (1024, 1536), 'blue').save(image)
            html = root / 'book.html'
            html.write_text(f'<p>Before.</p><p><img src="{image}"></p><p>After.</p>')
            odt = root / 'book.odt'
            subprocess.run(['pandoc', str(html), '-o', str(odt)], check=True)
            with zipfile.ZipFile(odt) as archive:
                before = {name: archive.read(name) for name in archive.namelist()}
            MODULE.format_images(odt)
            with zipfile.ZipFile(odt) as archive:
                self.assertIsNone(archive.testzip())
                for name, data in before.items():
                    if name != 'content.xml':
                        self.assertEqual(archive.read(name), data)
                content = ET.fromstring(archive.read('content.xml'))
            ns = MODULE.NS
            styles = {node.get(MODULE.key('style', 'name')): node
                      for node in content.findall('.//style:style', ns)}
            paragraphs = content.findall('.//text:p', ns)
            self.assertEqual([''.join(p.itertext()) for p in paragraphs if ''.join(p.itertext())],
                             ['Before.', 'After.'])
            for paragraph in paragraphs:
                frame = paragraph.find('draw:frame', ns)
                if frame is None:
                    continue
                style = styles[paragraph.get(MODULE.key('text', 'style-name'))]
                props = style.find('style:paragraph-properties', ns)
                self.assertEqual(props.get(MODULE.key('fo', 'text-align')), 'center')
                self.assertEqual(frame.get(MODULE.key('text', 'anchor-type')), 'as-char')
                width = MODULE.inches(frame.get(MODULE.key('svg', 'width')))
                height = MODULE.inches(frame.get(MODULE.key('svg', 'height')))
                self.assertLessEqual(width, 6.5)
                self.assertLessEqual(height, 9)
                self.assertAlmostEqual(width / height, 2/3, places=5)

if __name__ == '__main__':
    unittest.main()
