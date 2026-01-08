# Contributing / Keeping a link to the template

If you want to keep a connection to the template repo (so you can pull updates later), keep the existing Git history and add the template as an `upstream` remote.

```sh
# from inside your cloned repo
git remote rename origin upstream
git remote add origin git@github.com:<you>/<your-repo>.git

# push your main branch to your repo
git push -u origin main
```

Pull template updates later:

```sh
git fetch upstream
git merge upstream/main
```
