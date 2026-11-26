# Consumer CAD AI — Agent Instructions

This directory provides **Consumer CAD AI**, a verified consumer-electronics 3D CAD modelling, clearance/interference checking, and engineering drawing toolkit powered by `build123d` (Open CASCADE) and FreeCAD.

## Available Interfaces

### 1. MCP Server (`consumer-cad`, stdio)
Configured in `.mcp.json` (and `mcp.json` in portable Windows releases). Exposes 10 tools:
- **Parametric Hinged Enclosure**: `enclosure_defaults`, `check_enclosure`, `optimize_enclosure_height`, `build_enclosure`
- **Declarative Multi-Part JSON (`SolidSpec`)**: `solid_schema`, `check_custom`, `build_custom`
- **Result Inspection & Artifact Retrieval**: `read_run`, `preview_run`, `read_artifact`

### 2. Local CLI
- **Portable Windows bundle**: `.\cad.cmd <subcommand>` (uses bundled `runtime\python\python.exe` and `runtime\freecad\bin\freecadcmd.exe`)
- **Source checkout**: `.\.venv\Scripts\consumer-cad.exe <subcommand>` on Windows or `.venv/bin/consumer-cad <subcommand>` on Linux

Key CLI commands:
- `doctor` — verify Python, CAD kernel, and FreeCAD console
- `recipe examples/desktop_stand.py --out <new_dir> --freecad` — run and export a custom `build123d` Python recipe
- `check` / `build` / `check-spec` / `build-spec` / `optimize`

## Working Rules
Follow the full engineering & verification workflow in `skills/consumer-cad/SKILL.md`:
1. All dimensions are in **millimetres (mm)** and angles in **degrees**.
2. Always run verification (`check_*` or `recipe`) before publishing; do not claim geometry passes without checking `passed: true` and `issues`.
3. Every build writes to a **new** immutable directory (under `workspace/` for MCP runs) containing `design.json`, `verification.json`, `manifest.json`, and on pass: `assembly.step`, `parts/*.step`, `assembly.dxf`, `assembly.pdf`, `bom.csv`, `preview.png`, and `assembly.FCStd` (when FreeCAD is enabled).
4. For freeform geometry beyond `SolidSpec` JSON (such as sweeps, lofts, or custom brackets like `examples/desktop_stand.py`), write a `build(parameters)` Python recipe and execute it with `recipe`.
