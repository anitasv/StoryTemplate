# StoryTemplate

A minimal template for writing novels with [Typst](https://typst.app/).

## Bootstrap (create your own novel repo)

Recommended one-command project creation (creates a new folder + fresh Git repo):

```sh
curl -fsSL https://raw.githubusercontent.com/anitasv/StoryTemplate/main/scripts/bootstrap.sh | bash
```

On **macOS**, the bootstrap script will also offer to install missing prerequisites
(Homebrew, Typst, Pandoc). It will skip anything that’s already installed.

Then:

```sh
cd YourProjectFolder
make pdf
```

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

### What to edit first

- `chapters/` — your manuscript content (start with `chapters/chapter1.typ`)
- `story.typ` — chapter ordering (includes chapters in order)
- `print.typ` — print/PDF entrypoint (cover + title page + includes `story.typ`)
- `ebook.typ` — ebook/HTML entrypoint (includes `story.typ`)

Build a PDF:

```sh
make pdf
```

Note: the bootstrap script runs `./scripts/template-init.sh` and stamps your
title/author/language/rights into `styles/metadata.yaml`, `print.typ`, and the
`Makefile` output name.

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

