#!/usr/bin/env bash
# Ubuntu 24.04 x86_64, headless. Python and FreeCAD use separate runtimes.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
root=$(pwd -P)
freecad=true
demo=true
agent_args=()
for arg in "$@"; do
    case "$arg" in
        --skip-freecad) freecad=false ;;
        --skip-demo) demo=false ;;
        --global-codex) agent_args+=(--global-codex) ;;
        *) echo "Unknown option: $arg" >&2; exit 2 ;;
    esac
done
sudo_cmd=()
if [[ $EUID != 0 ]]; then sudo_cmd=(sudo); fi
"${sudo_cmd[@]}" apt-get update
"${sudo_cmd[@]}" apt-get install -y python3 python3-venv libgl1 libglu1-mesa libxrender1 libxext6 libsm6
if "$freecad"; then
    if [[ -n ${FREECAD_CMD:-} ]]; then
        [[ -x $FREECAD_CMD ]] || { echo "Invalid FREECAD_CMD: $FREECAD_CMD" >&2; exit 1; }
    elif ! command -v freecadcmd >/dev/null && ! command -v FreeCADCmd >/dev/null; then
        # Some Noble archive mirrors have no FreeCAD candidate.
        if ! apt-cache show freecad 2>/dev/null | grep '^Package: freecad$' >/dev/null; then
            . /etc/os-release
            if [[ $ID == ubuntu && ${VERSION_CODENAME:-} == noble ]]; then
                "${sudo_cmd[@]}" apt-get install -y software-properties-common
                "${sudo_cmd[@]}" add-apt-repository -y ppa:freecad-maintainers/freecad-stable
                "${sudo_cmd[@]}" apt-get update
            fi
        fi
        "${sudo_cmd[@]}" apt-get install -y freecad
    fi
fi
python_bin=${CAD_PYTHON:-python3}
"$python_bin" -c 'import sys; assert (3, 11) <= sys.version_info[:2] <= (3, 12), "Use Python 3.11/3.12 (CAD_PYTHON=/path/to/python3.12)"'
if [[ ! -x .venv/bin/python ]]; then "$python_bin" -m venv .venv; fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/python scripts/configure_agent.py "${agent_args[@]}"
.venv/bin/consumer-cad doctor
if "$demo"; then
    mkdir -p "$root/.local/first-run"
    out=$(mktemp -d "$root/.local/first-run/run-XXXXXXXX")
    # demo creates a new target directory below the reserved run id.
    mode=--no-freecad
    if "$freecad"; then mode=--freecad; fi
    .venv/bin/consumer-cad demo --out "$out/demo" "$mode"
    if "$freecad" && [[ -z $(find "$out/demo" -iname '*.FCStd' -size +0c -print -quit) ]]; then
        echo "Demo missing its FreeCAD project in $out/demo" >&2
        exit 1
    fi
    echo "Demo output: $out/demo"
fi
echo "Ready. Start Codex with ./scripts/cad-codex. Run ./scripts/cad-codex mcp list to inspect its configuration."
