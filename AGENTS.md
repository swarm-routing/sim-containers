# AGENTS.md — guide for AI coding agents

Operational guide for LLM agents working in `swarm-routing/ns3-containers`. Read this
before changing anything. Org-wide conventions:
[`swarm-routing/.github` CONTRIBUTING.md](https://github.com/swarm-routing/.github/blob/main/CONTRIBUTING.md). Shape and rules mirror
[AntHocNet's AGENTS.md](https://github.com/swarm-routing/AntHocNet/blob/main/AGENTS.md), the source repository.

## What this repo is

Builds and publishes `ghcr.io/swarm-routing/ns3-dev` (public): ns-3
pre-configured and pre-built with Ninja at `/opt/ns-3`, so a downstream contrib
module compiles alone in seconds. Automatic pipelines build only the release
ns-3 supports (its latest); older releases are built on demand and kept as
history (`tools/ns3_matrix.py`; bases and tags: README "Which image"). Profiles: `default` (ns-3 `-d default`, the plain `:<ver>` tag),
`debug` (CI default), `sanitized` (ASan+LSan+UBSan), `optimized` (ns-3
`-d release`, campaigns only). Bases: Ubuntu 24.04 (default), Debian 13,
Debian 13 slim, Alpine (experimental). `ns3-build-contrib` links mounted
modules into the tree and builds them.

```
docker/Dockerfile                 the image: BASE_IMAGE x NS3_VERSION x BUILD_PROFILE
docker/scripts/build-contrib.sh   ns3-build-contrib (strict warnings, coverage, quality modules)
docker/gcovr-requirements.{in,txt}   gcovr's pin and hashed lock (debug/sanitized images)
tools/ns3_matrix.py               supported vs on-demand releases, base digests, tags, PR representatives
tools/pr_tests.py                 which images and stages a PR tests (the `select` job)
tools/pass_markers.py             promote's check: every test job passed, on one digest
tools/cache_tags.py               which ns3-dev-cache tags the daily cleanup deletes (rule 14)
tools/release/dist.sh             the release asset: the pipeline's source tarball, checked (`make dist`)
.cz.toml, CITATION.cff            Commitizen config and the version it bumps; releases run through release.yml (the org reusable-release.yml)
test/run.sh                       every test stage against one image ref (`--stages`, `--unit-shard`)
test/{structure,profile,smoke,integration,unit}.sh   the stages: image contract, profile promise, smoke, simulation, ns-3 unit suites
test/ns3-suites.txt, test/known-failures.txt   unit suites per profile (split, main-only), expected upstream failures
test/downstream.{sh,txt}          the downstream canary (a wrapper of swarm-routing/.github tools/downstream/downstream.sh, swarm-routing/.github#482) and the org modules it builds (gates latest-*)
test/fixtures/                    swarm-hello (smoke), manet-canary (integration), profile-probe (profile); GPL-2.0-only
.trivyignore, .hadolint.yaml      accepted Dockerfile findings; hadolint settings
.github/workflows/                publish-images.yml (build, test by digest, promote, sign; `images gate`), container-security.yml,
                                  os-refresh.yml (daily scan, dispatches publish-images' `refresh`, #218),
                                  pr-title.yml, release.yml, candidates-cleanup.yml, licence.yml, sync-labels.yml; org-managed: org-sync.yml,
                                  review-gate.yml, dco.yml, scorecard.yml; .github/ISSUE_TEMPLATE/ (+ image-request.yml)
```

Before you change one of these files, or need what a flag, stage or job does
in detail, read its line in [`docs/layout.md`](docs/layout.md).

## Build & verify

The step-by-step version for people (prerequisites, every command, the CI
map, troubleshooting) is [`docs/development.md`](docs/development.md).

```bash
python3 -m unittest discover -s tools                               # matrix generator
docker build -f docker/Dockerfile --build-arg NS3_VERSION=3.48 \
    --build-arg BUILD_PROFILE=debug -t ns3-dev:3.48-debug .        # ~8-15 min on 4 cores
EXPECT_VERSION=3.48 EXPECT_PROFILE=debug EXPECT_OS=ubuntu \
    test/run.sh ns3-dev:3.48-debug                                 # every test stage, as CI runs them
test/downstream.sh --check                                         # the consumer list parses (no docker; swarm-routing/.github checked out next to this repo, or ORG_TOOLS_DIR)
test/downstream.sh ns3-dev:3.48-debug                              # every org module builds and passes on the image (latest-* gate)
hadolint docker/Dockerfile                                       # reads .hadolint.yaml; exit 0 required
shellcheck docker/scripts/build-contrib.sh test/*.sh
actionlint .github/workflows/*.yml
```

The smoke must report a small Ninja step count (8 today, gate 40): a larger
number means the warm cache was missed. Behind a TLS-intercepting proxy, build
from a scratch copy of the Dockerfile with the proxy CA added; never commit
that layer. The PR's own `publish-images` run is the authoritative check.

Releases (swarm-routing/.github CONTRIBUTING "Cutting a release"): the
version is the image pipeline's and its contract's (tags, profiles, bases,
`ns3-build-contrib`), never an image tag, which stays the ns-3 release. On
the maintainer's request only, dispatch `release.yml` with `dry-run`, then
`bump` (the first release with `increment` MAJOR: v1.0.0, maintainer decision
2026-11-13); merging the bot's `chore(release): bump version A to B` PR tags
and publishes `make dist`'s tarball (`tools/release/dist.sh`; `DIST_CHECK=0`
skips its check). The images keep `publish-images.yml`.

## Golden rules (invariants — do not break)

Org-wide (1–9), then this repo's own.

<!-- org-sync:begin org-rules -->
1. **Licensing per directory, as AntHocNet** ([`LICENSING.md`](LICENSING.md);
   AntHocNet [LICENSING.md](https://github.com/swarm-routing/AntHocNet/blob/main/LICENSING.md),
   [ADR-0028](https://github.com/swarm-routing/AntHocNet/blob/main/docs/adr/0028-core-is-dual-licensed.md)). A
   simulator-free `core/` and the standalone tooling are `MIT OR GPL-2.0-only`;
   ns-3 modules, the site, docs and data are `GPL-2.0-only`. Every original
   `.h`/`.hpp`/`.cc`/`.cpp`/`.go`/`.py`/`.sh` starts with
   `// Copyright (c) 2026 Daniel Joppi (https://github.com/swarm-routing)` +
   `// SPDX-License-Identifier: <MIT OR GPL-2.0-only | GPL-2.0-only>` (`#`
   comments where needed), matching its directory in `LICENSING.md`; an
   outside contributor may add their own `Copyright (c) <year> <Name>` line
   beneath the org line, never replace it, and signs off every commit (DCO,
   CONTRIBUTING "Outside contributions"). CI (`reusable-licence-check.yml`)
   checks the SPDX line, and the org line's place when a header names more
   than one holder; a header with a single, other holder (a replaced org line,
   or third-party code) passes it, so review catches that. A new directory
   gets its row in `LICENSING.md` in the same PR.
2. **The licence boundary only goes one way.** GPL code may use the dual
   parts; dual code never pulls GPL-only code in: a `core/` file includes only
   the C++ standard library, other `core/` files and the dual-licensed `core/`
   of a dependency pinned by commit and declared as the `core-deps` input of
   every workflow that runs the licence check (one calling
   `reusable-licence-check.yml`, or one calling `reusable-ns3-ci.yml`, which
   forwards it; workflow file names differ per repo), each with the same pin,
   with `core-roots` naming the repo's own `core/`
   (without it the check skips core includes; a protocol's `core/` on
   swarm-core's; CI checks it, `check-headers --core-dep`), and a dual script imports no GPL-only code. Code coming from AntHocNet keeps its
   licence: its `core/`/`tools/` (dual) may land in dual or GPL paths here; its
   `ns3/` modules and `web/` (GPL-2.0-only) only in GPL paths. Third-party code
   (AntHocNet's vendored `aomdv`/`gpsr`, IITP RAS) lands only in GPL paths with
   its provenance recorded. Write clean implementations against public ns-3
   interfaces rather than copying ns-3's `src/aodv`/`src/olsr`.
3. **Wire formats are POD + versioned.** Control headers are
   simulator-independent POD structs with bounds-checked little-endian
   readers/writers, a leading version byte, and deterministic roundtrip + fuzz
   tests. Changing a field or its units bumps the version byte.
4. **No contrib module named `core`** (collides with ns-3's `src/core`). The
   shared module is `swarm-core` (`#include "ns3/swarm-core-module.h"`), and
   every protocol builds on it, AntHocNet included: `core/` on its `core/`, the
   ns-3 adapter on `SwarmRoutingBase` (swarm-routing/swarm-adapter-ns3#14).
5. **Determinism.** A fixed `--seed=<N>` gives byte-identical output. All
   randomness through the simulator's seeded streams or an injected RNG port;
   never libc `rand()`, wall-clock time, or unordered-container iteration order
   in anything that reaches an output.
6. **Comparisons are paired.** Per-seed deltas across >= 20 seeds, emitting the
   canonical `##CONFIG##`, `##RUN##`, `##BENCH##`, `##DIAG##` lines. A
   comparator arm (a protocol we did not design) counts only after its three
   gates: a fidelity sheet from its paper, the per-PR delivery smoke, and an
   anchor reproducing the paper's own trend.
7. **Keep bounded structures bounded** (visited paths, dedup histories, queues
   carry a configured cap).
8. **CI hygiene.** Actions pinned by full commit SHA with a `# vX.Y.Z` comment;
   buildx caches scoped per profile; transient artifacts `retention-days` <= 7.
   Every job that runs steps has a `timeout-minutes` cap (a job that only
   calls a reusable workflow cannot take one: the called workflow's jobs carry it), and every apt, npm or installer step
   its own, sized from recent green runs; `apt-get update` runs with
   `--error-on=any` inside a shell retry. Ubuntu mirror outages are the usual
   cause of a red run.
9. **Nothing shipped depends on `.claude/`.** Skills hold procedures; scripts
   that anything shipped needs live in `tools/` (AntHocNet ADR-0014).
<!-- org-sync:end org-rules -->
10. **The configure line is shared.** `docker/Dockerfile` and `build-contrib.sh` must pass identical profile flags, `--enable-examples --enable-tests --disable-werror` and module list (the Dockerfile records them in `/opt/ns-3/.swarm-configure.env`); only the contrib list, the examples/tests filter and the quality hook's cache variables (`docker/scripts/swarm-quality.cmake`, which changes only the contrib modules' targets) may differ. Drift forces a full ns-3 rebuild in every downstream job — the smoke's step-count gate catches it.
11. **`optimized` is ns-3's `release` profile, never ns-3's `optimized`** (`-march=native` makes an image SIGILL on another CPU).
12. **CI consumes `debug`/`sanitized`, never `optimized`.** Asserts catch real bugs (AntHocNet #123).
13. **Pinned inputs.** The base image by digest; actions by SHA. A published number pins the immutable `:<ver>-<profile>-<sha7>` tag, not the rolling one.
14. **One buildx cache scope per version x base x profile** (`mode=max`, registry cache in `ns3-dev-cache`); only the supported release's scopes are kept: `candidates-cleanup.yml` deletes every other release's cache tags daily (`tools/cache_tags.py`, the supported release read as `tools/ns3_matrix.py` reads it; maintainer decision 2026-11-13, #146). The scope an on-demand build of an older release writes is deleted by the next cleanup, with no grace period. A tag that is not `<ver>-<base>-<profile>` is kept and reported; nothing is deleted when the supported release cannot be determined or the package has no scope of it.
15. **The version list is generated, never typed.** `tools/ns3_matrix.py` reads upstream tags; a hand-pinned version would silently stop following ns-3's supported release.
16. **Automatic pipelines build only the release ns-3 supports** (its latest; the generator's default). Older releases are history: never rebuild them as a side effect; the `versions` input is a deliberate, manual, on-demand build.
17. **What is tested is what is tagged.** Each image is built once; every test runs on that build by digest, in the same run; tags are a carbon copy of that digest (`imagetools create`), never a rebuild. A new test stage goes into `test/run.sh`, so automatic and on-demand builds (and fork PRs) all run it (#36, #37). An image may be tested in parallel jobs (`split` in `test/ns3-suites.txt`, #86), all on the same digest in the same run; promote needs every one of them, and `test/run.sh` with no option still runs everything. PRs never tag; `main` runs every stage on every image, each with its profile's whole unit group (`full` on every debug and sanitized image, `main-only` suites included), before it promotes the digest, so every published image is tested with every suite. On a PR only, two things are smaller: the Debian, slim and Alpine images run the `light` unit group (`UNIT_SET`, set by the workflow from the event and the matrix entry; maintainer decision on #87), Ubuntu `debug` and `sanitized` keep `full`; and every image leaves out the suites on `test/ns3-suites.txt`'s `main-only` line (`UNIT_PR=1`; today `ns3-tcp-cubic`, maintainer decision (c) on #86), saying so in the job log and summary. A run without `UNIT_SET` and `UNIT_PR` (a local run, a schedule or dispatch run, a push to `main`) runs the profile's whole group. A PR also tests only the images it affects (maintainer decision, 2026-11-11; #86, #87; `tools/pr_tests.py`, the `select` job): an image whose content (layers and config without the per-build `revision` and `build-run` labels) equals the image its versioned tag points to (what `main` last tested and promoted) is not tested again when no test input (`test/`, `tools/ns3_matrix.py`, `tools/pass_markers.py`, `tools/pr_tests.py`, `publish-images.yml`, `.trivyignore`) changed since the commit `main` tested it at; when only test inputs changed, the stages they feed run on the representative images only: Ubuntu `debug`, `sanitized` and `optimized`, Debian `debug`, slim `default` and Alpine `debug` (`REPRESENTATIVES` in `tools/ns3_matrix.py`: every base and every profile once); an image whose content differs runs every test job. Fork PRs make the same choice read-only, in their build job. The step summary has a line per image (e.g. "unchanged digest, already tested on main"); `images gate` passes when images are skipped. A known upstream bug is a `test/known-failures.txt` entry for one exact ns-3 version with its tracking issue, never a skipped or loosened check.
18. **`latest-*` moves only after the downstream canary** (#44). On `main`, the `canary` job builds and tests the org's ns-3 modules (`test/downstream.txt`, run by `test/downstream.sh`, a wrapper of swarm-routing/.github `tools/downstream/downstream.sh`) on the Ubuntu `debug` candidate, in parallel with promote; the `latest` job needs it to succeed. Today every consumer gates; which ones should gate and which run advisory waits on the maintainer (#215, swarm-routing/.github#672). A failing consumer leaves `latest` on the previous digest and opens or updates one issue per consumer and release; the versioned and `-<sha7>` tags are not held back. A consumer is one line (`name | owner/repo@ref | ns-3 range | modules | suites | stage | run`) or a `ci/canary.sh` in its repository, which then runs instead (exit 0 = pass); the ns-3 range decides which on-demand `versions` builds run it, and a line whose module directory does not exist yet is skipped with its reason. PRs run it as an advisory job; fork PRs skip it. Changing a column or the `ci/canary.sh` contract is announced in each consumer repository (rule 10 of `swarm-routing/.github`).

## Conventions

<!-- org-sync:begin conventions -->
- Issues follow the org taxonomy ([CONTRIBUTING.md](https://github.com/swarm-routing/.github/blob/main/CONTRIBUTING.md#issues), from
  [AntHocNet ADR-0013](https://github.com/swarm-routing/AntHocNet/blob/main/docs/adr/0013-track-bugs-and-findings-as-issues.md)): one type label
  (`bug`/`enhancement`/`chore`/`documentation`/`verification`, plus `epic` for
  umbrellas), area label(s) (`protocol`/`adapter`/`ns3`/`benchmark`/
  `observability`/`packaging`/`ci`/`learn-site`/`literature`), one `model:*`
  suggestion (a model on the Claude Pro plan), one `priority:P1|P2|P3` on
  non-epic issues (none on an epic), and a `release:vX.Y.Z` label only when
  a release in the repository's ladder (`docs/roadmap.md`, else the org
  ROADMAP's release train) gates the issue: that label set is the version's
  scope, released when its issues are done (CONTRIBUTING "Cutting a
  release"). Labels come from `.github`'s `labels.json`, applied to every
  repository as soon as it changes (never deleting one); a release version
  it lacks is added there (and to CONTRIBUTING's label table), or, in a
  repository that keeps its own release labels (AntHocNet), created with
  `gh label create release:vX.Y.Z`.
- Issue bodies: **Context** (evidence, numbers, links) · **Scope** ·
  **Acceptance criteria** (checkboxes) · **Depends on** (cross-repo form
  `swarm-routing/<repo>#N`) · **References**. Children of an epic say "Part of
  #N" and are linked as sub-issues. Comments you post end with the Claude Code
  footer.
- Issues migrated from AntHocNet carry `migrated` and start with *Migrated from
  `danieljoppi/AntHocNet#N`*.
- Epics are listed in a public repository's README `## Epics` and the org
  [ROADMAP](https://github.com/swarm-routing/.github/blob/main/ROADMAP.md#epics),
  generated from the `epic` issues by `.github`'s `tools/epics/epics.py`. An
  open epic is Planned (no sub-issue closed) or In progress (some closed); it
  is Done or Dropped only once the epic itself is closed (completed or not
  planned). The lists follow the issues with no hand step: an issue change
  that can move them makes the org-managed `epics-changed.yml` run org-bot's
  `epics` task, which opens the refresh PRs. Never edit a generated section
  by hand; private repositories keep none.
<!-- org-sync:end conventions -->

## Git workflow

<!-- org-sync:begin git-workflow -->
- Branch from `main` (`claude/<short-topic>`), one focused change per PR.
- **Always open a PR to `main`** once the branch is pushed — every change is
  tracked through one.
- **PRs are squash-merged** (the only merge method enabled). The PR title is
  the commit on `main`: a lowercase Conventional Commit, `type(scope)!:
  subject`, type one of `feat fix docs style refactor perf test build ci
  chore revert`, subject starting lowercase.
- Push with `git push -u origin <branch>`; merge when CI is green.
- **`main` takes no direct push**, in any repo: its ruleset requires a PR and
  the required checks, not an up-to-date branch. Bots push `bot/<name>`
  branches and open PRs; a release is the bump PR from `bot/release`, tagged
  after it merges (CONTRIBUTING "Cutting a release").
- A PR behind `main` may merge as it is. Update it
  (`gh api -X PUT "repos/<owner>/<repo>/pulls/<n>/update-branch"`, the PR's
  base repository) only when `main` changed what it touches (a template, a
  workflow, a required check), then merge after its CI. Never update a
  merge-queue PR by hand: enable auto-merge and the queue tests it on the
  latest `main` (CONTRIBUTING "Merge when CI is green"). Never force-push a
  branch someone else pushed. A behind `bot/release` PR: dispatch the release
  `bump` again.
- **Settings are code.** Settings, rulesets, required checks and the Actions
  allowlist change only by a PR to the repo's `[settings]` in
  `.github/org-sync.toml` or to `templates/rulesets/` in
  `swarm-routing/.github`, never in the UI or by a direct API write. A
  rulesets change applies on merge, a `[settings]` change on its push through
  the org-managed `settings-apply.yml` (swarm-routing/.github#569). A required
  check runs on every PR (no `paths:` filter; skip work inside a gate job) and
  is named exactly as its check run. A new third-party action goes into
  `defaults.json` `selected_actions` (`templates/rulesets/`) in swarm-routing/.github
  before or with the workflow that uses it, or `repo-settings` refuses the repo.
<!-- org-sync:end git-workflow -->

<!-- org-sync:begin skills -->
## Agent skills

The org's procedures ship as the Claude Code plugin **`swarm-routing`**
([`swarm-routing/skills`](https://github.com/swarm-routing/skills)), which this
repository's `.claude/settings.json` enables; other agents install the same
skills with `npx skills add swarm-routing/skills` ([skills.sh](https://skills.sh)).
A skill is the procedure; its script does the work without it (golden rule 9),
so an agent without the skill, or a session that does not read this
repository's settings, starts from the script. Plugin missing (it was
`org-repo` before 2026-11-09)? Run `claude plugin marketplace update
swarm-routing` and start a new session.

| Task | Script (any agent) | Skill |
|------|--------------------|-------|
| Bring this repository onto the org templates, or fix their drift | `swarm-routing/.github` `tools/org-sync/org_sync.py` | `org-repo` |
| Write or review a protocol's paper-fidelity sheet (`docs/fidelity.md`) | `swarm-routing/.github` `tools/fidelity/fidelity.py` | `fidelity-sheet` |
| Check a diff against the org golden rules before a PR or a review | `swarm-routing/.github` `tools/protocol-review/check_invariants.py` | `protocol-review` |
| Bring the README, AGENTS/CLAUDE/CONTEXT and docs/ to the org standard | `swarm-routing/.github` `tools/docs-review/check_docs.py` | `docs-review` |
| Find new papers on a topic, or confirm a reference (free sources only) | `swarm-routing/.github` `tools/lit-search/lit_search.py` | `lit-search` |
| Give a repository its docs/references.bib, or review it (every paper and org release it relies on, confirmed from its record) | `swarm-routing/.github` `tools/fidelity/fidelity.py` (bib), `tools/zenodo/zenodo.py` | `references` |
| Take open pull requests from review to merge (CI, review threads, merge) | `swarm-routing/.github` `tools/pr-status/pr_status.py` | `pr-shepherd` |
| Measure what a session loads from the agent files, or where a finished session's tokens went | `swarm-routing/skills` `tools/token-audit/token_audit.py` | `token-audit` |
| Register a repository for the OpenSSF Best Practices badge, or check its answers | `swarm-routing/.github` `cmd/bestpractices` (Go) | `bestpractices` |
| Check or bump the release a repository builds on (`swarm-core.lock`, `ns3-tools.lock`) | `swarm-routing/.github` `tools/checks/release_lock.py`, `tools/checks/check-swarm-core-pin.py` | `dependency-bump` |
| Cut a release on the maintainer's request, and its aftercare | `swarm-routing/.github` `tools/release/release_check.py`, `tools/zenodo/zenodo.py` | `release` |
| Record a reviewed SonarQube Cloud false positive or accepted finding | `swarm-routing/.github` `tools/sonar-triage/sonar_triage.py` | `sonar-triage` |

A skill only this repository uses lives in its own `.claude/skills/`; one two
repositories need moves to the plugin. Skills that file, cite and extract
papers stay in the maintainer's private library; a public skill may point to
them, never carry their content.
<!-- org-sync:end skills -->

<!-- org-sync:begin agent-defaults -->
## Working defaults

Condensed from [andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills).

- **Assumptions:** state the ones that matter. Ask only when the choice
  belongs to the maintainer (a default, a published number, a cell, the
  scope), with your recommendation and its reason, never the options alone.
  Otherwise pick the sensible option, say which, and keep going: long
  unattended runs, like campaigns, depend on that.
- **Simplicity:** the least code that solves the task. No speculative
  features, configurability or abstractions for one use.
- **Surgical diffs:** every changed line traces to the request. Match the
  surrounding style. Mention unrelated dead code rather than deleting it, and
  remove only the orphans your own change created. Update the doc or ADR of a
  documented decision you change.
- **Verifiable goals:** a bug gets a reproducing test first; a refactor passes
  before and after. Finish when the check passes, not when the code looks right.

## Session habits

- **Handoffs are always a ticket**: work in flight at a session's end, or a
  handoff asked for, is an issue from the *Handoff* template (label
  `handoff`), never a file in the repo; a session continuing a handoff
  updates that issue. Continued work starts from the newest open `handoff`
  issue for it, a new task from the request; close the issue, and any older
  one it superseded, when its work is done ([AntHocNet ADR-0013](https://github.com/swarm-routing/AntHocNet/blob/main/docs/adr/0013-track-bugs-and-findings-as-issues.md) item 5).
- **Attach only the repositories the task needs**: every request loads each
  attached repository's agent files.
- **Start from the record, not from memory:** the matching `handoff` issue,
  then the issue's acceptance criteria, then `main`. Check a claim against its
  source before it goes into an issue or a PR.
- **Script what repeats**: a check or lookup run more than a few times
  becomes a script in `tools/` that prints a summary; read the verdict, not
  the raw data (AntHocNet ADR-0014).
- **Automate what can be automated** (org CONTRIBUTING invariant 8): a step
  stays manual only when no API or permission exists for it, or the
  maintainer reserves the decision; list it in swarm-routing/.github#568.
- **Measure before cutting or adding agent text** with the `token-audit`
  skill (`swarm-routing/skills` `tools/token-audit/token_audit.py`). MCP
  servers, plugins, token habits and the long form of each pitfall below:
  [`docs/agents.md`](https://github.com/swarm-routing/.github/blob/main/docs/agents.md)
  in swarm-routing/.github (ADR-0005).

## Response style — caveman (token economy)

Answer in tight, low-filler prose: no hedging, pleasantries or preamble; same
information, fewer output tokens. **The record stays full:** code, commands,
paths, error text and benchmark numbers byte-for-byte, and commit messages,
PR bodies, ADRs, `docs/` and issue threads detailed (AntHocNet's AC_BE_NQOS /
A2 investigation was recoverable only from thorough threads). Caveman the
chat, not the record.

## Agent pitfalls

- **Before every push, run `make check`** (none: the "Build & verify"
  commands; `make pre-push TITLE='…'` where it exists) **and check the PR
  title** (Git workflow): a skipped step costs a CI round
  (swarm-routing/.github#586).
- `gh api … -F body=@file` reads the file; `-f body=@file` posts the literal
  text `@file`.
- When the permission system refuses a command (a merge, say), stop and report
  it. Never retry it another way, and never ask another agent to run it.
- Edit files with the editor tools, never a shell heredoc or `sed -i`, and
  touch one repository per command (swarm-routing/.github#578).
- Stage files by name, never `git add -A`; keep build output in `.gitignore`
  (swarm-routing/.github#644).
- A Go test reads only files under `cmd/` or `internal/` (`testdata/`)
  (swarm-routing/.github#587).
- Clean up only your own directory, never a shared one
  (swarm-routing/.github#644).
- Search an output the harness saved to a file (`grep`, `head`, `sed -n`),
  never read it whole; wait on a PR with `pr_status.py wait` or `wait
  --merged`, not by subscribing to its activity (swarm-routing/.github#794).
- A PR body's `Closes #N` closes the issue on merge; write `Part of #N` while
  acceptance criteria remain open.
- Before saying a tool or check is missing, look at `main` (`git fetch`,
  `origin/main`), not a stale local checkout.
- Write another repository's issue in full, `swarm-routing/<repo>#N`, also in
  a list or range: a bare `#N` links to the repository the text is in
  (swarm-routing/.github#277). An ns-3 item is its GitLab URL (or link text
  `nsnam/ns-3-dev#N`); text bound for ns-3's GitLab names ours by full GitHub
  URL (CONTRIBUTING "ns-3 bugs (RCAPA)").
- An issue called done in `ROADMAP.md` or an AGENTS.md is not evidence: read
  its acceptance criteria (swarm-routing/.github#274).
- Change text inside `org-sync:begin/end` markers only through
  `swarm-routing/.github` `templates/`, then org-bot's refresh PRs; never add
  such commits to an unrelated PR (swarm-routing/.github#236).
- With a merge queue, merge by enabling auto-merge (squash); a direct merge is
  refused (HTTP 405). Only the required checks (`gh api
  'repos/{owner}/{repo}/rules/branches/main'`) gate a merge; a report-only
  check (`codecov/patch`, Sonar) is triaged, not waited on. Merge an outside
  contributor's PR only after `dco` passed on its head, and never push to it
  (swarm-routing/.github#288; CONTRIBUTING "Merge when CI is green").
- `review / coderabbit` is required (swarm-routing/.github#294), so
  auto-merge may be enabled at once; still fix or answer every CodeRabbit
  thread before resolving it, and call a PR thread-free only after
  `pulls/N/comments` and the reviews show none. Where the gate is not
  required yet, wait with `pr_status.py gate REPO#N`
  (swarm-routing/.github#238).
- Never add a `Signed-off-by` trailer, for the maintainer or anyone else
  (CONTRIBUTING "Outside contributions").
- Never delete a stale branch or ask the maintainer to: org-bot's daily
  `branch-sweep` does (swarm-routing/.github#595).
- Releases are cut on request only, once the version's `release:vX.Y.Z`
  issues and its ladder exit criteria are done; never approve a gated publish;
  recover a failed publish with "Re-run all jobs"; read a DOI from Zenodo,
  never type it; never dispatch the site's `release-sync.yml` by hand
  (swarm-routing/.github#571; CONTRIBUTING "Cutting a release").
- Cite a paper by its `https://doi.org/<DOI>` link, read from its record
  (`lit-search`), or a DOI-less work by its publisher's page; never point into
  or name the private paper library.
- Never dismiss a security alert or handle a leaked secret: both are the
  maintainer's; review `security-autofix.yml`'s PRs like any other
  (swarm-routing/.github#629; CONTRIBUTING "Security alerts").
- An ns-3 bug, or its investigation, gets an RCAPA ticket in
  swarm-routing/sim-tools first (`NS3-NNN`), then its doc and register row;
  every workaround links the ID, and upstream reports go out only through
  swarm-routing/ns3-upstream-report. A regression in a published library
  version gets one in that library's repository (`<PREFIX>-NNN`), open until a
  release carries the fix; the pins and `git tag --contains` decide, never
  memory (CONTRIBUTING "RCAPA", "ns-3 bugs (RCAPA)").
<!-- org-sync:end agent-defaults -->

## Where to look

| You want to… | Go to |
|--------------|-------|
| Add an ns-3 version | nothing: the weekly run picks up a new upstream release (`tools/ns3_matrix.py`); an older one is built on demand with `workflow_dispatch` `versions` |
| Change what a release gets, a base image digest, or add a profile | `tools/ns3_matrix.py` (+ its test) and the `Dockerfile` profile `case` |
| Handle an image request (another distro, compiler, version) | the *Image request* form's issue; supported set and its reasons in README "Need another distribution…" and #19. The org's forms in `.github/ISSUE_TEMPLATE/` are org-sync items (`forms = true`; swarm-routing/.github#318) |
| Add a stock ns-3 module to the images | `NS3_MODULES` in `docker/Dockerfile` (every downstream repo inherits it) |
| Change how contrib modules build | `docker/scripts/build-contrib.sh` (+ `test/smoke.sh`) |
| The reference image this was derived from | AntHocNet `docker/Dockerfile.ns3`, `.github/workflows/images.yml` |
| The org's invariants, labels, issue shape | [`swarm-routing/.github` CONTRIBUTING.md](https://github.com/swarm-routing/.github/blob/main/CONTRIBUTING.md) |
| The reference implementation and its history | [`swarm-routing/AntHocNet`](https://github.com/swarm-routing/AntHocNet) (`AGENTS.md`, `CONTEXT.md`, `docs/adr/`) |
| Pick up open work | this repo's issues — highest open `priority:P*` first; newest open `handoff` issue for work in flight |
