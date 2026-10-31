#!/usr/bin/env python3
"""Prepare shared, cached images and lightweight HTML for EPUB/ODT exports.

Original images and standalone HTML are never modified. Only opaque,
continuous-tone PNGs are candidates for JPEG; transparency, animation, simple
palette graphics, and already-compressed formats are preserved byte-for-byte.
"""

import argparse
import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote

try:
    import PIL
    from PIL import Image, ImageFile, ImageOps
except ImportError as error:
    raise SystemExit("Image preparation requires Pillow: python3 -m pip install -r requirements-images.txt") from error


IMAGE_URL = re.compile(
    rb"(?P<quote>[\"'])data:image/(?P<format>png|jpeg|gif|webp|svg\+xml);base64,"
    rb"(?P<data>[^\"']*)(?P=quote)"
)
EXTENSIONS = {b"png": ".png", b"jpeg": ".jpg", b"gif": ".gif",
              b"webp": ".webp", b"svg+xml": ".svg"}
DEFAULT_SETTINGS = {"quality": 85, "max_dimension": 1600}
CACHE_VERSION = 1


def validate_settings(settings):
    if set(settings) != set(DEFAULT_SETTINGS):
        raise ValueError("Image settings must contain only quality and max_dimension")
    quality = settings["quality"]
    if quality is not None and (type(quality) is not int or not 1 <= quality <= 95):
        raise ValueError("quality must be an integer from 1 to 95, or null for lossless extraction")
    if type(settings["max_dimension"]) is not int or settings["max_dimension"] < 1:
        raise ValueError("max_dimension must be a positive integer")
    return settings


def atomic_write(path, data, *, if_changed=False):
    """Publish complete files, including when parallel exports share the cache."""
    path = Path(path)
    parent = path.parent.resolve()
    # Do not follow a destination symlink outside the intended output directory.
    if path.is_symlink() or path.resolve() != parent / path.name:
        raise ValueError(f"Unsafe output path: {path}")
    if if_changed and path.exists() and path.read_bytes() == data:
        return
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary = Path(temporary)
    assert temporary.resolve().parent == parent
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            assert temporary.resolve().parent == parent
            temporary.unlink()


def jpeg_candidate(data, quality, max_dimension):
    """Return a smaller JPEG, or None when retaining the original is safer."""
    with Image.open(BytesIO(data)) as original:
        if original.format != "PNG":
            raise ValueError("An image declared as PNG is not a PNG")
        if getattr(original, "is_animated", False):
            return None
        if "A" in original.getbands() or "transparency" in original.info:
            if original.convert("RGBA").getextrema()[3] != (255, 255):
                return None
        image = ImageOps.exif_transpose(original).convert("RGB")
        # Preserve logos, diagrams, and limited-palette artwork losslessly.
        if image.getcolors(maxcolors=256) is not None:
            return None
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
        output = BytesIO()
        # Pillow's default buffer can be too small for optimized 4:4:4 JPEGs
        # with high-entropy detail (notably when writing to BytesIO).
        ImageFile.MAXBLOCK = max(ImageFile.MAXBLOCK, image.width * image.height * 4)
        image.save(output, format="JPEG", quality=quality, optimize=True,
                   progressive=True, subsampling=0,
                   icc_profile=original.info.get("icc_profile"))
        jpeg = output.getvalue()
    return jpeg if len(jpeg) < len(data) else None


