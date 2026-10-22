#!/usr/bin/env bash
# Install (or update) the unattended SWE-bench pipeline as a systemd user service
# and start it. Arguments are passed to `python -m scripts.swebench_eval pipeline`:
#
#   infra/systemd/install.sh --name lite-s20-seed7 --n 20 --seed 7 \
#       --owner you@example.com --with-gold --ablation lite-s20-seed7-v1-nogate
#
# Watch it:   tail -f ~/.cache/devpilot/swebench/pipeline.log
#             systemctl --user status devpilot-benchmark
# Stop it:    systemctl --user disable --now devpilot-benchmark
set -euo pipefail

if [ "$#" -eq 0 ]; then
  sed -n '2,12p' "$0"
  exit 1
fi

repo="$(cd "$(dirname "$0")/../.." && pwd)"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
unit="$unit_dir/devpilot-benchmark.service"

for arg in "$@"; do
  case "$arg" in *[\|\&\\]*) echo "unsupported character in argument: $arg" >&2; exit 1 ;; esac
done

mkdir -p "$unit_dir" "$HOME/.cache/devpilot/swebench"
sed -e "s|@REPO@|$repo|g" -e "s|@ARGS@|$*|g" \
  "$repo/infra/systemd/devpilot-benchmark.service.in" > "$unit"

systemctl --user daemon-reload
systemctl --user enable --now devpilot-benchmark.service
echo "Installed $unit"
systemctl --user --no-pager status devpilot-benchmark.service | head -5
