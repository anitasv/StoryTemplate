#!/bin/sh
# Initialize/update StoryTemplate metadata in a dependency-free way.
#
# Updates:
# - styles/metadata.yaml (Pandoc/EPUB metadata)
# - print.typ (title/author variables)
#
# Usage:
#   scripts/template-init.sh                # interactive
#   scripts/template-init.sh --show         # print current values
#   scripts/template-init.sh --title "..." --author "..." [--language en] [--rights "..."]
#
# Notes:
# - Uses only POSIX shell + standard tools (sed, awk, grep, mv).
# - In-place updates are done via temp files for safety.

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
META_FILE="$ROOT_DIR/styles/metadata.yaml"
PRINT_FILE="$ROOT_DIR/print.typ"
MAKEFILE="$ROOT_DIR/Makefile"

die() { echo "error: $*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
StoryTemplate initializer

Interactive:
  scripts/template-init.sh

Non-interactive:
  scripts/template-init.sh --title "My Novel" --author "My Name" [--language en] [--rights "All rights reserved"]

Other:
  scripts/template-init.sh --show
  scripts/template-init.sh -h|--help
USAGE
}

require_file() {
  [ -f "$1" ] || die "missing file: $1"
}

read_yaml_value() {
  # read_yaml_value <file> <key>
  # prints unquoted value if present (best-effort for simple YAML: key: "value")
  awk -v k="$2" '
    $0 ~ "^[[:space:]]*"k":[[:space:]]*" {
      sub("^[[:space:]]*"k":[[:space:]]*", "");
      gsub(/^"|"[[:space:]]*$/, "");
      print; exit
    }
  ' "$1" 2>/dev/null || true
}

read_typ_value() {
  # read_typ_value <file> <varname>
  # matches: #let var = "..."
  awk -v v="$2" '
    $0 ~ "^#let[[:space:]]+"v"[[:space:]]*=" {
      s=$0
      sub("^#let[[:space:]]+"v"[[:space:]]*=[[:space:]]*\"", "", s)
      sub("\"[[:space:]]*$", "", s)
      print s; exit
    }
  ' "$1" 2>/dev/null || true
}

escape_sed_repl() {
  # Escape for sed replacement string (| delimiter): \ and & and |
  # shellcheck disable=SC2001
  printf '%s' "$1" | sed -e 's/[\\&|]/\\\\&/g'
}

update_yaml_key() {
  # update_yaml_key <file> <key> <value>
  f="$1"; k="$2"; v="$3"
  tmp="$f.tmp"
  esc_v=$(escape_sed_repl "$v")
  # Replace first occurrence of `key: ...` with `key: "value"`.
  # If key not present, insert after `---` line.
  if grep -qE "^[[:space:]]*$k:[[:space:]]*" "$f"; then
    sed -E "0,/^[[:space:]]*$k:[[:space:]]*/ s|^([[:space:]]*$k:)[[:space:]]*.*$|\\1 \"$esc_v\"|" "$f" >"$tmp"
  else
    awk -v k="$k" -v v="$v" '
      NR==1 && $0 ~ /^---[[:space:]]*$/ { print; print k ": \"" v "\""; next }
      { print }
    ' "$f" >"$tmp"
  fi
  mv "$tmp" "$f"
}

update_yaml_key_quoted() {
  # update_yaml_key_quoted <file> <key> <value>
  # Writes: key: "<value>"  (quotes are always present).
  update_yaml_key_raw "$1" "$2" "\"$(yaml_escape "$3")\""
}

yaml_escape() {
  # Escape double quotes inside a value so it can live inside YAML double quotes.
  printf '%s' "$1" | sed -e 's/"/\\"/g'
}

update_yaml_key_raw() {
  # update_yaml_key_raw <file> <key> <raw_value>
  # Like update_yaml_key, but does NOT add additional quoting.
  f="$1"; k="$2"; raw="$3"
  tmp="$f.tmp"
  esc_raw=$(escape_sed_repl "$raw")
  if grep -qE "^[[:space:]]*$k:[[:space:]]*" "$f"; then
    # BSD sed doesn't support the GNU `0,/<re>/` address form.
    # Use an explicit first-match replace via awk (portable).
    awk -v k="$k" -v v="$raw" '
      BEGIN{done=0}
      done==0 && $0 ~ "^[[:space:]]*" k ":[[:space:]]*" { sub($0, k ": " v); done=1 }
      { print }
    ' "$f" >"$tmp"
  else
    awk -v k="$k" -v v="$raw" '
      NR==1 && $0 ~ /^---[[:space:]]*$/ { print; print k ": " v; next }
      { print }
    ' "$f" >"$tmp"
  fi
  mv "$tmp" "$f"
}

update_typ_let() {
  # update_typ_let <file> <varname> <value>
  f="$1"; vname="$2"; v="$3"
  tmp="$f.tmp"
  esc_v=$(escape_sed_repl "$v")
  if grep -qE "^#let[[:space:]]+$vname[[:space:]]*=" "$f"; then
    # BSD sed doesn't support the GNU `0,/<re>/` address form.
    # Use an explicit first-match replace via awk (portable).
    awk -v vn="$vname" -v vv="$v" '
      BEGIN{done=0}
      done==0 && $0 ~ "^#let[[:space:]]+" vn "[[:space:]]*=" {
        print "#let " vn " = \"" vv "\""; done=1; next
      }
      { print }
    ' "$f" >"$tmp"
  else
    # Insert at top if missing.
    {
      printf '#let %s = "%s"\n' "$vname" "$v"
      cat "$f"
    } >"$tmp"
  fi
  mv "$tmp" "$f"
}

