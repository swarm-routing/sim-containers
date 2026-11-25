#!/usr/bin/env bash
# Copyright (c) 2026 Daniel Joppi (https://github.com/swarm-routing)
# SPDX-License-Identifier: MIT OR GPL-2.0-only
#
# Patches stage (docs/adr/0002-patched-image-variant.md), run inside an
# ns3-dev image with this repo mounted at /src:
#
#   docker run --rm -v "$PWD:/src:ro" ghcr.io/swarm-routing/ns3-dev:latest-sanitized-patched \
#       bash /src/test/patches.sh
#
# A stock image carries no patch: no /opt/ns-3/.swarm-patches and no
# /usr/local/share/ns3-patches (the build's patch step ran with no patch). It
# also reports whether the tree has NS3-005's saturation line, as a note, not
# a failure: an upstream release that adopts the fix must still promote.
#
# A patched image proves its record and every patch in it:
#   1. /opt/ns-3/.swarm-patches names the patch set (= EXPECT_PATCHES when
#      set), a full sim-tools commit (= EXPECT_SIM_TOOLS_COMMIT when set),
#      and splits the set into applied and skipped, one apply.sh line each;
#   2. each patch's apply.sh (/usr/local/share/ns3-patches/<ID>, from that
#      commit), run again with --dry-run on the built tree, says "already
#      has" for an applied patch and skips for a skipped one: the tree is
#      the patched one, and applying again would change nothing;
#   3. each applied patch's reproducer runs clean where it can tell: NS3-005's
#      aodv-lifetime-overflow.cc aborts under UBSan on a stock tree, so on
#      the sanitized profile it must exit 0 and print its verdict line with
#      no sanitizer report; on another profile the overflow would be silent,
#      so it says SKIP. A patch ID this stage has no proof for fails it.
#
# EXPECT_VARIANT (stock|patched, the pipeline's matrix entry) says which the
# image must be; unset (a local run), the record decides and the stage says
# so. The container is thrown away afterwards (test/run.sh: --rm), so the
# reproducer's build in the tree changes nothing that is kept.
# ok() and bad() always return 0, so `test && ok ... || bad ...` is a true
# if/else here.
# shellcheck disable=SC2015
set -euo pipefail

NS3=${NS3DIR:-/opt/ns-3}
record="$NS3/.swarm-patches"
share=/usr/local/share/ns3-patches
expect=${EXPECT_VARIANT:-}
fails=0
ok()  { echo "  ok    $*"; }
bad() { echo "  FAIL  $*" >&2; fails=$((fails + 1)); }

if [[ -z "$expect" ]]; then
    expect=$([[ -f "$record" ]] && echo patched || echo stock)
    echo "  SKIP  EXPECT_VARIANT unset: checking the image as $expect (from $record)"
fi

if [[ "$expect" == stock ]]; then
    echo "patches: a stock image carries no patch"
    [[ ! -e "$record" ]] && ok "no $record" || bad "$record exists on a stock image"
    [[ ! -e "$share" ]] && ok "no $share" || bad "$share exists on a stock image"
    # Informational, never a failure: a later upstream release may carry the
    # same fix (once upstreamed), and its stock image must still promote. The
    # two checks above are what prove that the build applied no patch.
    h="$NS3/src/aodv/model/aodv-rtable.h"
    if [[ -f "$h" ]]; then
        if grep -qF 'lt < maxTime - Simulator::Now()' "$h"; then
            echo "  SKIP  $h has NS3-005's saturation line: this ns-3 release carries it upstream (no patch was applied)"
        else
            ok "no NS3-005 code in $h (upstream AODV as released)"
        fi
    else
        echo "  SKIP  no $h (no AODV in this tree)"
    fi
    [[ "$fails" -eq 0 ]] || { echo "patches: $fails check(s) failed" >&2; exit 1; }
    echo "patches: stock, unpatched"
    exit 0
fi
[[ "$expect" == patched ]] || { echo "  FAIL  EXPECT_VARIANT='$expect' (stock|patched)" >&2; exit 1; }

echo "patches: the record ($record)"
[[ -f "$record" ]] || { echo "  FAIL  no $record on a patched image" >&2; exit 1; }
NS3_PATCHES="" SIM_TOOLS_COMMIT="" NS3_PATCHES_APPLIED="" NS3_PATCHES_SKIPPED=""
# shellcheck source=/dev/null
. "$record"
[[ -n "$NS3_PATCHES" ]] && ok "patch set: $NS3_PATCHES" || bad "NS3_PATCHES is empty"
if [[ -n "${EXPECT_PATCHES:-}" ]]; then
    [[ "$NS3_PATCHES" == "$EXPECT_PATCHES" ]] && ok "patch set = EXPECT_PATCHES" \
        || bad "patch set '$NS3_PATCHES', expected '$EXPECT_PATCHES'"
