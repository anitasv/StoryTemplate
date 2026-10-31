# Main Typst entry file and output PDF
OUTPUT := output
PRINT  := print.typ
EBOOK  := ebook.typ
NAME   := Test_Title
PDF    := $(OUTPUT)/$(NAME).pdf
EPUB   := $(OUTPUT)/$(NAME).epub
HTML   := $(OUTPUT)/$(NAME).html
EPUB_HTML := $(OUTPUT)/$(NAME).epub-input.html
DOCUMENT_ASSETS := $(OUTPUT)/document-assets
DOCUMENT_CACHE_STAMP := $(DOCUMENT_ASSETS)/.ready
DOCUMENT_IMAGE_SCRIPT := scripts/prepare-document-images.py
DOCUMENT_IMAGE_CONFIG := styles/image-export.json
DOCUMENT_IMAGE_OPTIONS = --assets "$(DOCUMENT_ASSETS)" --config "$(DOCUMENT_IMAGE_CONFIG)" --dependencies
EPUB_COVER := $(OUTPUT)/epub-cover.path
PYTHON ?= python3

# Remove a failed conversion rather than leaving a seemingly up-to-date EPUB.
.DELETE_ON_ERROR:

# Typst CLI command (override with: make TYPST=/path/to/typst)
TYPST     ?= typst

# Collect all .typ files recursively so that any change triggers a rebuild.
# Use recursive expansion (=) so this is re-evaluated each `make` invocation.
# Ensure stable alphabetical ordering.
TYP_SOURCES = $(shell LC_ALL=C find chapters -name '*.typ' -print | sort)

