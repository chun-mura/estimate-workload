#!/usr/bin/env bash
# Copy Codex custom-agent TOML to a directory Codex actually reads.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash scripts/install-codex-agents.sh [--check] [--project] [--dest DIR]

Codex が読む場所へ custom agent の TOML をコピーする。
プラグイン導入だけでは届かない。

  既定        ~/.codex/agents （このマシンの全プロジェクト）
  --project   今のリポの .codex/agents （チーム共有）
  --dest DIR  コピー先を明示（テスト用）
  --check     コピーせず、正本との差分を見る
EOF
}

root=$(cd "$(dirname "$0")/.." && pwd)
src="$root/.codex/agents"
dest="$HOME/.codex/agents"
mode=install

while [ $# -gt 0 ]; do
  case "$1" in
    --check)
      mode=check
      shift
      ;;
    --project)
      dest="$(pwd)/.codex/agents"
      shift
      ;;
    --dest)
      if [ $# -lt 2 ]; then
        echo "install-codex-agents: --dest needs a directory" >&2
        exit 2
      fi
      dest=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "install-codex-agents: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ ! -d "$src" ]; then
  echo "install-codex-agents: source missing: $src" >&2
  exit 1
fi

shopt -s nullglob
files=("$src"/*.toml)
if [ ${#files[@]} -eq 0 ]; then
  echo "install-codex-agents: no .toml in $src" >&2
  exit 1
fi

status=0
if [ "$mode" = check ]; then
  for src_file in "${files[@]}"; do
    name=$(basename "$src_file")
    dest_file="$dest/$name"
    if [ ! -f "$dest_file" ]; then
      echo "codex-agents $name: WARN not installed; run: bash scripts/install-codex-agents.sh"
      status=1
      continue
    fi
    if cmp -s "$src_file" "$dest_file"; then
      echo "codex-agents $name: OK"
    else
      echo "codex-agents $name: WARN stale; run: bash scripts/install-codex-agents.sh"
      status=1
    fi
  done
  exit "$status"
fi

mkdir -p "$dest"
for src_file in "${files[@]}"; do
  name=$(basename "$src_file")
  cp "$src_file" "$dest/$name"
  echo "codex-agents $name: installed $dest/$name"
done
