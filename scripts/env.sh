#!/usr/bin/env bash
# Source from bash; explicit interpreter selection, no activation of other projects.
export RSI_CODE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export RSI_RUNTIME_ROOT="${RSI_RUNTIME_ROOT:-/root/autodl-tmp/Dex_runtime/agent-rsi}"
export RSI_SOFTWARE_ROOT="$RSI_RUNTIME_ROOT/software"
export UV_PYTHON_INSTALL_DIR="$RSI_SOFTWARE_ROOT/python"
export UV_PYTHON_BIN_DIR="$RSI_SOFTWARE_ROOT/bin"
export UV_CACHE_DIR="$RSI_SOFTWARE_ROOT/cache/uv"
export TMPDIR="$RSI_SOFTWARE_ROOT/tmp"
export HF_HOME="$RSI_RUNTIME_ROOT/cache/huggingface"
export TORCH_EXTENSIONS_DIR="$RSI_SOFTWARE_ROOT/cache/torch_extensions"
export TORCHINDUCTOR_CACHE_DIR="$RSI_SOFTWARE_ROOT/cache/torchinductor"
export TRITON_CACHE_DIR="$RSI_SOFTWARE_ROOT/cache/triton"
export UV_BIN="${UV_BIN:-$HOME/.local/bin/uv}"
export PYTHONNOUSERSITE=1
export TOKENIZERS_PARALLELISM=false
export LITELLM_LOCAL_MODEL_COST_MAP=True
# Container supplies NVIDIA ICD under /etc, while SAPIEN probes /usr/share.
if test -f /etc/vulkan/icd.d/nvidia_icd.json; then
 export VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json
fi

# User-space Ubuntu EGL/Vulkan libraries; does not replace the NVIDIA driver.
if test -f "$RSI_SOFTWARE_ROOT/system/usr/lib/x86_64-linux-gnu/libEGL.so.1"; then
 export LD_LIBRARY_PATH="$RSI_SOFTWARE_ROOT/system/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
