# Copyright (c) 2026 Daniel Joppi (https://github.com/swarm-routing)
# SPDX-License-Identifier: MIT OR GPL-2.0-only
#
# The protocol-CI image, ghcr.io/swarm-routing/ns3-protocol-dev: an ns3-dev
# image with the two modules every swarm-routing protocol builds on already
# built in its warm tree, so a protocol repository's CI compiles only its own
# module:
#
#   swarm-core     swarm-routing/swarm-adapter-ns3 (the module at its root), on
#                  the swarm-routing/swarm-core release its swarm-core.lock names
#   routing-bench  swarm-routing/sim-tools, ns3/routing-bench
#
# Built by publish-protocol-images.yml from what tools/protocol_images.py
# resolves (never typed here): BASE_IMAGE is ns3-dev's latest-<profile> (or an
# on-demand <ver>-<profile>) by digest, each module is the newest release tag
# of its repository and the commit that tag names (invariant 13).
#
#   docker build -f docker/protocol/Dockerfile \
#       --build-arg BASE_IMAGE=ghcr.io/swarm-routing/ns3-dev@sha256:... \
#       --build-arg SWARM_CORE_SPEC=swarm-routing/swarm-adapter-ns3@v2.0.0 \
#       --build-arg SWARM_CORE_COMMIT=73f8f0de8417c05f97ae9903953e0825202c1f58 \
#       --build-arg 'SWARM_CORE_LOCK=swarm-routing/swarm-core@v2.0.0 5fb7c180ea3a88a71b99b7c3d11dc8e2eeccb7d4' \
#       --build-arg ROUTING_BENCH_SPEC=swarm-routing/sim-tools@v1.1.3:ns3/routing-bench \
#       --build-arg ROUTING_BENCH_COMMIT=c3e88640469acffb1cc6cccc2da4edb1641d687b \
#       -t ns3-protocol-dev:debug .
#
# The modules are built by the base image's own ns3-build-contrib, exactly as
# a consumer builds them (invariant 10: same profile flags, module list and
# quality hook, none of the quality options on), from /opt/swarm-modules/<name>.
# A consumer passes the same `name=/opt/swarm-modules/<name>` specs (recorded
# in /opt/ns-3/.swarm-modules.env as SWARM_MODULE_SPECS) before its own
# module, and Ninja finds both modules up to date: only the consumer's module,
# the routing-bench programs when it registers an arm, and the executables
# that link every module are built (test/protocol.sh measures it).
ARG BASE_IMAGE
# hadolint ignore=DL3006
FROM ${BASE_IMAGE}
# Again after FROM, for the record and the label below.
ARG BASE_IMAGE

# name=owner/repo@tag[:subdir], and the commit the tag must name.
ARG SWARM_CORE_SPEC
ARG SWARM_CORE_COMMIT
ARG ROUTING_BENCH_SPEC
ARG ROUTING_BENCH_COMMIT
# The swarm-core release the module swarm-core (swarm-adapter-ns3) locks, as
# the resolver read it from that release's swarm-core.lock: owner/repo@tag commit.
ARG SWARM_CORE_LOCK