def prepare_image(data, image_format, assets, *, quality=85, max_dimension=1600):
    settings = validate_settings({"quality": quality, "max_dimension": max_dimension})
    assets = Path(assets)
    assets.mkdir(parents=True, exist_ok=True)
    options = dict(settings, version=CACHE_VERSION, pillow=PIL.__version__,
                   format=image_format.decode("ascii"))
    digest = hashlib.sha256(json.dumps(options, sort_keys=True).encode() + b"\0")
    digest.update(data)
    key = digest.hexdigest()
    extension = EXTENSIONS[image_format]
    record_path = assets / f"{key}.json"
    # A record lets both formats reuse a conversion without decoding the PNG.
    # Check the output hash as well, so interrupted/corrupt caches self-repair.
    try:
        record = json.loads(record_path.read_text())
        if record["file"] in {key + extension, key + ".jpg"}:
            cached = assets / record["file"]
            if hashlib.sha256(cached.read_bytes()).hexdigest() == record["sha256"]:
                return cached
    except (OSError, ValueError, KeyError, TypeError):
        pass

    result = data
    if quality is not None and image_format == b"png":
        jpeg = jpeg_candidate(data, quality, max_dimension)
        if jpeg is not None:
            result, extension = jpeg, ".jpg"
    target = assets / (key + extension)
    atomic_write(target, result, if_changed=True)
    record = {"file": target.name, "sha256": hashlib.sha256(result).hexdigest()}
    atomic_write(record_path, (json.dumps(record, sort_keys=True) + "\n").encode(), if_changed=True)
    return target


def make_escape(path):
    return str(path).replace("\\", "\\\\").replace("$", "$$").replace("#", "\\#").replace(" ", "\\ ").replace(":", "\\:")


def write_dependencies(destination, assets):
    """Let make detect individual missing assets, not just a removed cache."""
    paths = sorted(set(assets))
    content = make_escape(destination) + ": " + " ".join(map(make_escape, paths)) + "\n"
    # Empty rules permit recovery when a cached asset is missing.
    content += "".join(make_escape(path) + ":\n" for path in paths)
    atomic_write(Path(str(destination) + ".d"), content.encode())


def externalize(source, destination, *, assets=None, quality=85, max_dimension=1600,
                dependencies=False):
    source = Path(source)
    destination = Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Prepared input must be separate from the standalone HTML")
    validate_settings({"quality": quality, "max_dimension": max_dimension})
    assets = Path(assets) if assets is not None else destination.parent / "document-assets"
    document = source.read_bytes()
    used = []
    count = 0

    def extract(match):
        nonlocal count
        payload = re.sub(rb"\s+", b"", match["data"])
        data = base64.b64decode(payload, validate=True)
        target = prepare_image(data, match["format"], assets,
                               quality=quality, max_dimension=max_dimension)
        used.append(target)
        relative = Path(os.path.relpath(target, destination.parent)).as_posix()
        count += 1
        return match["quote"] + quote(relative, safe="/").encode("ascii") + match["quote"]

    result = IMAGE_URL.sub(extract, document)
    if dependencies:
        write_dependencies(destination, used)
    # Write last even if identical: make must see the source was processed.
    atomic_write(destination, result)
    print(f"Prepared HTML: {len(document):,} -> {len(result):,} bytes; "
          f"{count} image references ({len(set(used))} unique cached images)")
    return used


def prepare_file(source, destination, *, assets, quality=85, max_dimension=1600,
                 dependencies=False):
    """Write the prepared cover's actual filename (JPEG or lossless original)."""
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("Image path manifest must be separate from the original image")
    formats = {extension: mime for mime, extension in EXTENSIONS.items()}
    formats[".jpeg"] = b"jpeg"
    image_format = formats[source.suffix.lower()]
    target = prepare_image(source.read_bytes(), image_format, assets,
                           quality=quality, max_dimension=max_dimension)
    if dependencies:
        write_dependencies(destination, [target])
    atomic_write(destination, (str(target) + "\n").encode())
    print(f"Prepared image: {source} -> {target}")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("html", "image"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--dependencies", action="store_true")
    args = parser.parse_args()
    try:
        settings = DEFAULT_SETTINGS if args.config is None else json.loads(args.config.read_text())
        validate_settings(settings)
        function = externalize if args.mode == "html" else prepare_file
        function(args.source, args.destination, assets=args.assets,
                 dependencies=args.dependencies, **settings)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Image preparation failed: {error}\n")


if __name__ == "__main__":
    main()
