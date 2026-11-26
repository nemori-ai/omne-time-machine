"""Turn a mirror clone of the source repository into the page's data file.

Usage: python3 scripts/extract.py SOURCE_GIT CONFIG_JSON OUT_JSON

Reads every commit reachable from branches and refs/pull/*, reconstructs branch
lanes from the merge topology, and writes one compact JSON file.
"""
import collections
import datetime
import json
import re
import subprocess
import sys

TZ = 8 * 3600  # every time on the page is Beijing time
MERGE_PR = re.compile(r"Merge pull request #(\d+) from (?:[^/\s]+/)?(\S+)")
MERGE_PR_SHORT = re.compile(r"Merge (?:pull request|PR) #(\d+)")
MERGE_BRANCH = re.compile(r"Merge (?:remote-tracking )?branch '([^']+)'")
MERGE_REF = re.compile(r"Merge ([\w./-]+/[\w./-]+)[:\s]")
RENAME = re.compile(r"^(.*)\{(.*) => (.*)\}(.*)$")
# top-level folders whose children are separate modules on the constellation
MODULE_PARENTS = {"packages", "packages.0.0.1.legacy", "apps", "apps.0.0.1.legacy", "tools", "examples", ".meta_harness", "docs", "spec"}


def git(repo, *args, check=True):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=check).stdout


def resolve_rename(path):
    m = RENAME.match(path)
    if m:
        path = (m.group(1) + m.group(3) + m.group(4)).replace("//", "/")
    elif " => " in path:
        path = path.split(" => ")[1]
    return path.strip('"')


def parse_log(text):
    commits, cur = {}, None
    for line in text.split("\n"):  # not splitlines(): subjects may hold U+2028 and friends
        if line.startswith("@@"):
            h, parents, t, author, subject = line[2:].split("|", 4)
            cur = commits[h] = dict(p=parents.split(), t=int(t), author=author, s=subject, files=[])
        elif cur is not None:
            parts = line.split("\t")
            if len(parts) >= 3:
                cur["files"].append(resolve_rename(parts[2]))
    return commits


def lane_name_for_merge(subject):
    m = MERGE_PR.search(subject)
    if m:
        return m.group(2), int(m.group(1))
    m = MERGE_PR_SHORT.search(subject)
    if m:
        return "PR #" + m.group(1), int(m.group(1))
    m = MERGE_BRANCH.search(subject) or MERGE_REF.match(subject)
    return (m.group(1), None) if m else ("", None)


def assign_lanes(repo, commits, trunks):
    """Each lane is a first-parent chain. main comes first, then each trunk, then every
    merged-in second parent, then whatever branch or PR heads are still unclaimed."""
    lane_of, lanes = {}, []

    def new_lane(name, kind, pr=None, merge=None):
        lanes.append(dict(name=name, kind=kind, pr=pr, merge=merge, fork=None, commits=[]))
        return len(lanes) - 1

    def walk(tip, li):
        h = tip
        while h in commits and h not in lane_of:
            lane_of[h] = li
            lanes[li]["commits"].append(h)
            ps = commits[h]["p"]
            h = ps[0] if ps else None
        if h in lane_of:
            lanes[li]["fork"] = h

    def expand(start):
        # lanes only grow and claims are final, so one pass in index order reaches a fixed point
        li = start
        while li < len(lanes):
            for h in list(lanes[li]["commits"]):
                for p2 in commits[h]["p"][1:]:
                    if p2 in commits and p2 not in lane_of:
                        name, pr = lane_name_for_merge(commits[h]["s"])
                        walk(p2, new_lane(name, "pr" if pr else "branch", pr, h))
            li += 1

    walk(git(repo, "rev-parse", "main").strip(), new_lane("main", "main"))
    for name in trunks:
        tip = git(repo, "rev-parse", "--verify", "--quiet", name + "^{commit}", check=False).strip()
        if tip:
            walk(tip, new_lane(name, "trunk"))
        else:
            print("trunk not found, skipped:", name, file=sys.stderr)
    expand(0)

    refs = [line.split() for line in git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/pull").splitlines()]
    pr_head = {o: int(r.split("/")[2]) for r, o in refs if r.startswith("refs/pull/") and r.endswith("/head")}
    heads = sorted((x for x in refs if x[0].startswith("refs/heads/")), key=lambda x: -commits.get(x[1], {"t": 0})["t"])
    pulls = sorted((x for x in refs if x[0].startswith("refs/pull/")), key=lambda x: -int(x[0].split("/")[2]))
    for r, o in heads + pulls:
        if o in commits and o not in lane_of:
            if r.startswith("refs/heads/"):
                li = new_lane(r[len("refs/heads/"):], "branch")
            else:
                n = int(r.split("/")[2])
                li = new_lane("PR #%d" % n, "pr", n)
            walk(o, li)
            expand(li)
    for L in lanes:
        if L["commits"] and not L["pr"]:
            L["pr"] = pr_head.get(L["commits"][0])
    return lane_of, lanes


def by_count(counter):
    # ties broken by name so the output does not depend on hash order
    return [k for k, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))]


