"""Generate the bundled desktop phone stand demo and open its result folder."""

import argparse
import os
from pathlib import Path
from uuid import uuid4

from consumer_cad_ai.cli import main as cad


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-open", action="store_true", help="print the result path without opening Explorer")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    recipe = root / "examples" / "desktop_stand.py"
    output = root / "outputs" / f"desktop-stand-{uuid4().hex[:12]}"
    report = output.parent / (output.name + ".json")
    output.parent.mkdir(exist_ok=True)
    print("正在生成铝合金桌面手机支架与工程图，请稍候…", flush=True)
    try:
        status = cad(["--json-out", str(report), "recipe", str(recipe), "--out", str(output), "--freecad"])
    finally:
        report.unlink(missing_ok=True)
    if status:
        if output.is_dir():
            print(f"请查看校验报告：{output / 'verification.json'}")
        return status
    print(f"样例已生成：{output}")
    if not args.no_open:
        os.startfile(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
