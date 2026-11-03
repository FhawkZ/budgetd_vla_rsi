#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
parent="$RSI_SOFTWARE_ROOT/envs/robotwin"
envdir="$RSI_SOFTWARE_ROOT/envs/skillrsi"
clip="$RSI_RUNTIME_ROOT/vendor/CLIP-d05afc436d78f1c48dc0dbf8e5980a9d471f35f6"
test -x "$parent/bin/python" && test -f "$clip/setup.py"
if ! test -x "$envdir/bin/python"; then "$UV_BIN" venv --python "$parent/bin/python" "$envdir"; fi
"$parent/bin/python" - "$parent" "$envdir" <<'PYCODE'
import pathlib,sys
base,out=map(pathlib.Path,sys.argv[1:]);sp=out/'lib/python3.11/site-packages'
(sp/'robotwin_frozen_parent.pth').write_text('import site; site.addsitedir('+repr(str(base/'lib/python3.11/site-packages'))+')\n')
PYCODE
"$UV_BIN" pip install --python "$envdir/bin/python" --no-deps ftfy==6.3.1
"$UV_BIN" pip install --python "$envdir/bin/python" --no-deps --no-build-isolation "$clip"
"$envdir/bin/python" -c 'import clip,ftfy,torch,torchvision; print("overlay imports pass")'
