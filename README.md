# omne-time-machine

A time-machine replay of every commit in all branches and PRs of [nemori-ai/omne-harness-lite](https://github.com/nemori-ai/omne-harness-lite).

Site: <https://nemori-ai.github.io/omne-time-machine/>

## How it updates

The workflow [`refresh.yml`](.github/workflows/refresh.yml) rebuilds the site:

1. Restore the mirror clone of the source repo from cache, then do an incremental `git fetch`.
2. `scripts/extract.py` reads every commit reachable from a branch or `refs/pull/*` and writes `data.json`.
3. `scripts/build.py` writes the data into `site/template.html` and outputs `_site/index.html` and `_site/version.json`.
4. Deploy to GitHub Pages.

An open page reads `version.json` once a minute. If the viewer is at "now", the page loads the new data right away. If the viewer is in the middle of a replay, a load button appears at the top of the page.

### What starts a rebuild

- A `source-updated` event from the source repository, sent on each push to any branch. This keeps the site current. See [Update right after a push](#update-right-after-a-push).
- A schedule every 10 minutes. This is only a fallback. GitHub runs scheduled workflows late or skips them: in this organization, an hourly schedule in the source repository ran once every 4 to 15 hours in November 2026.
- A push to `main` in this repository, or a manual run.

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

## Update right after a push

The source repository sends a `source-updated` event to this repository on each branch push. To set it up:

1. Create a fine-grained personal access token. Set the resource owner to `nemori-ai`, give it access to only `omne-time-machine`, and grant **Contents: Read and write**. A `repository_dispatch` event needs that permission.
2. Save the token as the secret `TIME_MACHINE_TOKEN` in the source repository:

   ```bash
   gh secret set TIME_MACHINE_TOKEN -R nemori-ai/omne-harness-lite
   ```

3. Add this workflow to the source repository as `.github/workflows/notify-time-machine.yml`:

   ```yaml
   name: Notify time machine

   on:
     push:
       branches: ["**"]
     delete:

   jobs:
     notify:
       runs-on: ubuntu-latest
       steps:
         - name: Ask omne-time-machine to rebuild
           env:
             GH_TOKEN: ${{ secrets.TIME_MACHINE_TOKEN }}
           run: |
             if [ -z "$GH_TOKEN" ]; then
               echo "TIME_MACHINE_TOKEN is not set, skipping"
               exit 0
             fi
             gh api repos/nemori-ai/omne-time-machine/dispatches -f event_type=source-updated
   ```

A burst of pushes does not queue a burst of rebuilds. The refresh workflow runs one build at a time and keeps at most one waiting.

## How things are counted

- All times are Beijing time (UTC+8).
- Commit authors are counted by the author name git records. Accounts are not merged.
- Branch lines are reconstructed from the merge topology. They include branches that were deleted.
