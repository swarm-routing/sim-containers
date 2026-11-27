# Copyright (c) 2026 Daniel Joppi (https://github.com/swarm-routing)
# SPDX-License-Identifier: MIT OR GPL-2.0-only
"""Tests for protocol_images.py: python3 -m unittest discover -s tools"""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
import protocol_images as p  # noqa: E402

# `git ls-remote --tags` of swarm-routing/sim-tools on 2026-11-24 (trimmed),
# and of swarm-routing/swarm-adapter-ns3.
SIM_TOOLS = [
    "45b269996a3a7d2e7e3c4c1460932535aaa9bd40\trefs/tags/v1.1.2",
    "5c3bfb76f0af59fec3ec3be14cf8e8f5d45b7554\trefs/tags/v1.1.2^{}",
    "baf0e873d8e55e0644341d512fa56d88e76b1e1c\trefs/tags/v1.1.3",
    "c3e88640469acffb1cc6cccc2da4edb1641d687b\trefs/tags/v1.1.3^{}",
    "1111111111111111111111111111111111111111\trefs/tags/v1.1.10-rc1",
    "2222222222222222222222222222222222222222\trefs/tags/latest",
]
ADAPTER = [
    "0e9ffbf3bbc2aed46cec1592f8ebbd1383bcf681\trefs/tags/v1.0.0",
    "ff097aeb1f6237fb9796ff4713e91524fb5b4d3f\trefs/tags/v1.0.0^{}",
    "2b949df44aa00a8676a1bed7885da92a47700aec\trefs/tags/v2.0.0",
    "73f8f0de8417c05f97ae9903953e0825202c1f58\trefs/tags/v2.0.0^{}",
    "3333333333333333333333333333333333333333\trefs/tags/v0.10.0",
]
# A swarm-core.lock (swarm-adapter-ns3 v2.2.0's), served for the adapter's
# v2.0.0 commit: a swarm-core release other than the adapter's, so a test
# catches one version taken for the other.
LOCK = """# The swarm-core release this ns-3 module builds on (#231).
SWARM_CORE_REPO=swarm-routing/swarm-core
SWARM_CORE_TAG=v2.1.0
SWARM_CORE_COMMIT=392e84d98cefd45db184d0788c264621f2e58192
SWARM_CORE_VERSION=2.1.0
SWARM_CORE_ASSET=swarm-core-2.1.0.tar.gz
SWARM_CORE_SHA256=771e815865ea4d7618cdda61f0c51d0ad52918a4a58494c83350a0576acc6138
"""
BASE_DIGEST = "sha256:" + "a" * 64
SHA = "d11c6c5" + "0" * 33


def fake_ls(repo):
    return {"swarm-routing/sim-tools": SIM_TOOLS, "swarm-routing/swarm-adapter-ns3": ADAPTER}[repo]


def fake_lock(repo, commit):
    assert (repo, commit) == ("swarm-routing/swarm-adapter-ns3", "73f8f0de8417c05f97ae9903953e0825202c1f58")
    return LOCK


def fake_inspect(published=None):
    published = published or {}

    def insp(ref):
        if ref.startswith(p.BASE + ":"):
            return BASE_DIGEST, {"org.opencontainers.image.version": "3.49"}
        return published.get(ref)
    return insp


def run(argv, insp):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        p.main(argv, ls=fake_ls, insp=insp, lock_of=fake_lock)
    return json.loads(out.getvalue())["include"], err.getvalue()


class NewestRelease(unittest.TestCase):
    def test_highest_semver_peeled(self):
        self.assertEqual(p.newest_release(SIM_TOOLS), ("v1.1.3", "c3e88640469acffb1cc6cccc2da4edb1641d687b"))
        self.assertEqual(p.newest_release(ADAPTER), ("v2.0.0", "73f8f0de8417c05f97ae9903953e0825202c1f58"))

    def test_lightweight_tag_is_its_commit(self):
        self.assertEqual(p.newest_release(["abc\trefs/tags/v0.1.0"]), ("v0.1.0", "abc"))

    def test_numeric_not_lexical(self):
        lines = ["a\trefs/tags/v0.9.0", "b\trefs/tags/v0.10.0"]
        self.assertEqual(p.newest_release(lines)[0], "v0.10.0")

    def test_no_release(self):
        with self.assertRaises(ValueError):
            p.newest_release(["a\trefs/tags/latest", "b\trefs/tags/v1.0.0-rc1"])


class Lock(unittest.TestCase):
    def test_reads_the_release(self):
        self.assertEqual(p.parse_lock(LOCK), {"repo": "swarm-routing/swarm-core", "tag": "v2.1.0",
                                              "commit": "392e84d98cefd45db184d0788c264621f2e58192", "version": "2.1.0"})

    def test_rejects_an_incomplete_or_inconsistent_lock(self):
        for bad in ("", LOCK.replace("SWARM_CORE_VERSION=2.1.0", "SWARM_CORE_VERSION=2.1.1"),
                    LOCK.replace("SWARM_CORE_TAG=v2.1.0", "SWARM_CORE_TAG=main"),
                    LOCK.replace("392e84d98cefd45db184d0788c264621f2e58192", "392e84d")):
            with self.subTest(bad=bad[-80:]), self.assertRaises(ValueError):
                p.parse_lock(bad)


