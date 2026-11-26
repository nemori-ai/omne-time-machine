"""Write the data file into the page template.

Usage: python3 scripts/build.py DATA_JSON TEMPLATE_HTML OUT_DIR [--live]

--live writes a standalone index.html plus version.json for GitHub Pages, and turns on
the page's polling. Without it, index.html is the fragment a claude.ai artifact wraps
in its own document.
"""
import datetime
import json
import pathlib
import sys

DOCUMENT_HEAD = """<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}[hidden]{display:none!important}</style>
"""


def main(data_path, template_path, out_dir, live):
    data = json.load(open(data_path, encoding="utf-8"))
    data["meta"]["live"] = live
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = open(template_path, encoding="utf-8").read().replace("/*__DATA__*/", blob)
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(DOCUMENT_HEAD + page if live else page, encoding="utf-8")
    if live:
        version = dict(commits=len(data["rows"]), last=data["t0"] + data["rows"][-1][0],
                       built=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
        (out / "version.json").write_text(json.dumps(version), encoding="utf-8")
    print("%s: %.2f MB" % (out / "index.html", len(page.encode()) / 1e6), file=sys.stderr)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--live"]
    if len(args) != 3:
        sys.exit(__doc__)
    main(*args, live="--live" in sys.argv)