def module_of(path):
    parts = path.split("/")
    if len(parts) == 1:
        return "(root)"
    if parts[0] in MODULE_PARENTS and len(parts) > 2:
        return parts[0] + "/" + parts[1]
    return parts[0]


def main(repo, config_path, out_path):
    cfg = json.load(open(config_path, encoding="utf-8"))
    commits = parse_log(git(repo, "log", "--branches", "--glob=refs/pull/*", "--format=@@%H|%P|%at|%aN|%s", "--numstat"))
    lane_of, lanes = assign_lanes(repo, commits, cfg["trunks"])
    missing = [h for h in commits if h not in lane_of]
    if missing:
        sys.exit("commits without a lane: %d" % len(missing))

    order = sorted(commits, key=lambda h: commits[h]["t"])
    idx = {h: i for i, h in enumerate(order)}
    t0 = commits[order[0]]["t"]

    # authors exactly as git records them, most commits first
    authors = by_count(collections.Counter(commits[h]["author"] for h in order))
    author_idx = {a: i for i, a in enumerate(authors)}

    # lanes: [name, kind, pr, start, end, n, parentLane, intoLane, forkIdx, mergeIdx]
    keep = [li for li, L in enumerate(lanes) if L["commits"]]
    remap = {li: k for k, li in enumerate(keep)}
    lane_rows = []
    for li in keep:
        L = lanes[li]
        ts = [commits[h]["t"] for h in L["commits"]]
        end = max(ts + ([commits[L["merge"]]["t"]] if L["merge"] else []))
        lane_rows.append([
            L["name"] or "~" + commits[L["commits"][0]]["s"][:60], L["kind"], L["pr"],
            min(ts) - t0, end - t0, len(ts),
            remap.get(lane_of[L["fork"]]) if L["fork"] else None,
            remap.get(lane_of[L["merge"]]) if L["merge"] else None,
            idx.get(L["fork"]) if L["fork"] else None,
            idx.get(L["merge"]) if L["merge"] else None,
        ])

    module_count = collections.Counter()
    for h in order:
        module_count.update(set(module_of(p) for p in commits[h]["files"]))
    modules = [m for m in by_count(module_count) if module_count[m] >= 3]
    module_idx = {m: i for i, m in enumerate(modules)}

    # rows: [dt, lane, author, files, secondParentIdx, modules[:12]]
    rows, subjects = [], []
    for h in order:
        c = commits[h]
        mods = sorted(set(module_idx[m] for m in map(module_of, c["files"]) if m in module_idx))
        second = idx.get(c["p"][1], -1) if len(c["p"]) > 1 else -1
        rows.append([c["t"] - t0, remap[lane_of[h]], author_idx[c["author"]], len(c["files"]), second, mods[:12]])
        subjects.append(c["s"][:80])

    count = lambda pattern: len(git(repo, "for-each-ref", pattern).splitlines())
    meta = dict(authors=authors, heads=count("refs/heads"), pulls=count("refs/pull"), tags=count("refs/tags"), site=cfg.get("site"))
    data = dict(t0=t0, tz=TZ, rows=rows, subjects=subjects, lanes=lane_rows, nodes=modules, nodeCount=[module_count[m] for m in modules], meta=meta)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    last = datetime.datetime.fromtimestamp(commits[order[-1]]["t"] + TZ, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    print("commits %d, lanes %d, authors %d, last %s (UTC+8)" % (len(order), len(lane_rows), len(authors), last), file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