# Each module is cloned at its tag, checked against the commit resolved with
# it (a moved tag fails the build), and kept without its .git. swarm-core's
# configure fetches the swarm-core primitives' release tarball its own
# swarm-core.lock names, checked by SHA256 there; it stays in the CMake cache,
# so a consumer's configure fetches nothing. That lock must be the one the
# resolver read (SWARM_CORE_LOCK), recorded below.
# ${specs} is unquoted on purpose: two specs, two words.
# hadolint ignore=SC2086
RUN set -eu; \
    fetch() { \
        name=$1; spec=$2; commit=$3; \
        repo=${spec%%@*}; ref=${spec#*@}; sub=""; \
        case "$ref" in *:*) sub=${ref#*:}; ref=${ref%%:*} ;; esac; \
        [ -n "$repo" ] && [ -n "$ref" ] && [ "${#commit}" = 40 ] \
            || { echo "$name: need a spec owner/repo@tag[:subdir] and a 40-char commit" >&2; exit 1; }; \
        git -c advice.detachedHead=false clone --quiet --depth 1 --branch "$ref" "https://github.com/${repo}.git" "/tmp/src-$name"; \
        got=$(git -C "/tmp/src-$name" rev-parse HEAD); \
        [ "$got" = "$commit" ] || { echo "$name: $repo@$ref is $got, expected $commit" >&2; exit 1; }; \
        mkdir -p /opt/swarm-modules; \
        cp -a "/tmp/src-$name/${sub:-.}" "/opt/swarm-modules/$name"; \
        rm -rf "/opt/swarm-modules/$name/.git" "/tmp/src-$name"; \
        printf '%s=%s %s /opt/swarm-modules/%s\n' "$name" "$spec" "$commit" "$name" >> /tmp/prebuilt; \
    }; \
    fetch swarm-core "${SWARM_CORE_SPEC}" "${SWARM_CORE_COMMIT}"; \
    fetch routing-bench "${ROUTING_BENCH_SPEC}" "${ROUTING_BENCH_COMMIT}"; \
    lockv() { sed -n "s/^SWARM_CORE_$1=//p" /opt/swarm-modules/swarm-core/swarm-core.lock; }; \
    lock="$(lockv REPO)@$(lockv TAG) $(lockv COMMIT)"; \
    [ "$lock" = "${SWARM_CORE_LOCK}" ] \
        || { echo "swarm-core: its swarm-core.lock names '$lock', expected '${SWARM_CORE_LOCK}'" >&2; exit 1; }; \
    specs="swarm-core=/opt/swarm-modules/swarm-core routing-bench=/opt/swarm-modules/routing-bench"; \
    { echo "# Modules built into this tree (docker/protocol/Dockerfile). Pass"; \
      echo "# SWARM_MODULE_SPECS to ns3-build-contrib before your own module."; \
      echo "# SWARM_PREBUILT: one line per module, name=owner/repo@tag[:subdir] commit path."; \
      echo "SWARM_MODULES=\"swarm-core routing-bench\""; \
      echo "SWARM_MODULE_SPECS=\"${specs}\""; \
      printf 'SWARM_PREBUILT="%s"\n' "$(cat /tmp/prebuilt)"; \
      echo "# SWARM_CORE_LOCK: the swarm-core release swarm-core (swarm-adapter-ns3) builds on, owner/repo@tag commit."; \
      echo "SWARM_CORE_LOCK=\"${SWARM_CORE_LOCK}\""; \
      echo "SWARM_BASE_IMAGE=\"${BASE_IMAGE}\""; \
    } > /opt/ns-3/.swarm-modules.env; \
    rm /tmp/prebuilt; \
    ns3-build-contrib ${specs}

# The sim-containers commit and run that built the image (as in
# docker/Dockerfile), after the build so a new commit changes only the config.
ARG REVISION=unknown
ARG BUILD_RUN=local
# What tools/protocol_images.py compares to decide whether an image is up to
# date: the base digest, the modules' commits and this file's hash.
ARG RECIPE=unknown
# The release of swarm-routing/swarm-adapter-ns3 (the module swarm-core), and
# the swarm-core release its swarm-core.lock names (SWARM_CORE_LOCK's).
ARG SWARM_ADAPTER_VERSION
ARG SWARM_CORE_VERSION
ARG SWARM_CORE_COMMIT_LOCKED
ARG ROUTING_BENCH_VERSION
# name=owner/repo@<40-char commit>[:subdir],... (reusable-ns3-image.yml's form)
ARG DEPENDENCIES
# version (the ns-3 release), profile, base OS and licence are inherited from
# ns3-dev; the rest describes this image.
LABEL org.opencontainers.image.source="https://github.com/swarm-routing/sim-containers" \
      org.opencontainers.image.revision="${REVISION}" \
      io.github.swarm-routing.build-run="${BUILD_RUN}" \
      org.opencontainers.image.title="ns3-protocol-dev" \
      org.opencontainers.image.description="ns3-dev with swarm-core (swarm-adapter-ns3 ${SWARM_ADAPTER_VERSION}, on swarm-core ${SWARM_CORE_VERSION}) and routing-bench ${ROUTING_BENCH_VERSION} prebuilt: protocol CI compiles only its own module" \
      io.github.swarm-routing.ns3-dev.image="${BASE_IMAGE}" \
      io.github.swarm-routing.modules="swarm-core,routing-bench" \
      io.github.swarm-routing.dependencies="${DEPENDENCIES}" \
      io.github.swarm-routing.swarm-adapter-ns3.version="${SWARM_ADAPTER_VERSION}" \
      io.github.swarm-routing.swarm-core.version="${SWARM_CORE_VERSION}" \
      io.github.swarm-routing.swarm-core.commit="${SWARM_CORE_COMMIT_LOCKED}" \
      io.github.swarm-routing.routing-bench.version="${ROUTING_BENCH_VERSION}" \
      io.github.swarm-routing.protocol-image.recipe="${RECIPE}"

WORKDIR /opt/ns-3
CMD ["bash"]
