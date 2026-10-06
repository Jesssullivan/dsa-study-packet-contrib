#!/usr/bin/env bash
set -euo pipefail
umask 077

upstream_commit=0cf1092493af067646fc5f3db9421c6a6ec9c938
upstream_tag=v2.101.0
upstream_url=https://github.com/cli/cli.git
tool_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)

if [[ $# != 1 || $1 != /* ]]; then
  printf '%s\n' 'Usage: bootstrap.sh /absolute/path/to/new-build-directory' >&2
  exit 2
fi
build_root=$1
for dependency in git go cc python3; do
  command -v "$dependency" >/dev/null || {
    printf 'Missing dependency: %s\n' "$dependency" >&2
    exit 2
  }
done

# Only public upstream source and public Go dependencies are read at build time.
# No operator carrier is accepted by this script; it never runs hosted commands.
unset GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN
unset GH_DEBUG GH_HOST GITHUB_API_URL GITHUB_SERVER_URL
unset GIT_TRACE GIT_TRACE_CURL GIT_CURL_VERBOSE
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
export GOTOOLCHAIN=go1.27.1 GOPROXY=https://proxy.golang.org,direct
export GOSUMDB=sum.golang.org GOPRIVATE='' GONOPROXY='' GONOSUMDB='' NETRC=/dev/null

# Atomic mkdir refuses reused paths, including symlinks and active build trees.
if ! mkdir -- "$build_root"; then
  printf '%s\n' 'Build directory must be a new path with an existing parent.' >&2
  exit 2
fi
source_root=$build_root/source
git init --quiet "$source_root"
git -C "$source_root" -c credential.helper= -c core.askPass= \
  fetch --quiet --depth=1 "$upstream_url" "refs/tags/$upstream_tag:refs/tags/$upstream_tag"
[[ $(git -C "$source_root" rev-parse "$upstream_tag^{commit}") == "$upstream_commit" ]]
git -C "$source_root" checkout --quiet --detach "$upstream_commit"
[[ $(git -C "$source_root" rev-parse HEAD) == "$upstream_commit" ]]
mkdir -p "$source_root/cmd/gh-codespace-file" "$build_root/bin"
for file in main.go main_test.go README.md LICENSE; do
  install -m 0644 "$tool_dir/$file" "$source_root/cmd/gh-codespace-file/$file"
done

(
  cd -- "$source_root"
  go test ./cmd/gh-codespace-file
  go test -race ./cmd/gh-codespace-file
  go build -trimpath -o "$build_root/bin/gh-codespace-file-rebuild" ./cmd/gh-codespace-file
  go version -m "$build_root/bin/gh-codespace-file-rebuild" > "$build_root/build-info.txt"
)
"$build_root/bin/gh-codespace-file-rebuild" --help > "$build_root/help.txt"
python3 - "$build_root" "$tool_dir" "$upstream_commit" <<'PY'
import hashlib
import json
import pathlib
import sys

root, tools = map(pathlib.Path, sys.argv[1:3])
files = {
    "main.go": tools / "main.go",
    "main_test.go": tools / "main_test.go",
    "binary": root / "bin/gh-codespace-file-rebuild",
}
receipt = {
    "upstream_commit": sys.argv[3],
    "hosted_actions": "not_run",
    "operator_carrier": "not_read",
    "sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest()
               for name, path in files.items()},
}
(root / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
PY
