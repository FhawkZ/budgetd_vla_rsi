#!/usr/bin/env bash
# Data lives on explicitly temporary tmpfs; only reproducible assets, never sole evidence.
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
export RSI_RUNTIME_ROOT=/dev/shm/agent-rsi-lzgpu301-20261105/runtime
export RSI_SOFTWARE_ROOT=/root/autodl-tmp/qian/.dex_env/agent-rsi-standalone/software
export UV_CACHE_DIR=/dev/shm/agent-rsi-lzgpu301-20261105/uv-cache
export UV_PYTHON_INSTALL_DIR="$RSI_SOFTWARE_ROOT/python"
export TMPDIR="$RSI_SOFTWARE_ROOT/tmp"
export RSI_PERSISTENT_RECORD_ROOT=/root/autodl-tmp/qian/Dex_runtime/agent-rsi-migration-20261105
export HF_HOME="$RSI_RUNTIME_ROOT/cache/huggingface"
export TORCH_EXTENSIONS_DIR="$RSI_SOFTWARE_ROOT/cache/torch_extensions"
export UV_BIN=/home/lzgpu301/.local/bin/uv
# Source the selected uv-managed profile only after environment deployment.

export TORCHINDUCTOR_CACHE_DIR="$RSI_SOFTWARE_ROOT/cache/torchinductor"
export TRITON_CACHE_DIR="$RSI_SOFTWARE_ROOT/cache/triton"
if test -f "$RSI_SOFTWARE_ROOT/system/usr/lib/x86_64-linux-gnu/libEGL.so.1"; then
 export LD_LIBRARY_PATH="$RSI_SOFTWARE_ROOT/system/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
