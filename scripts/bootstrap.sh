#!/usr/bin/env bash
# StoryTemplate bootstrap installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/anitasv/StoryTemplate/main/scripts/bootstrap.sh | bash
#
# What it does:
# - Prompts for book metadata (title/author/language/rights)
# - Suggests a default folder name derived from the title (CamelCase)
# - Clones StoryTemplate into the folder
# - Detaches from template history (removes .git) and initializes a fresh git repo
# - Runs scripts/template-init.sh to stamp metadata

set -euo pipefail

TEMPLATE_GIT_URL_DEFAULT="https://github.com/anitasv/StoryTemplate.git"
TEMPLATE_BRANCH_DEFAULT="main"

die() { echo "error: $*" >&2; exit 1; }

is_macos() {
  [ "$(uname -s)" = "Darwin" ]
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

confirm() {
  # confirm <question> -> returns 0 if yes
  local q="$1"
  local ans
  printf '%s [y/N]: ' "$q" >&2
  IFS= read -r ans || ans=""
  case "${ans}" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

install_homebrew_macos() {
  # Installs Homebrew only if missing.
  if have_cmd brew; then
    return 0
  fi

  echo
  echo "Homebrew not found. Installing Homebrew..."
  # Official installer. Non-interactive; will prompt for sudo if needed.
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  # Make brew available in this shell for subsequent steps.
  if have_cmd brew; then
    return 0
  fi
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi

  have_cmd brew || die "Homebrew install completed but 'brew' is still not on PATH"
}

brew_install_if_missing() {
  # brew_install_if_missing <formula> <cmd-to-check>
  local formula="$1"
  local cmd_check="$2"

  if have_cmd "$cmd_check"; then
    echo "Already installed: $cmd_check"
    return 0
  fi
  echo "Installing: $formula (provides '$cmd_check')"
  brew install "$formula"
}

deps_satisfied_macos() {
  # Returns 0 if the optional toolchain we can install via Homebrew is already
  # satisfied. This prevents prompting users who already have everything.
  #
  # Satisfied means:
  # - typst is on PATH
  # - pandoc is on PATH
  # We don't require Homebrew itself if the commands already exist.
  have_cmd typst && have_cmd pandoc
}

prompt() {
  # prompt <label> <default> -> echoes chosen value
  local label="$1"
  local def="${2-}"
  local ans
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

to_camel_case() {
  # Best-effort CamelCase for folder names.
  # - Keeps alnum
  # - Treats non-alnum as separators
  # - Uppercases first letter of each word
  local s="$1"
  # shellcheck disable=SC2001
  s=$(printf '%s' "$s" | sed -E 's/[^[:alnum:]]+/ /g; s/^ +| +$//g')
  if [ -z "$s" ]; then
    printf '%s' "MyNovel"
    return
  fi
  awk 'BEGIN{ORS=""} {for(i=1;i<=NF;i++){w=$i; first=toupper(substr(w,1,1)); rest=substr(w,2); printf "%s%s", first, rest}}' <<<"$s"
}

main() {
  need_cmd git
  need_cmd sed
  need_cmd awk

  # Optional dependency installs (macOS only).
  if is_macos; then
    if deps_satisfied_macos; then
      echo "macOS detected. Optional tooling already installed (typst, pandoc)."
    else
      echo "macOS detected. Optional tooling install:"
      if confirm "Install dependencies (Homebrew if needed, plus typst/pandoc)"; then
        # We only attempt to install if user asks.
        # First ensure brew exists.
        install_homebrew_macos

        # Ensure brew packages are present; skip if commands exist.
        brew_install_if_missing typst typst
        brew_install_if_missing pandoc pandoc
      fi
    fi
  fi

  local template_url="${TEMPLATE_GIT_URL:-$TEMPLATE_GIT_URL_DEFAULT}"
  local template_branch="${TEMPLATE_BRANCH:-$TEMPLATE_BRANCH_DEFAULT}"

  echo "StoryTemplate bootstrap"
  echo

  local title author language rights folder_default folder
  title=$(prompt "Book title" "My Awesome Novel")
  folder_default=$(to_camel_case "$title")
  folder=$(prompt "Project folder" "$folder_default")
  author=$(prompt "Author / pen name" "My Pen Name")
  language=$(prompt "Language (BCP-47, e.g. en, en-US)" "en")
  rights=$(prompt "Rights" "All rights reserved")

  [ -n "$folder" ] || die "project folder cannot be empty"
  if [ -e "$folder" ]; then
    die "path already exists: $folder"
  fi

  echo
  echo "Cloning template into: $folder"
  git clone --depth 1 --branch "$template_branch" "$template_url" "$folder"

  ( 
    cd "$folder"
    echo "Detaching from template git history"
    rm -rf .git
    git init -q
    git branch -M main >/dev/null 2>&1 || true

    echo "Applying metadata"
    ./scripts/template-init.sh \
      --title "$title" \
      --author "$author" \
      --language "$language" \
      --rights "$rights"

    git add -A
    git commit -m "Initialize novel from StoryTemplate" >/dev/null 2>&1 || true
  )

  echo
  echo "Done. Next steps:"
  echo "  cd $folder"
  echo "  make pdf   # build PDF (requires typst)"
}

main "$@"
