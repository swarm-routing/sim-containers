#!/usr/bin/env python3
# Copyright (c) 2026 Daniel Joppi (https://github.com/swarm-routing)
# SPDX-License-Identifier: MIT OR GPL-2.0-only
"""Resolve what the protocol-CI images are built from, and whether to build.

    tools/protocol_images.py --sha SHA [--ns3-version latest|X.Y] [--force]
        [--profiles debug,sanitized]

ghcr.io/swarm-routing/ns3-protocol-dev (docker/protocol/Dockerfile) is an
ns3-dev image with swarm-core and routing-bench prebuilt. Every input is
read, never typed (rules 13, 15):

  base     ns3-dev's latest-<profile> (the release ns-3 supports, moved only
           after ns3-dev's downstream canary), or <X.Y>-<profile> on demand;
           by digest, the ns-3 release read from its version label
  modules  each module's newest release: the highest vX.Y.Z tag of its
           repository (`git ls-remote`, no pre-release) and the commit it names
  recipe   the hash of docker/protocol/Dockerfile

and the image is built only when its versioned tag does not exist yet or
was built from other inputs (the labels the Dockerfile records), or with
--force: a new ns3-dev digest (a new ns-3 release, an image change, an OS
refresh) or a new release of either module rebuilds it, nothing else does.

Profiles: debug and sanitized only, the two CI consumes (rule 12); Ubuntu,
the base reusable-ns3-ci.yml uses. Tags of an entry (e.g. ns-3.49, swarm-core
2.0.0, routing-bench 1.1.3, debug):

  3.49-debug-swarmcore2.0.0-routingbench1.1.3          rolling: newest build of these inputs
  3.49-debug-swarmcore2.0.0-routingbench1.1.3-<sha7>   immutable: the sim-containers commit
  3.49-debug                                           rolling: the newest modules on 3.49
  latest-debug                                         rolling: the supported release (automatic builds only)

Prints {"include": [entry, ...]} with only the entries to build on stdout,
and one Markdown list line per profile (build or skip, and why) on stderr,
which the workflow appends to its step summary.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

IMAGE = "ghcr.io/swarm-routing/ns3-protocol-dev"
BASE = "ghcr.io/swarm-routing/ns3-dev"
PROFILES = ("debug", "sanitized")
RECIPE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docker", "protocol", "Dockerfile")
# name -> (repository, subdirectory holding the module, tag stem in image tags)
MODULES = {
    "swarm-core": ("swarm-routing/swarm-adapter-ns3", "", "swarmcore"),
    "routing-bench": ("swarm-routing/sim-tools", "ns3/routing-bench", "routingbench"),
}
RELEASE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
LABEL_RECIPE = "io.github.swarm-routing.protocol-image.recipe"
LABEL_BASE = "io.github.swarm-routing.ns3-dev.image"
LABEL_DEPS = "io.github.swarm-routing.dependencies"


def newest_release(ls_remote_lines):
    """(tag, commit) of the highest vX.Y.Z tag; an annotated tag's peeled commit."""
    commits = {}
    for line in ls_remote_lines:
        parts = line.split()
        if len(parts) != 2 or not parts[1].startswith("refs/tags/"):
            continue
        sha, ref = parts[0], parts[1][len("refs/tags/"):]
        peeled = ref.endswith("^{}")
        ref = ref[:-3] if peeled else ref
        if RELEASE.match(ref) and (peeled or ref not in commits):
            commits[ref] = sha
    if not commits:
        raise ValueError("no vX.Y.Z release tag")
    tag = max(commits, key=lambda t: tuple(int(x) for x in RELEASE.match(t).groups()))
    return tag, commits[tag]


def ls_remote(repo):
    out = subprocess.run(["git", "ls-remote", "--tags", f"https://github.com/{repo}.git"],
                         check=True, capture_output=True, text=True, timeout=120).stdout
    return out.splitlines()


