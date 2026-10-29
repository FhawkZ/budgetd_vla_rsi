#!/usr/bin/env bash
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
profile="${1:?usage: source scripts/activate.sh qwen|agent|rpent|sim|robotwin}"
case "$profile" in qwen|agent|rpent|sim|robotwin) ;; *) echo "Unknown profile" >&2; return 2 ;; esac
source "$RSI_SOFTWARE_ROOT/envs/$profile/bin/activate"
export ROBORSI_HOME="$RSI_RUNTIME_ROOT/roborsi-home"
export ROBORSI_WORKSPACE="$ROBORSI_HOME/workspace"
if test "$profile" = agent; then
 export PYTHONPATH="$RSI_RUNTIME_ROOT/vendor/RoboRSI-90c8569705bf4004a4f79e34e650c87ab7f075d4"
elif test "$profile" = rpent; then
 export PYTHONPATH="$RSI_RUNTIME_ROOT/vendor/RPent-a744bd5f128ebef3cb8c6736cf7cd98adff681f1"
else
 unset PYTHONPATH
fi
