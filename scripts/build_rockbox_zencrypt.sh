#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
project_root="$(cd -- "$script_dir/.." && pwd -P)"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    printf 'Usage: bash %s [BUILD_DIRECTORY]\n' "$0"
    printf 'Requires: cmake >= 3.16, make, a C/C++ compiler, tee.\n'
    printf 'Optional environment: ROCKBOX_ROOT, CC, CXX, JOBS (default: 2).\n'
    exit 0
fi
if (( $# > 1 )); then
    printf 'Error: expected at most one build directory.\n' >&2
    exit 2
fi
for tool in cmake make tee; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Error: required build tool missing: %s\n' "$tool" >&2
        exit 1
    fi
done

build_dir="${1:-$project_root/build/rockbox-tools}"
rockbox_root="${ROCKBOX_ROOT:-$project_root/rockbox}"
mkdir -p -- "$build_dir"
build_dir="$(cd -- "$build_dir" && pwd -P)"

cmake -S "$script_dir/native" -B "$build_dir" \
    -G "Unix Makefiles" \
    -DROCKBOX_ROOT="$rockbox_root" \
    -DCMAKE_BUILD_TYPE=Debug \
    2>&1 | tee "$build_dir/configure.log"
cmake --build "$build_dir" --target zen_crypt firmware_extract update_extract \
    --parallel "${JOBS:-2}" \
    2>&1 | tee "$build_dir/build.log"

printf '\nBuild complete:\n  %s\n  %s\n  %s\n' \
    "$build_dir/zen_crypt" "$build_dir/firmware_extract" "$build_dir/update_extract"
printf 'Logs: %s/configure.log and %s/build.log\n' "$build_dir" "$build_dir"