def inspect(ref):
    """(digest, labels) of a registry image, or None when it does not exist."""
    p = subprocess.run(["docker", "buildx", "imagetools", "inspect", ref,
                        "--format", "{{json .Manifest}}|{{json .Image}}"],
                       capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        if re.search(r"not found|manifest unknown", p.stderr, re.I):
            return None
        raise RuntimeError(f"cannot inspect {ref}: {p.stderr.strip()}")
    manifest, image = p.stdout.split("|", 1)
    img = json.loads(image)
    if "config" not in img:  # an index: one config per platform, same labels
        img = next(iter(img.values()))
    return json.loads(manifest)["digest"], (img.get("config") or {}).get("Labels") or {}


def recipe(path=RECIPE_FILE):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def modules(releases):
    """Module entries from {name: (tag, commit)}, in build order."""
    out = []
    for name, (repo, sub, stem) in MODULES.items():
        tag, commit = releases[name]
        spec = f"{repo}@{tag}" + (f":{sub}" if sub else "")
        out.append({"name": name, "spec": spec, "commit": commit, "version": tag[1:], "stem": stem,
                    "pinned": f"{name}={repo}@{commit}" + (f":{sub}" if sub else "")})
    return out


def entry(profile, ns3_version, base_ref, base_digest, ns3_release, mods, rec, sha):
    versioned = f"{ns3_release}-{profile}-" + "-".join(f"{m['stem']}{m['version']}" for m in mods)
    tags = [versioned, f"{versioned}-{sha[:7]}", f"{ns3_release}-{profile}"]
    if ns3_version == "latest":
        tags.append(f"latest-{profile}")
    e = {"profile": profile, "ns3": ns3_release, "base_ref": base_ref,
         "base_image": f"{BASE}@{base_digest}", "recipe": rec,
         "dependencies": ",".join(m["pinned"] for m in mods),
         "versioned": versioned, "tags": " ".join(tags)}
    for m in mods:
        key = m["name"].replace("-", "_")
        e[f"{key}_spec"] = m["spec"]
        e[f"{key}_commit"] = m["commit"]
        e[f"{key}_version"] = m["version"]
    return e


def decide(e, existing_labels, force=False):
    """(build?, reason) for an entry, given its versioned tag's labels (None: no such tag)."""
    if force:
        return True, "forced (workflow_dispatch force)"
    if existing_labels is None:
        return True, f"`{e['versioned']}` not published yet"
    want = {LABEL_BASE: e["base_image"], LABEL_DEPS: e["dependencies"], LABEL_RECIPE: e["recipe"]}
    changed = [k.rsplit(".", 1)[-1] for k, v in want.items() if existing_labels.get(k) != v]
    if changed:
        return True, f"`{e['versioned']}` was built from other inputs ({', '.join(changed)})"
    return False, f"`{e['versioned']}` is up to date (same ns3-dev digest, module commits and recipe)"


def main(argv=None, ls=ls_remote, insp=inspect):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sha", required=True, help="the sim-containers commit (its sha7 is the immutable tag suffix)")
    ap.add_argument("--ns3-version", default="latest", help="latest (default) or an ns-3 release with an ns3-dev image, e.g. 3.48")
    ap.add_argument("--profiles", default=",".join(PROFILES))
    ap.add_argument("--force", action="store_true", help="build even when the versioned tag is up to date")
    a = ap.parse_args(argv)
    profiles = [p for p in a.profiles.split(",") if p]
    bad = [p for p in profiles if p not in PROFILES]
    if bad or not profiles:
        ap.error(f"--profiles takes {', '.join(PROFILES)} (CI consumes these only, rule 12), not {a.profiles!r}")
    if a.ns3_version != "latest" and not re.fullmatch(r"3\.\d+(\.\d+)?", a.ns3_version):
        ap.error(f"--ns3-version takes latest or a release such as 3.48, not {a.ns3_version!r}")

    mods = modules({name: newest_release(ls(repo)) for name, (repo, _, _) in MODULES.items()})
    rec = recipe()
    include, lines = [], []
    for p in profiles:
        base_ref = f"{BASE}:{'latest' if a.ns3_version == 'latest' else a.ns3_version}-{p}"
        found = insp(base_ref)
        if found is None:
            raise SystemExit(f"{base_ref} does not exist: no ns3-dev image to build on")
        digest, labels = found
        release = labels.get("org.opencontainers.image.version", "")
        if not release:
            raise SystemExit(f"{base_ref} has no org.opencontainers.image.version label")
        e = entry(p, a.ns3_version, base_ref, digest, release, mods, rec, a.sha)
        # An unreadable tag (a package not created yet answers 403 to an
        # anonymous pull) counts as not published: the cost is one extra build,
        # and an immutable -<sha7> tag is never moved by the promote step.
        try:
            existing = insp(f"{IMAGE}:{e['versioned']}")
        except RuntimeError as err:
            print(f"warning: {err}; treated as not published", file=sys.stderr)
            existing = None
        build, why = decide(e, None if existing is None else existing[1], a.force)
        if not build:
            # Up to date, but a rolling tag may lag (an on-demand run of the
            # supported release moves no latest-*): rebuild, so promote moves
            # every tag to one tested digest.
            for t in e["tags"].split()[2:]:
                try:
                    cur = insp(f"{IMAGE}:{t}")
                except RuntimeError:
                    cur = None
                if cur is None or cur[0] != existing[0]:
                    build, why = True, f"`{t}` is not on `{e['versioned']}`"
                    break
        lines.append(f"- {p}: {'build' if build else 'skip'}: {why}; base `{base_ref}` = `{digest[:19]}`, "
                     + ", ".join(f"{m['name']} {m['spec']} ({m['commit'][:7]})" for m in mods))
        if build:
            include.append(e)
    print("\n".join(lines), file=sys.stderr)
    print(json.dumps({"include": include}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
