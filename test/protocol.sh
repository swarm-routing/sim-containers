#!/usr/bin/env bash
# Copyright (c) 2026 Daniel Joppi (https://github.com/swarm-routing)
# SPDX-License-Identifier: MIT OR GPL-2.0-only
#
# Protocol-image test, run inside an ns3-protocol-dev image (docker/protocol/Dockerfile)
# with this repo mounted at /src:
#
#   docker run --rm -v "$PWD:/src:ro" ghcr.io/swarm-routing/ns3-protocol-dev:latest-debug \
#       bash /src/test/protocol.sh
#
# An ns3-dev image has no /opt/ns-3/.swarm-modules.env: the stage says SKIP.
# On a protocol image it proves the promise protocol CI relies on:
#   1. the record: every prebuilt module (SWARM_PREBUILT) is at its path, a
#      release tag and a 40-char commit, linked as contrib/<name> and built,
#      and SWARM_MODULE_SPECS names exactly those paths;
#   2. the prebuilt modules are what a consumer builds: ns3-build-contrib with
#      SWARM_MODULE_SPECS alone compiles none of their objects again
#      (invariant 10: same configure line, same quality hook);
#   3. a protocol module on both (test/fixtures/protocol-hello), built as
#      reusable-ns3-ci.yml builds one (--strict-warnings on it only, its
#      dependencies by their image paths), compiles itself and the
#      executables that link every module, and never a prebuilt library or
#      test object; Ninja's step count stays under MAX_STEPS (as the smoke's);
#   4. the fixture's suite and the prebuilt modules' own suites pass on this
#      tree and profile (sanitized included).
# ok() and bad() always return 0, so `test && ok ... || bad ...` is a true
# if/else here.
# shellcheck disable=SC2015
set -euo pipefail

MAX_STEPS=${MAX_STEPS:-40}
NS3=${NS3DIR:-/opt/ns-3}
envfile="$NS3/.swarm-modules.env"
if [ ! -f "$envfile" ]; then
    echo "  SKIP  no $envfile: not an ns3-protocol-dev image (the protocol stage applies to those only)"
    exit 0
fi
# shellcheck source=/dev/null
. "$envfile"

fails=0
ok()  { echo "  ok    $*"; }
bad() { echo "  FAIL  $*" >&2; fails=$((fails + 1)); }

echo "protocol: the record ($envfile)"
names=(); specs=()
while read -r spec commit path; do
    [ -n "$spec" ] || continue
    name=${spec%%=*}; names+=("$name"); specs+=("$name=$path")
    ref=${spec#*@}; ref=${ref%%:*}
    [[ "$ref" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] && ok "$name: release tag $ref" || bad "$name: '$ref' is not a release tag vX.Y.Z"
    [[ "$commit" =~ ^[0-9a-f]{40}$ ]] && ok "$name: commit $commit" || bad "$name: '$commit' is not a 40-char commit"
    [ -f "$path/CMakeLists.txt" ] && ok "$name: sources at $path" || bad "$name: no CMakeLists.txt in $path"
    [ "$(readlink "$NS3/contrib/$name" 2>/dev/null)" = "$path" ] && ok "$name: contrib/$name -> $path" \
        || bad "$name: contrib/$name is not a link to $path"
    compgen -G "$NS3/build/lib/libns3*-${name}-*.so" >/dev/null && ok "$name: library built" || bad "$name: no library in $NS3/build/lib"
done <<< "${SWARM_PREBUILT:-}"
[ "${#names[@]}" -gt 0 ] || bad "SWARM_PREBUILT lists no module"
[ "${SWARM_MODULE_SPECS:-}" = "${specs[*]}" ] && ok "SWARM_MODULE_SPECS = ${specs[*]}" \
    || bad "SWARM_MODULE_SPECS='${SWARM_MODULE_SPECS:-}', expected '${specs[*]}'"
[ "${SWARM_MODULES:-}" = "${names[*]}" ] && ok "SWARM_MODULES = ${names[*]}" || bad "SWARM_MODULES='${SWARM_MODULES:-}', expected '${names[*]}'"

steps_of() { grep -oE '^\[[0-9]+/[0-9]+\]' "$1" | sed -E 's#.*/([0-9]+)\]#\1#' | sort -n | tail -1; }
# A compile or link step of a prebuilt module's library or test library (its
# examples are left out: routing-bench's programs relink when an arm module
# joins the tree, by design).
rebuilt() {
    local m pat=""
    for m in "${names[@]}"; do pat="${pat:+$pat|}contrib/$m/[^ ]*CMakeFiles/$m(-test)?\\.dir/|contrib/$m/_deps/|lib[^ /]*-$m(-test)?-[a-z]+\\.(so|a)"; done
    grep -E '^\[[0-9]+/[0-9]+\] (Building|Linking)' "$1" | grep -E "$pat" | grep -v '/examples/' || true
}

work=$(mktemp -d)
echo "protocol: the prebuilt modules alone are up to date"
# shellcheck disable=SC2086  # SWARM_MODULE_SPECS holds one word per module
ns3-build-contrib $SWARM_MODULE_SPECS > "$work/alone.log" 2>&1 || { cat "$work/alone.log"; bad "ns3-build-contrib \$SWARM_MODULE_SPECS failed"; }
again=$(rebuilt "$work/alone.log")
[ -z "$again" ] && ok "nothing of theirs recompiled ($(steps_of "$work/alone.log") steps)" \
    || bad "prebuilt modules rebuilt (configure-line drift, invariant 10):"$'\n'"$again"

echo "protocol: a protocol module compiles only itself"
suites=(--suite protocol-hello); for m in "${names[@]}"; do suites+=(--suite "$m"); done
# shellcheck disable=SC2086
if ns3-build-contrib --strict-warnings --quality-modules protocol-hello "${suites[@]}" \
        $SWARM_MODULE_SPECS protocol-hello=/src/test/fixtures/protocol-hello > "$work/consumer.log" 2>&1; then
    ok "fixture built under --strict-warnings; suites passed: protocol-hello ${names[*]}"
else
    tail -60 "$work/consumer.log"; bad "the fixture build or a suite failed"
fi
steps=$(steps_of "$work/consumer.log")
echo "protocol: ninja steps for the protocol build = ${steps:-0} (max $MAX_STEPS)"
[ "${steps:-0}" -le "$MAX_STEPS" ] && ok "warm: ${steps:-0} steps" || bad "${steps} steps: the warm tree was missed"
again=$(rebuilt "$work/consumer.log")
[ -z "$again" ] && ok "no prebuilt library or test object recompiled" \
    || bad "prebuilt modules rebuilt by a consumer build:"$'\n'"$again"

[ "$fails" -eq 0 ] || { echo "protocol: $fails check(s) failed" >&2; exit 1; }
echo "protocol: all checks passed"
