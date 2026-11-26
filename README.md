# omne-time-machine

A time-machine replay of every commit in all branches and PRs of [nemori-ai/omne-harness-lite](https://github.com/nemori-ai/omne-harness-lite).

Site: <https://nemori-ai.github.io/omne-time-machine/>

## How it updates

The workflow [`refresh.yml`](.github/workflows/refresh.yml) runs every 10 minutes:

1. Restore the mirror clone of the source repo from cache, then do an incremental `git fetch`.
2. `scripts/extract.py` reads every commit reachable from a branch or `refs/pull/*` and writes `data.json`.
3. `scripts/build.py` writes the data into `site/template.html` and outputs `_site/index.html` and `_site/version.json`.
4. Deploy to GitHub Pages.

An open page reads `version.json` once a minute. If the viewer is at "now", the page loads the new data right away. If the viewer is in the middle of a replay, a load button appears at the top of the page.

GitHub does not guarantee when scheduled workflows run. A run often starts a few minutes late.

## Run it locally

```bash
git clone --mirror https://github.com/nemori-ai/omne-harness-lite source.git
python3 scripts/extract.py source.git config.json data.json
python3 scripts/build.py data.json site/template.html _site --live
python3 -m http.server -d _site
```

## Configuration

Settings in `config.json`:

- `repo`: URL of the source repository.
- `trunks`: long-lived integration branches drawn as trunks beside `main`. A branch that does not exist is skipped.
- `site`: URL of this site.

## Update right after a push (optional)

Add a workflow to the source repository that sends a `repository_dispatch` event of type `source-updated` to this repository on every push. Sending the event needs a token with write access to this repository's contents.

## How things are counted

- All times are Beijing time (UTC+8).
- Commit authors are counted by the author name git records. Accounts are not merged.
- Branch lines are reconstructed from the merge topology. They include branches that were deleted.
