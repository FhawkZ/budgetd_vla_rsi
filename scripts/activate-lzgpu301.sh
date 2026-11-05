#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/env-lzgpu301.sh"
profile="${1:?usage: source scripts/activate-lzgpu301.sh skillrsi|qwen}"
case "$profile" in
 skillrsi) source "$RSI_SOFTWARE_ROOT/envs/skillrsi/bin/activate" ;;
 qwen) source /home/lzgpu301/.local/share/budgeted-vla-rsi/envs/qwen/bin/activate ;;
 *) echo "Unknown profile" >&2; return 2 ;;
esac
unset PYTHONPATH
