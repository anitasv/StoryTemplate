# Main Typst entry file and output PDF
OUTPUT := output
PRINT  := print.typ
EBOOK  := ebook.typ
NAME   := Test_Title
PDF    := $(OUTPUT)/$(NAME).pdf
EPUB   := $(OUTPUT)/$(NAME).epub
HTML   := $(OUTPUT)/$(NAME).html

# Typst CLI command (override with: make TYPST=/path/to/typst)
TYPST     ?= typst

# Collect all .typ files recursively so that any change triggers a rebuild.
# Use recursive expansion (=) so this is re-evaluated each `make` invocation.
# Ensure stable alphabetical ordering.
TYP_SOURCES = $(shell LC_ALL=C find chapters -name '*.typ' -print | sort)

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
$(PDF): $(PRINT) $(CHAPTERS_STAMP)
	mkdir -p $(OUTPUT)
	$(TYPST) compile $(PRINT) $(PDF)

html: $(HTML)

$(HTML): $(EBOOK) $(CHAPTERS_STAMP)
	mkdir -p $(OUTPUT)
	$(TYPST) compile --features html $(EBOOK) $(HTML)

# Update the stamp when any chapter file changes (or is added/removed).
# We compute a content hash over all chapter sources in a stable order.

# Note: `.PHONY` here forces this recipe to run, but because the stamp file is
# only updated when the hash changes, downstream targets won’t rebuild unless
# chapter contents actually changed.
.PHONY: chapters-stamp
chapters-stamp: $(CHAPTERS_STAMP)

# Update the stamp only when inputs are newer (standard make behavior).
# This makes `make` a true no-op when nothing changed, while still triggering
# rebuilds whenever any chapter file changes.
$(CHAPTERS_STAMP): $(TYP_SOURCES)
	mkdir -p $(OUTPUT)
	( LC_ALL=C find chapters -name '*.typ' -print0 \
	  | sort -z \
	  | xargs -0 shasum \
	  | shasum \
	  | awk '{print $$1}' > $@.tmp )
	@cmp -s $@.tmp $@ 2>/dev/null || mv $@.tmp $@
	@rm -f $@.tmp

epub: $(EPUB)

$(EPUB): $(HTML) styles/metadata.yaml styles/epub.css
	pandoc $(HTML) \
	  --from=html --to=epub \
	  --epub-cover-image=images/cover.png \
	  --metadata-file=styles/metadata.yaml \
	  --css=styles/epub.css \
	  --output $(EPUB)

# -------- ODT (one per chapter) --------

ODT_DIR := $(OUTPUT)/odt
ODT_PANDOC_FILTER := scripts/pandoc/odt-image-width.lua
CHAPTERS := $(basename $(notdir $(TYP_SOURCES)))
CHAPTER_HTML := $(addprefix $(OUTPUT)/chapters/,$(addsuffix .html,$(CHAPTERS)))
CHAPTER_ODT := $(addprefix $(ODT_DIR)/,$(addsuffix .odt,$(CHAPTERS)))

# Build all chapter ODTs
odt: $(CHAPTER_ODT)

# Compile each chapter .typ to standalone HTML first
$(OUTPUT)/chapters/%.html: chapters/%.typ
	mkdir -p $(OUTPUT)/chapters
	$(TYPST) compile --root . --features html $< $@

# Convert chapter HTML to ODT
$(ODT_DIR)/%.odt: $(OUTPUT)/chapters/%.html
	mkdir -p $(ODT_DIR)
	pandoc $< --from=html --to=odt \
	  --lua-filter=$(ODT_PANDOC_FILTER) \
	  --output $@

# Remove generated files
clean:
	rm -f $(PDF) $(EPUB) $(HTML) $(CHAPTERS_STAMP)
	rmdir $(OUTPUT)

clean-odt:
	rm -f $(CHAPTER_ODT)
	-rmdir $(ODT_DIR) 2>/dev/null || true
	-rmdir $(OUTPUT)/chapters 2>/dev/null || true

# Print total word count of the novel (.typ sources)
wc: $(CHAPTERS_STAMP)
	wc -w $(TYP_SOURCES)
