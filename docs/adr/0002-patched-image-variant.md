# 0002. Publish a patched ns3-dev variant beside the stock images, with sim-tools' self-detecting patches only

- **Status:** accepted
- **Date:** 2026-11-25
- **Issue:** [swarm-routing/sim-tools#381](https://github.com/swarm-routing/sim-tools/issues/381) (part of [swarm-routing/sim-tools#374](https://github.com/swarm-routing/sim-tools/issues/374))

## Context

Until now every `ns3-dev` image was stock ns-3: on 2026-11-23 the maintainer
decided that the images stay stock and that the org works around ns-3 bugs in
its harness (NS3-001, the ns-3.49 AODV ICMP livelock: sim-tools'
`routing-bench` installs AODV behind its `IcmpErrorGuardHelper`; README
"Known issues").

NS3-005 ([swarm-routing/sim-tools#374](https://github.com/swarm-routing/sim-tools/issues/374),
[RCAPA](https://github.com/swarm-routing/sim-tools/blob/main/docs/ns3-rcapa/ns3-rcapa-aodv-lifetime-overflow.md))
cannot be worked around that way. Stock AODV gives the local broadcast route
of an interface that comes up the lifetime
`Simulator::GetMaximumSimulationTime()`, and `aodv::RoutingTableEntry` adds
`Simulator::Now()` to every lifetime: an `int64` overflow for any interface
brought up after t=0. Under the `sanitized` profile UBSan
(`-fno-sanitize-recover=all`) aborts the run, so a sanitized AODV campaign
(sim-tools#361's `--failures` run) cannot finish on any stock image. The fix
is in ns-3's own source, not in a module the harness links.

sim-tools now ships the fix as a self-detecting patch,
`ns3/patches/NS3-005/` (merged at
[`1b36c739`](https://github.com/swarm-routing/sim-tools/commit/1b36c739e0374295fc961772c044ecf90fb1b619)):
`apply.sh <ns-3 tree>` decides from the source, never from the version
(no AODV, already patched, or no unchecked `lifetime + Now()`: skip; the patch
applies: apply; the bug is there but the patch does not fit: exit 1), and
`aodv-lifetime-overflow.cc` reproduces the bug (UBSan abort on a stock
sanitized tree, `NS3-005 not-reproduced` and exit 0 on a patched one).

On 2026-11-25 the maintainer accepted sim-tools
[ADR-0002](https://github.com/swarm-routing/sim-tools/blob/main/docs/adr/0002-sim-tools-layout-and-packages.md)
decision 3 (#381): patched `ns3-dev` images exist as a **separate variant
beside the stock tags**, which stay available for comparison, and apply
**only self-detecting patches**; their NS3-005 plan ends with "patch our
images with sim-tools". Ruled out there: patches applied silently, and a
patched image replacing a stock tag.

## Decision

This **reverses the 2026-11-23 "images stay stock" decision for
self-detecting sim-tools patches** (maintainer decision 2026-11-25; sim-tools
ADR-0002 decision 3, #381). The stock images stay exactly as they were. Beside
them:

1. **Which images.** The supported release's Ubuntu `debug` and `sanitized`
   images (the profiles CI consumes) get a patched variant
   (`PATCHED` in `tools/ns3_matrix.py`). On-demand older releases get none
   (golden rule 16: they are history, and NS3-005's patch does not fit
   ns-3.43 and older).
2. **What is applied.** The patches in `PATCHES` (`NS3-005` today), each
   `ns3/patches/<ID>/apply.sh` of
   [swarm-routing/sim-tools](https://github.com/swarm-routing/sim-tools) at
   `SIM_TOOLS_COMMIT`, a full SHA pinned in `tools/ns3_matrix.py` (golden
   rule 13). `docker/Dockerfile` fetches sim-tools by that commit (`git
   fetch` of the SHA, then the checkout must equal it), right after the ns-3
   clone and **before configure**, so the configure line and every later step
   are the stock ones (golden rule 10). Nothing of the patch is vendored here.
   Bumping the commit or adding a patch is a change to `tools/ns3_matrix.py`
   (and, for a new patch, a proof in `test/patches.sh`).
3. **Only self-detecting patches, never silent.** Each `apply.sh` prints one
   `<ID>: ...` line and applies or skips; any other outcome (exit 1: the bug
   is there and the patch does not fit) fails the build. A patch is not
   applied by any other means.
4. **Tags.** `:<ver>-<profile>-patched` (and the full-number twin for a
   patch release), each with its immutable `-<sha7>` twin
   (`:3.49-sanitized-patched-<sha7>`), and `:latest-<profile>-patched`. No
   stock tag ever points at a patched image. Cache scope
   `<ver>-ubuntu-<profile>-patched` (golden rule 14; `tools/cache_tags.py`
   deletes an unsupported release's patched scopes like the stock ones).
5. **The record.** Labels `io.github.swarm-routing.ns3.patches` (the set, or
   `none`) and `io.github.swarm-routing.sim-tools.commit` (the SHA, or
   `none`) on every image; title and description say `patched`.
   `/opt/ns-3/.swarm-patches` (sourceable: `NS3_PATCHES`, `SIM_TOOLS_REPO`,
   `SIM_TOOLS_COMMIT`, `NS3_PATCHES_APPLIED`, `NS3_PATCHES_SKIPPED`, then each
   `apply.sh` line as a comment) and `/usr/local/share/ns3-patches/<ID>/` (the
   patch directory as fetched) exist on a patched image only.
6. **The proof** (golden rule 17). The variant goes through the same
   pipeline as every image: built once, every stage of `test/run.sh` on its
   digest (the full unit group included, so the patched AODV passes ns-3's own
   AODV suites), tags by copy. The `patches` stage proves a patched image
   (the record equals the matrix entry; each `apply.sh --dry-run` finds the
   built tree already patched; NS3-005's reproducer exits 0 with its verdict
   line and no sanitizer report on `sanitized`, SKIP on `debug`, where the
   overflow is silent) and proves that every stock image carries no patch.
7. **`latest-*`** (golden rule 18). The `latest-*-patched` tags move in the
   same `latest` job as the stock ones, so only after the downstream canary
   passed. The canary runs on the stock Ubuntu `debug` candidate only: the
   variant differs from it in the patched ns-3 sources alone, which its own
   unit and `patches` stages test.

## Consequences

- A sanitized AODV run that NS3-005 aborts can use
  `:latest-sanitized-patched` (pin `:3.49-sanitized-patched-<sha7>` for a
  published number); comparing against upstream ns-3 keeps the stock tags.
- Two more images per pipeline run on `main` and on image PRs (one sanitized,
  split like the stock one), and two more cache scopes.
- The stock images gained two labels (`none`), and the patch step is a new
  layer before configure: the first build after this change rebuilds every
  image's ns-3 tree once.
- Each new patch needs a proof in `test/patches.sh`; a patch ID it does not
  know fails the stage, so no patch ships unproven.
- Once ns-3 merges a fix, `apply.sh` skips by itself on a release that has
  it, the record says skipped, and the variant equals stock for that bug.
- Ruled out: a patched image under a stock tag; a patch that is not
  self-detecting; a vendored copy of a patch here; a patched on-demand
  release.
