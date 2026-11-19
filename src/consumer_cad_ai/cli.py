"""Command-line interface. JSON goes to stdout; diagnostics go to stderr."""

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

from .design import Design


def _payload(path):
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


def _doctor():
    from .freecad_bridge import find_freecad
    from build123d import Box
    try:
        freecad = find_freecad()
    except FileNotFoundError as error:
        freecad = str(error)
    solid = Box(1, 1, 1)
    return {"passed": solid.is_valid and abs(solid.volume - 1.0) < 1e-8,
            "platform": platform.platform(), "python": platform.python_version(),
            "packages": {p: version(p) for p in ("consumer-cad-ai", "build123d", "cadquery-ocp", "mcp")},
            "freecad_console": freecad}


def _parser():
    cli = argparse.ArgumentParser(prog="consumer-cad", description=__doc__)
    sub = cli.add_subparsers(dest="action", required=True)
    for name, help_text in [
        ("doctor", "report versions and run a 1 mm³ CAD kernel check"),
        ("serve", "start the stdio MCP server"), ("serve-remote", "start the configured OAuth MCP endpoint"),
        ("defaults", "print the enclosure parameters"), ("schema", "print the JSON assembly specification"),
    ]:
        sub.add_parser(name, help=help_text)
    check = sub.add_parser("check", help="measure and check an enclosure")
    check.add_argument("design", type=Path, nargs="?")
    opt = sub.add_parser("optimize", help="find a verified enclosure height")
    opt.add_argument("design", type=Path)
    opt.add_argument("--min-height", required=True, type=float)
    opt.add_argument("--max-height", required=True, type=float)
    opt.add_argument("--step", default=0.5, type=float)
    opt.add_argument("--save-design", type=Path, help="write verified parameters to a new JSON file")
    for name in ("demo", "build", "build-spec", "recipe"):
        cmd = sub.add_parser(name, help={"demo": "export the hinged enclosure demo", "build": "export an enclosure",
                                        "build-spec": "export a declarative assembly", "recipe": "execute a local Python CAD recipe"}[name])
        if name != "demo":
            cmd.add_argument("source", type=Path)
        if name == "recipe":
            cmd.add_argument("--parameters", type=Path, help="optional JSON parameter overrides")
        cmd.add_argument("--out", required=True, type=Path, help="new result directory")
        cmd.add_argument("--freecad", action=argparse.BooleanOptionalAction, default=None,
                         help="require or disable FCStd (default: use FreeCAD if installed)")
    return cli


def _execute(args):
    if args.action == "doctor":
        return _doctor()
    if args.action == "defaults":
        return Design().to_dict()
    if args.action == "schema":
        from .solid_spec import spec_schema
        return spec_schema()
    if args.action == "check":
        from .geometry import verify
        return verify(Design.from_dict(_payload(args.design)))
    if args.action == "optimize":
        from .optimize import optimize_height
        report = optimize_height(Design.from_dict(_payload(args.design)), args.min_height, args.max_height, args.step)
        if args.save_design and report["passed"]:
            with args.save_design.open("x", encoding="utf-8") as stream:
                json.dump(report["design"], stream, indent=2)
                stream.write("\n")
        return report

    from .pipeline import run_enclosure, run_recipe, run_spec
    if args.action == "recipe":
        return run_recipe(args.source, _payload(args.parameters), args.out, args.freecad)
    if args.action == "build-spec":
        return run_spec(_payload(args.source), args.out, args.freecad)
    return run_enclosure(_payload(getattr(args, "source", None)), args.out, args.freecad)


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.action == "serve":
            from .server import main as serve
            serve()
            return 0
        if args.action == "serve-remote":
            from .remote import serve_remote
            serve_remote()
            return 0
        result = _execute(args)
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2))
        return 0 if result.get("passed", True) else 2
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"consumer-cad: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