else
    echo "  SKIP  EXPECT_PATCHES unset (nothing to compare)"
fi
[[ "$SIM_TOOLS_COMMIT" =~ ^[0-9a-f]{40}$ ]] && ok "sim-tools commit $SIM_TOOLS_COMMIT" \
    || bad "'$SIM_TOOLS_COMMIT' is not a full commit SHA"
if [[ -n "${EXPECT_SIM_TOOLS_COMMIT:-}" ]]; then
    [[ "$SIM_TOOLS_COMMIT" == "$EXPECT_SIM_TOOLS_COMMIT" ]] && ok "sim-tools commit = EXPECT_SIM_TOOLS_COMMIT" \
        || bad "sim-tools commit '$SIM_TOOLS_COMMIT', expected '$EXPECT_SIM_TOOLS_COMMIT'"
else
    echo "  SKIP  EXPECT_SIM_TOOLS_COMMIT unset (nothing to compare)"
fi
# shellcheck disable=SC2086  # one word per patch ID
both=$(printf '%s\n' $NS3_PATCHES_APPLIED $NS3_PATCHES_SKIPPED | sort)
# shellcheck disable=SC2086
[[ "$both" == "$(printf '%s\n' $NS3_PATCHES | sort)" ]] && ok "applied: '${NS3_PATCHES_APPLIED}', skipped: '${NS3_PATCHES_SKIPPED}'" \
    || bad "applied '${NS3_PATCHES_APPLIED}' + skipped '${NS3_PATCHES_SKIPPED}' is not the patch set"

# NS3-005 (swarm-routing/sim-tools#374): its reproducer, built in the tree.
proof_ns3_005() {
    local dir=$1 out rc
    if [[ "${BUILD_PROFILE:-}" != sanitized ]]; then
        echo "  SKIP  NS3-005: the reproducer tells only under UBSan (sanitized profile), this is ${BUILD_PROFILE:-unknown}"
        return 0
    fi
    cp "$dir/aodv-lifetime-overflow.cc" "$NS3/scratch/"
    if ! out=$(cd "$NS3" && ./ns3 build scratch/aodv-lifetime-overflow 2>&1); then
        printf '%s\n' "$out" | tail -40 >&2
        bad "NS3-005: the reproducer does not build"
        return 0
    fi
    set +e
    out=$(cd "$NS3" && ./ns3 run --no-build scratch/aodv-lifetime-overflow 2>&1)
    rc=$?
    set -e
    printf '%s\n' "$out" | sed 's/^/        /'
    [[ "$rc" -eq 0 ]] && ok "NS3-005: the reproducer exits 0 under the sanitizers" \
        || bad "NS3-005: the reproducer exits $rc on the patched tree"
    grep -qF 'NS3-005 not-reproduced' <<<"$out" && ok "NS3-005: verdict 'not-reproduced'" \
        || bad "NS3-005: no 'NS3-005 not-reproduced' line"
    ! grep -qE 'runtime error|AddressSanitizer|LeakSanitizer' <<<"$out" && ok "NS3-005: no sanitizer report" \
        || bad "NS3-005: a sanitizer report on the patched tree"
}

for id in $NS3_PATCHES; do
    echo "patches: $id"
    dir="$share/$id"
    [[ -f "$dir/apply.sh" ]] || { bad "$id: no $dir/apply.sh"; continue; }
    line=$(bash "$dir/apply.sh" --dry-run "$NS3" 2>&1) || { bad "$id: apply.sh --dry-run failed: $line"; continue; }
    echo "        $line"
    applied=0
    [[ " $NS3_PATCHES_APPLIED " == *" $id "* ]] && applied=1
    if [[ "$applied" -eq 1 ]]; then
        [[ "$line" == *"already has"*skipped* ]] && ok "$id: applied at build, apply.sh now says already patched" \
            || bad "$id: recorded as applied, but apply.sh says: $line"
    else
        [[ "$line" == *skipped* ]] && ok "$id: skipped at build, apply.sh still skips" \
            || bad "$id: recorded as skipped, but apply.sh says: $line"
        echo "  SKIP  $id: not applied to this tree (apply.sh skipped it), no reproducer to run"
        continue
    fi
    case "$id" in
        NS3-005) proof_ns3_005 "$dir" ;;
        *) bad "$id: test/patches.sh has no proof for this patch (add one)" ;;
    esac
done

[[ "$fails" -eq 0 ]] || { echo "patches: $fails check(s) failed" >&2; exit 1; }
echo "patches: $NS3_PATCHES proven"
