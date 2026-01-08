# Installation / Getting Started

This repo is a reusable template for writing novels with [Typst](https://typst.app/).

This file covers:

1) How to check out the template from GitHub
2) How to detach it from the upstream template repo and create **your own** Git repository

> **Safety note**
> The steps below include removing the existing `.git/` directory.
> That permanently deletes the template’s Git history *in your local copy*.
> Only do this **inside the folder you just cloned**.

---

## Option A (recommended): One-command bootstrap (curl)

This will:

- ask a few questions (title, author, language, rights)
- suggest a default folder name derived from the title (CamelCase)
- clone the template into that folder
- remove the template git history and initialize a fresh git repo

Run:

```sh
curl -fsSL https://raw.githubusercontent.com/anitasv/StoryTemplate/main/scripts/bootstrap.sh | bash
```

After it finishes:

```sh
cd <your-folder>
make pdf
```

---

## Option B: Manual install (clone + detach)

## 1) Clone the template

### Shallow clone (fast)

If you only want the latest snapshot (no history):

```sh
git clone --depth 1 git@github.com:anitasv/StoryTemplate.git
cd StoryTemplate
```

### About `depth=0`

`--depth 0` is **not** a valid value for `git clone`. Git uses:

- `--depth 1` for a shallow clone with only the latest commit
- *no* `--depth` flag for a full clone (effectively “unlimited depth”)

If you saw “depth=0” in other tooling, it typically means “no depth limit”.

---

## 2) Detach from the template and create your own repo

Delete the template Git history and re-init:

From inside the cloned folder:

```sh
# remove the template's Git history
rm -rf .git

# create a fresh Git repo
git init

# (optional) rename the default branch
git branch -M main

# commit the template as your first commit
git add -A
git commit -m "Initial commit from StoryTemplate"
```

Now create an empty repo on GitHub/GitLab/etc, then add it as your remote:

```sh
git remote add origin git@github.com:<you>/<your-repo>.git
git push -u origin main
```

---

## Next

Continue with the project usage instructions in **README.md**.

