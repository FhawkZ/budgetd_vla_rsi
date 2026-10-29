#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
profile="${1:?usage: bootstrap.sh qwen|agent|rpent|sim|robotwin}"
mkdir -p "$TMPDIR" "$UV_CACHE_DIR" "$RSI_SOFTWARE_ROOT/envs"
case "$profile" in
 qwen) py=3.12.15; lock=qwen-cu128-py312.lock ;;
 agent) py=3.12.15; lock=agent-py312.lock ;;
 rpent) py=3.12.15; lock=rpent-py312.lock ;;
 sim) py=3.11.17; lock=sim-py311.lock ;;
 robotwin) py=3.11.17; lock=robotwin-py311.lock ;;
 *) echo "Unknown profile: $profile" >&2; exit 2 ;;
esac
"$UV_BIN" python install "$py"
envdir="$RSI_SOFTWARE_ROOT/envs/$profile"
if test ! -x "$envdir/bin/python"; then "$UV_BIN" venv --python "$UV_PYTHON_INSTALL_DIR/cpython-$py-linux-x86_64-gnu/bin/python" "$envdir"; fi
index_args=(--index-url "${RSI_PYPI_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}")
if test "$profile" = rpent; then index_args=(--index-url https://pypi.org/simple --extra-index-url "${RSI_PYPI_INDEX:-https://repo.huaweicloud.com/repository/pypi/simple}" --index-strategy unsafe-best-match); fi
if test "$profile" = qwen; then index_args=(--index-url https://download.pytorch.org/whl/cu128 --extra-index-url "${RSI_PYPI_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}" --index-strategy unsafe-best-match); fi
"$UV_BIN" pip install --python "$envdir/bin/python" "${index_args[@]}" -r "$RSI_CODE_ROOT/requirements/$lock"
"$UV_BIN" pip check --python "$envdir/bin/python"