class Matrix(unittest.TestCase):
    def test_nothing_published_builds_both(self):
        inc, err = run(["--sha", SHA], fake_inspect())
        self.assertEqual([e["profile"] for e in inc], ["debug", "sanitized"])
        e = inc[0]
        self.assertEqual(e["versioned"], "3.49-debug-adapter2.0.0-swarmcore2.1.0-routingbench1.1.3")
        self.assertEqual(e["tags"].split(), [
            "3.49-debug-adapter2.0.0-swarmcore2.1.0-routingbench1.1.3",
            "3.49-debug-adapter2.0.0-swarmcore2.1.0-routingbench1.1.3-d11c6c5",
            "3.49-debug-swarmcore2.0.0-routingbench1.1.3",  # the former name (adapter version), still moved
            "3.49-debug", "latest-debug"])
        self.assertEqual(e["core_lock"], "swarm-routing/swarm-core@v2.1.0 392e84d98cefd45db184d0788c264621f2e58192")
        self.assertEqual(e["core_version"], "2.1.0")
        self.assertEqual(e["core_commit"], "392e84d98cefd45db184d0788c264621f2e58192")
        self.assertEqual(e["swarm_core_version"], "2.0.0")  # the adapter's release
        self.assertEqual(e["base_image"], f"{p.BASE}@{BASE_DIGEST}")
        self.assertEqual(e["base_ref"], f"{p.BASE}:latest-debug")
        self.assertEqual(e["swarm_core_spec"], "swarm-routing/swarm-adapter-ns3@v2.0.0")
        self.assertEqual(e["routing_bench_spec"], "swarm-routing/sim-tools@v1.1.3:ns3/routing-bench")
        self.assertEqual(e["routing_bench_commit"], "c3e88640469acffb1cc6cccc2da4edb1641d687b")
        self.assertEqual(e["dependencies"],
                         "swarm-core=swarm-routing/swarm-adapter-ns3@73f8f0de8417c05f97ae9903953e0825202c1f58,"
                         "routing-bench=swarm-routing/sim-tools@c3e88640469acffb1cc6cccc2da4edb1641d687b:ns3/routing-bench")
        self.assertIn("not published yet", err)

    def test_up_to_date_is_skipped(self):
        inc, _ = run(["--sha", SHA, "--profiles", "debug"], fake_inspect())
        e = inc[0]
        labels = {p.LABEL_BASE: e["base_image"], p.LABEL_DEPS: e["dependencies"], p.LABEL_RECIPE: e["recipe"]}
        same = ("sha256:" + "b" * 64, labels)
        insp = fake_inspect({f"{p.IMAGE}:{t}": same for t in e["tags"].split() if not t.endswith("-d11c6c5")})
        inc2, err = run(["--sha", SHA, "--profiles", "debug"], insp)
        self.assertEqual(inc2, [])
        self.assertIn("up to date", err)
        inc3, err = run(["--sha", SHA, "--profiles", "debug", "--force"], insp)
        self.assertEqual(len(inc3), 1)
        self.assertIn("forced", err)

    def test_lagging_rolling_tag_rebuilds(self):
        inc, _ = run(["--sha", SHA, "--profiles", "debug"], fake_inspect())
        e = inc[0]
        labels = {p.LABEL_BASE: e["base_image"], p.LABEL_DEPS: e["dependencies"], p.LABEL_RECIPE: e["recipe"]}
        same = ("sha256:" + "b" * 64, labels)
        published = {f"{p.IMAGE}:{t}": same for t in e["tags"].split()}
        published[f"{p.IMAGE}:latest-debug"] = ("sha256:" + "d" * 64, labels)
        insp = fake_inspect(published)
        inc2, err = run(["--sha", SHA, "--profiles", "debug"], insp)
        self.assertEqual(len(inc2), 1)
        self.assertIn("`latest-debug` is not on", err)

    def test_new_base_digest_rebuilds(self):
        inc, _ = run(["--sha", SHA, "--profiles", "debug"], fake_inspect())
        e = inc[0]
        labels = {p.LABEL_BASE: f"{p.BASE}@sha256:{'c' * 64}", p.LABEL_DEPS: e["dependencies"], p.LABEL_RECIPE: e["recipe"]}
        inc2, err = run(["--sha", SHA, "--profiles", "debug"],
                        fake_inspect({f"{p.IMAGE}:{e['versioned']}": ("sha256:" + "b" * 64, labels)}))
        self.assertEqual(len(inc2), 1)
        self.assertIn("other inputs (image)", err)

    def test_on_demand_release_moves_no_latest(self):
        inc, _ = run(["--sha", SHA, "--ns3-version", "3.48", "--profiles", "sanitized"], fake_inspect())
        self.assertEqual(inc[0]["base_ref"], f"{p.BASE}:3.48-sanitized")
        self.assertNotIn("latest-sanitized", inc[0]["tags"].split())

    def test_profiles_ci_consumes_only(self):
        for bad in ("optimized", "default", "debug,optimized", ""):
            with self.subTest(bad=bad), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                p.main(["--sha", SHA, "--profiles", bad], ls=fake_ls, insp=fake_inspect(), lock_of=fake_lock)

    def test_missing_base_fails(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            p.main(["--sha", SHA], ls=fake_ls, insp=lambda ref: None, lock_of=fake_lock)

    def test_recipe_is_the_dockerfile(self):
        self.assertRegex(p.recipe(), r"^[0-9a-f]{16}$")


if __name__ == "__main__":
    unittest.main()
