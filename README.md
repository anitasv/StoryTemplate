# StoryTemplate

A minimal template for writing novels with [Typst](https://typst.app/).

## Install / create your own repo

Start here:

- **docs/INSTALL.md** — recommended one-command bootstrap (curl) to create your own novel folder + Git repo.

If you want to keep an `upstream` remote for pulling template updates, see **docs/CONTRIBUTE.md**.

## Prerequisites

You’ll need the following tools installed locally:

1) **Typst** (required) — compiles the `.typ` sources to PDF/HTML.

- Website: https://typst.app/
- Install instructions: https://github.com/typst/typst#installation

2) **Pandoc** (required for EPUB + ODT) — converts the generated HTML into EPUB, and (optionally) chapter ODT files.

- Website: https://pandoc.org/
- Install instructions: https://pandoc.org/installing.html

3) **make** (recommended) — runs the build recipes in the included `Makefile`.

- Usually preinstalled on macOS/Linux.
- On Windows, consider using WSL.

## Quick start

If you haven’t yet, follow **docs/INSTALL.md** first.

### One-command project creation (recommended)

This will:

- prompt you for your novel title/author/etc.
- create a new folder (default is CamelCase derived from the title)
- clone the template into it
- remove the template’s git history and initialize a fresh repo

```sh
curl -fsSL https://raw.githubusercontent.com/anitasv/StoryTemplate/main/scripts/bootstrap.sh | bash
```

1) Edit your manuscript:

- `story.typ` includes your chapters
- `chapters/chapter1.typ` is an example chapter file

2) Set your book metadata (title/author/etc.):

```sh
./scripts/template-init.sh
```

This updates:

- `styles/metadata.yaml` (EPUB/Pandoc metadata)
- `print.typ` (`book_title` / `book_author` used for the title page)

It also updates:

- `Makefile` (`NAME := ...`) so generated output filenames match your book title.

## Initialize / update the template (`template-init.sh`)

Run this any time you want to change the title/author/language/rights across outputs.

### Interactive usage

From the repo root:

```sh
./scripts/template-init.sh
```

You’ll be prompted for:

- Title
- Author
- Language (BCP-47 tag like `en` or `en-US`)
- Rights

### Non-interactive usage

```sh
./scripts/template-init.sh \
  --title "My Awesome Novel" \
  --author "My Pen Name" \
  --language en \
  --rights "All rights reserved"
```

### Show current values

```sh
./scripts/template-init.sh --show
```

## Build

If you have `typst` installed, you can build outputs via the provided `Makefile`.

All build outputs go into `output/`.

### Common `make` commands

Build everything (PDF + HTML + EPUB):

```sh
make
```

Build PDF (print layout):

```sh
make pdf
```

Build HTML (ebook layout, used as the source for EPUB):

```sh
make html
```

Build EPUB (requires `pandoc`):

```sh
make epub
```

Build chapter ODT files (one `.odt` per `chapters/*.typ`, requires `pandoc`):

```sh
make odt
```

Print word count across all `chapters/*.typ`:

```sh
make wc
```

Clean generated files:

```sh
make clean
make clean-odt
```

### Build outputs directly

You can also build individual files directly (these are defined in the `Makefile`):

```sh
make print.pdf
```

### Overriding the Typst binary

If `typst` isn’t on your PATH, you can override it:

```sh
make pdf TYPST=/path/to/typst
```

## Writing / editing chapters

### Where the manuscript lives

- **Chapters:** add/edit files in `chapters/` (e.g. `chapters/chapter2.typ`).
- **Chapter list / ordering:** `story.typ` is the “table of contents” for Typst. It `#include`s chapter files in the order they should appear.
- **Print entrypoint:** `print.typ` (cover + title page + includes `story.typ`).
- **Ebook entrypoint:** `ebook.typ` (currently just includes `story.typ`).

### Typical workflow for adding a new chapter

1) Create a new file, e.g. `chapters/chapter2.typ`.
2) Add it to `story.typ`:

```typst
// Include chapters
#include "chapters/chapter1.typ"
#include "chapters/chapter2.typ"
```

3) Rebuild:

```sh
make pdf
```

## Metadata, cover image, and styles

- **Book metadata:** `styles/metadata.yaml` (used by Pandoc for EPUB metadata)
- **Title page variables:** `print.typ` (`#let book_title = ...`, `#let book_author = ...`)
- **Cover image:** `images/cover.png`
- **EPUB CSS:** `styles/epub.css`

## Other documentation

Additional project docs live in `docs/`:

- `docs/WRITING_INSTRUCTIONS.md` — writing style instructions, mainly intended for LLMs.
- `docs/OUTLINE.md` — story outline notes
- `docs/CHARACTERS.md` — character notes
