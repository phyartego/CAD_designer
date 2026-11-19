"""Load a trusted, single-file CAD recipe in the local CLI process.

A recipe defines build(parameters), accepting a JSON object and returning a list
of Component instances in closed assembly coordinates, or a Recipe for a hinged
assembly. Dimensions use millimetres and positive angles use the axis right-hand
rule. Local recipes execute with the current account's Python permissions.
"""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import runpy

from build123d import Axis, Shape

from .geometry import Component


@dataclass
class Recipe:
    parts: list[Component]
    hinge: Axis | None = None
    angles_deg: tuple[float, ...] = (0.0,)


def load_recipe(path: Path, parameters: dict) -> tuple[list[Component], Axis | None, tuple[float, ...]]:
    """Run a local .py source file and normalize its build(parameters) result."""
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".py":
        raise ValueError("A recipe must be a Python source file with the .py extension")
    if not isinstance(parameters, dict):
        raise ValueError("Recipe parameters must be a JSON object")
    # Read source each time. Rapid design edits must take effect even if the file
    # size and second-resolution modification timestamp happen to be unchanged.
    build = runpy.run_path(str(path)).get("build")
    if not callable(build):
        raise ValueError("A CAD recipe must define build(parameters)")
    result = build(dict(parameters))
    recipe = result if isinstance(result, Recipe) else Recipe(result)
    if not isinstance(recipe.parts, list) or not recipe.parts:
        raise ValueError("build(parameters) must return a non-empty list of Components or a Recipe")
    names = set()
    for part in recipe.parts:
        if not isinstance(part, Component) or not isinstance(part.shape, Shape):
            raise ValueError("Each recipe component must be a Component with a build123d Shape")
        if not isinstance(part.name, str) or not part.name.strip() or part.name in names:
            raise ValueError("Each recipe component needs a non-empty, unique name")
        if not isinstance(part.material, str) or not part.material.strip():
            raise ValueError(f"Missing material for component {part.name}")
        names.add(part.name)
    if recipe.hinge is not None and not isinstance(recipe.hinge, Axis):
        raise ValueError("Recipe hinge must be a build123d Axis")
    if not isinstance(recipe.angles_deg, (tuple, list)) or any(
        isinstance(a, bool) or not isinstance(a, (float, int)) or not isfinite(a)
        for a in recipe.angles_deg
    ):
        raise ValueError("Sampling angles must be finite numbers in degrees")
    angles = tuple(dict.fromkeys((0.0, *recipe.angles_deg)))
    moving = any(part.moving for part in recipe.parts)
    if moving != (recipe.hinge is not None) or (len(angles) > 1 and not moving):
        raise ValueError("Motion requires a hinge axis and at least one moving component")
    return recipe.parts, recipe.hinge, angles