show_current() {
  require_file "$META_FILE"
  require_file "$PRINT_FILE"
  title=$(read_yaml_value "$META_FILE" title)
  author=$(read_yaml_value "$META_FILE" creator)
  lang=$(read_yaml_value "$META_FILE" language)
  rights=$(read_yaml_value "$META_FILE" rights)
  ptitle=$(read_typ_value "$PRINT_FILE" book_title)
  pauthor=$(read_typ_value "$PRINT_FILE" book_author)
  cat <<EOF
Current values:
  metadata.yaml title:    ${title:-<missing>}
  metadata.yaml creator:  ${author:-<missing>}
  metadata.yaml language: ${lang:-<missing>}
  metadata.yaml rights:   ${rights:-<missing>}
  print.typ book_title:   ${ptitle:-<missing>}
  print.typ book_author:  ${pauthor:-<missing>}
EOF
}

prompt() {
  # prompt <label> <default>  -> echoes chosen value
  label="$1"; def="$2"
  if [ -n "$def" ]; then
    printf '%s [%s]: ' "$label" "$def" >&2
  else
    printf '%s: ' "$label" >&2
  fi
  IFS= read -r ans || ans=""
  if [ -z "$ans" ]; then
    printf '%s' "$def"
  else
    printf '%s' "$ans"
  fi
}

TITLE=""
AUTHOR=""
LANGUAGE=""
RIGHTS=""
MODE="interactive"

while [ $# -gt 0 ]; do
  case "$1" in
    --show) MODE="show"; shift ;;
    --title) TITLE=${2-}; shift 2 ;;
    --author|--creator) AUTHOR=${2-}; shift 2 ;;
    --language|--lang) LANGUAGE=${2-}; shift 2 ;;
    --rights) RIGHTS=${2-}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1 (use --help)" ;;
  esac
done

require_file "$META_FILE"
require_file "$PRINT_FILE"
require_file "$MAKEFILE"

if [ "$MODE" = "show" ]; then
  show_current
  exit 0
fi

cur_title=$(read_yaml_value "$META_FILE" title)
cur_author=$(read_yaml_value "$META_FILE" creator)
cur_lang=$(read_yaml_value "$META_FILE" language)
cur_rights=$(read_yaml_value "$META_FILE" rights)

if [ -z "$TITLE" ] && [ -z "$AUTHOR" ] && [ -z "$LANGUAGE" ] && [ -z "$RIGHTS" ]; then
  # interactive
  TITLE=$(prompt "Book title" "${cur_title:-My Awesome Novel}")
  AUTHOR=$(prompt "Author / pen name" "${cur_author:-My Pen Name}")
  LANGUAGE=$(prompt "Language (BCP-47, e.g. en, en-US)" "${cur_lang:-en}")
  RIGHTS=$(prompt "Rights" "${cur_rights:-All rights reserved}")
else
  # non-interactive: apply defaults for unspecified values
  : "${TITLE:=${cur_title:-My Awesome Novel}}"
  : "${AUTHOR:=${cur_author:-My Pen Name}}"
  : "${LANGUAGE:=${cur_lang:-en}}"
  : "${RIGHTS:=${cur_rights:-All rights reserved}}"
fi

update_yaml_key_quoted "$META_FILE" title "$TITLE"
update_yaml_key_quoted "$META_FILE" creator "$AUTHOR"
update_yaml_key_quoted "$META_FILE" language "$LANGUAGE"
update_yaml_key_quoted "$META_FILE" rights "$RIGHTS"

update_typ_let "$PRINT_FILE" book_title "$TITLE"
update_typ_let "$PRINT_FILE" book_author "$AUTHOR"

# Also update output basename in Makefile so generated files match the book.
# Convention: strip to alnum, convert spaces/dashes to underscore.
NAME_RAW="$TITLE"
NAME=$(printf '%s' "$NAME_RAW" \
  | tr -cd '[:alnum:] _-' \
  | tr ' -' '__' \
  | sed -E 's/_+/_/g; s/^_+//; s/_+$//')

if [ -n "$NAME" ]; then
  tmp="$MAKEFILE.tmp"
  esc_name=$(escape_sed_repl "$NAME")
  if grep -qE '^[[:space:]]*NAME[[:space:]]*:=' "$MAKEFILE"; then
    # BSD sed doesn't support the GNU `0,/<re>/` address form.
    # Use an explicit first-match replace via awk (portable).
    awk -v n="$NAME" '
      BEGIN{done=0}
      done==0 && $0 ~ /^[[:space:]]*NAME[[:space:]]*:=/ { sub(/:=.*/, ":= " n); done=1 }
      { print }
    ' "$MAKEFILE" >"$tmp"
  else
    # Insert near the top if not found.
    awk -v n="$NAME" 'NR==1{print; print "NAME   := " n; next} {print}' "$MAKEFILE" >"$tmp"
  fi
  mv "$tmp" "$MAKEFILE"
fi

echo "Updated:"
echo "  - styles/metadata.yaml (title/creator/language/rights)"
echo "  - print.typ (book_title/book_author)"
echo "  - Makefile (NAME := $NAME)"

