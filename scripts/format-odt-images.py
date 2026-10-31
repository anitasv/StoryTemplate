#!/usr/bin/env python3
"""Center image-only ODT paragraphs and fit their frames inside page margins."""
import argparse
from io import BytesIO
from pathlib import Path
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile

NS = {
    'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
    'style': 'urn:oasis:names:tc:opendocument:xmlns:style:1.0',
    'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
    'draw': 'urn:oasis:names:tc:opendocument:xmlns:drawing:1.0',
    'fo': 'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0',
    'svg': 'urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0',
}

def key(prefix, name):
    return '{' + NS[prefix] + '}' + name

def inches(value):
    match = re.fullmatch(r'([0-9.]+)(in|cm|mm|pt)', value)
    if match is None:
        raise ValueError(f'Unsupported ODT length: {value}')
    return float(match[1]) * {'in': 1, 'cm': 1/2.54, 'mm': 1/25.4, 'pt': 1/72}[match[2]]

def format_images(path):
    path = Path(path).resolve()
    with zipfile.ZipFile(path) as archive:
        entries = [(item, archive.read(item.filename)) for item in archive.infolist()]
    data = dict((item.filename, payload) for item, payload in entries)
    for name in ('styles.xml', 'content.xml'):
        for _, (prefix, uri) in ET.iterparse(BytesIO(data[name]), events=['start-ns']):
            if not re.fullmatch(r'ns\d+', prefix):
                ET.register_namespace(prefix, uri)
    styles = ET.fromstring(data['styles.xml'])
    content = ET.fromstring(data['content.xml'])
    properties = styles.find('.//style:page-layout-properties', NS)
    # Pandoc's default page layout; use its explicit dimensions/margins when present.
    def length(name, default):
        return inches(properties.get(key('fo', name), default)) if properties is not None else inches(default)
    width = length('page-width', '8.5in') - length('margin-left', '1in') - length('margin-right', '1in')
    height = length('page-height', '11in') - length('margin-top', '1in') - length('margin-bottom', '1in')
    if width <= 0 or height <= 0:
        raise ValueError('ODT page margins leave no space for images')
    auto = content.find('office:automatic-styles', NS)
    if auto is None:
        auto = ET.SubElement(content, key('office', 'automatic-styles'))
    existing = {node.get(key('style', 'name')) for node in auto}
    replacements = {}
    count = 0
    for paragraph in content.findall('.//text:p', NS):
        frames = paragraph.findall('.//draw:frame', NS)
        if not frames or any(text.strip() for text in paragraph.itertext()):
            continue  # Leave mixed prose/image paragraphs alone.
        parent = paragraph.get(key('text', 'style-name'), 'Standard')
        if parent not in replacements:
            name = 'CenteredIllustration' + str(len(replacements) + 1)
            while name in existing:
                name += '_'
            existing.add(name)
            style = ET.SubElement(auto, key('style', 'style'), {
                key('style', 'name'): name, key('style', 'family'): 'paragraph',
                key('style', 'parent-style-name'): parent,
            })
            ET.SubElement(style, key('style', 'paragraph-properties'), {
                key('fo', 'text-align'): 'center', key('fo', 'margin-left'): '0in',
                key('fo', 'margin-right'): '0in', key('fo', 'text-indent'): '0in',
            })
            replacements[parent] = name
        paragraph.set(key('text', 'style-name'), replacements[parent])
        for frame in frames:
            if frame.find('draw:image', NS) is None:
                continue
            frame.set(key('text', 'anchor-type'), 'as-char')
            w, h = frame.get(key('svg', 'width')), frame.get(key('svg', 'height'))
            if w and h:
                w, h = inches(w), inches(h)
                # Leave space for the containing paragraph's line spacing.
                scale = min(1, width / w, (height - 0.25) / h)
                frame.set(key('svg', 'width'), f'{w * scale:.6f}in')
                frame.set(key('svg', 'height'), f'{h * scale:.6f}in')
            count += 1
    data['content.xml'] = ET.tostring(content, encoding='utf-8', xml_declaration=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix='.odt')
    os.close(descriptor)
    temporary = Path(temporary)
    assert temporary.resolve().parent == path.parent
    try:
        with zipfile.ZipFile(temporary, 'w') as archive:
            for item, original in entries:
                archive.writestr(item, data.get(item.filename, original))
        assert path.resolve().parent == temporary.resolve().parent
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            assert temporary.resolve().parent == path.parent
            temporary.unlink()
    print(f'Centered {count} ODT illustrations: {path.name}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('odt', type=Path)
    format_images(parser.parse_args().odt)
