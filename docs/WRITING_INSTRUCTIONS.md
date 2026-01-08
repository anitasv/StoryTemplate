# Writing Instructions

## Template setup (title/author/metadata)

This repo is intended to be a re-usable template. Before you export/print, set your book metadata.

Interactive (recommended):

```sh
./scripts/template-init.sh
```

Non-interactive:

```sh
./scripts/template-init.sh \
  --title "My Awesome Novel" \
  --author "My Pen Name" \
  --language en \
  --rights "All rights reserved"
```

Show current values:

```sh
./scripts/template-init.sh --show
```