# Track chapter illustrations as well as the cover for image-only rebuilds.
IMAGE_SOURCES = $(wildcard images/*.png images/*.jpg images/*.jpeg images/*.gif images/*.webp images/*.svg)
SHARED_TYP_SOURCES = $(filter-out $(PRINT) $(EBOOK),$(wildcard *.typ))

# A stamp file that changes whenever chapter contents change.
# This makes rebuilds robust even if mtimes aren’t updated as expected.
CHAPTERS_STAMP := $(OUTPUT)/.chapters.stamp

.PHONY: all clean wc

.PHONY: pdf epub html

.PHONY: odt clean-odt

# Default target: build the PDF
all: $(PDF) $(HTML) $(EPUB)

pdf: $(PDF)

# Rebuild the PDF if any .typ file has changed
$(PDF): $(PRINT) $(SHARED_TYP_SOURCES) $(IMAGE_SOURCES) $(CHAPTERS_STAMP)
	mkdir -p $(OUTPUT)
	$(TYPST) compile $(PRINT) $(PDF)

html: $(HTML)

$(HTML): $(EBOOK) $(SHARED_TYP_SOURCES) $(IMAGE_SOURCES) $(CHAPTERS_STAMP)
	mkdir -p $(OUTPUT)
	$(TYPST) compile --features html $(EBOOK) $(HTML)

# Update the stamp when any chapter file changes (or is added/removed).
# We compute a content hash over all chapter sources in a stable order.

# Check additions, removals and content changes, without touching an unchanged stamp.
.PHONY: chapters-stamp FORCE_CHAPTERS_STAMP
chapters-stamp: $(CHAPTERS_STAMP)
FORCE_CHAPTERS_STAMP:
$(CHAPTERS_STAMP): FORCE_CHAPTERS_STAMP
	mkdir -p $(OUTPUT)
	( LC_ALL=C find chapters -name '*.typ' -print0 \
	  | sort -z \
	  | xargs -0 shasum \
	  | shasum \
	  | awk '{print $$1}' > $@.tmp )
	@cmp -s $@.tmp $@ 2>/dev/null || mv $@.tmp $@
	@rm -f $@.tmp

epub: $(EPUB)

# Both formats share immutable, content-addressed image derivatives.
# The stamp changes only when the entire cache is recreated; adding an image
# must not invalidate all other prepared HTML files.
$(DOCUMENT_CACHE_STAMP):
	mkdir -p "$(DOCUMENT_ASSETS)"
	touch "$@"

$(EPUB_HTML): $(HTML) $(DOCUMENT_IMAGE_SCRIPT) $(DOCUMENT_IMAGE_CONFIG) $(DOCUMENT_CACHE_STAMP)
	$(PYTHON) $(DOCUMENT_IMAGE_SCRIPT) html "$(HTML)" "$@" $(DOCUMENT_IMAGE_OPTIONS)

$(EPUB_COVER): images/cover.png $(DOCUMENT_IMAGE_SCRIPT) $(DOCUMENT_IMAGE_CONFIG) $(DOCUMENT_CACHE_STAMP)
	$(PYTHON) $(DOCUMENT_IMAGE_SCRIPT) image "$<" "$@" $(DOCUMENT_IMAGE_OPTIONS)

$(EPUB): $(EPUB_HTML) $(EPUB_COVER) styles/metadata.yaml styles/epub.css
	@IFS= read -r cover < "$(EPUB_COVER)"; \
	pandoc "$(EPUB_HTML)" \
	  --from=html --to=epub \
	  --resource-path="$(OUTPUT):." \
	  --epub-cover-image="$$cover" \
	  --metadata-file=styles/metadata.yaml \
	  --css=styles/epub.css \
	  --output "$(EPUB)"

# -------- ODT (one per chapter) --------

ODT_DIR := $(OUTPUT)/odt
ODT_PANDOC_FILTER := scripts/pandoc/odt-image-width.lua
CHAPTERS := $(basename $(notdir $(TYP_SOURCES)))
CHAPTER_HTML := $(addprefix $(OUTPUT)/chapters/,$(addsuffix .html,$(CHAPTERS)))
CHAPTER_ODT := $(addprefix $(ODT_DIR)/,$(addsuffix .odt,$(CHAPTERS)))
CHAPTER_ODT_HTML := $(addprefix $(OUTPUT)/odt-input/,$(addsuffix .html,$(CHAPTERS)))

# Keep expensive intermediates between builds rather than letting make delete them.
.SECONDARY: $(CHAPTER_HTML) $(CHAPTER_ODT_HTML)

# Generated dependencies regenerate prepared inputs if individual assets vanish.
-include $(wildcard $(EPUB_HTML).d $(EPUB_COVER).d $(addsuffix .d,$(CHAPTER_ODT_HTML)))

# Build all chapter ODTs
odt: $(CHAPTER_ODT)

# Compile each chapter .typ to standalone HTML first
$(OUTPUT)/chapters/%.html: chapters/%.typ $(SHARED_TYP_SOURCES) $(IMAGE_SOURCES)
	mkdir -p $(OUTPUT)/chapters
	$(TYPST) compile --root . --features html $< $@

# Externalize/compress chapter images using the same cache as EPUB.
$(OUTPUT)/odt-input/%.html: $(OUTPUT)/chapters/%.html $(DOCUMENT_IMAGE_SCRIPT) $(DOCUMENT_IMAGE_CONFIG) $(DOCUMENT_CACHE_STAMP)
	$(PYTHON) $(DOCUMENT_IMAGE_SCRIPT) html "$<" "$@" $(DOCUMENT_IMAGE_OPTIONS)

# Convert the small, linked-image input rather than base64-heavy chapter HTML.
$(ODT_DIR)/%.odt: $(OUTPUT)/odt-input/%.html $(ODT_PANDOC_FILTER) scripts/format-odt-images.py
	mkdir -p "$(ODT_DIR)"
	pandoc "$<" --from=html --to=odt \
	  --resource-path="$(OUTPUT)/odt-input:$(OUTPUT)/chapters:." \
	  --lua-filter=$(ODT_PANDOC_FILTER) \
	  --output "$@"
	$(PYTHON) scripts/format-odt-images.py "$@"

# Remove generated files only; clean-odt preserves the cache shared with EPUB.
clean: clean-odt
	rm -f $(PDF) $(EPUB) $(HTML) $(EPUB_HTML) $(EPUB_HTML).d $(EPUB_COVER) $(EPUB_COVER).d $(CHAPTERS_STAMP)
	rm -f "$(DOCUMENT_ASSETS)"/*.png "$(DOCUMENT_ASSETS)"/*.jpg "$(DOCUMENT_ASSETS)"/*.gif "$(DOCUMENT_ASSETS)"/*.webp "$(DOCUMENT_ASSETS)"/*.svg "$(DOCUMENT_ASSETS)"/*.json "$(DOCUMENT_CACHE_STAMP)"
	-rmdir "$(DOCUMENT_ASSETS)" 2>/dev/null || true
	-rmdir "$(OUTPUT)" 2>/dev/null || true

clean-odt:
	rm -f $(CHAPTER_ODT) $(CHAPTER_HTML) $(CHAPTER_ODT_HTML) $(addsuffix .d,$(CHAPTER_ODT_HTML))
	-rmdir "$(ODT_DIR)" 2>/dev/null || true
	-rmdir "$(OUTPUT)/chapters" 2>/dev/null || true
	-rmdir "$(OUTPUT)/odt-input" 2>/dev/null || true

# Print total word count of the novel (.typ sources)
wc: $(CHAPTERS_STAMP)
	wc -w $(TYP_SOURCES)
