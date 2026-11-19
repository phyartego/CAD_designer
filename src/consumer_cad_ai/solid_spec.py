"""Declarative solid modelling with Pydantic validation and build123d booleans.

Axes are right-handed. A box starts at its minimum corner and a cylinder at
the centre of its base, along +Z. Each primitive is rotated about X, Y, then Z
through its local origin, and translated. Part transforms apply after all local
features. Both features and parts use millimetres and degrees.
"""

from math import hypot
from typing import Annotated, Literal

from build123d import Axis, Compound, Shape, Solid
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .geometry import Component


Dimension = Annotated[float, Field(ge=0.01, le=2000, strict=True, allow_inf_nan=False)]
Coordinate = Annotated[float, Field(ge=-4000, le=4000, strict=True, allow_inf_nan=False)]
Degree = Annotated[float, Field(ge=-360, le=360, strict=True, allow_inf_nan=False)]
Name = Annotated[str, Field(min_length=1, max_length=80, pattern=r"\S")]
XYZ = tuple[Coordinate, Coordinate, Coordinate]


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Transform(_Schema):
    origin: XYZ = Field(default=(0, 0, 0), description="XYZ translation in mm after rotation")
    rotation_deg: tuple[Degree, Degree, Degree] = Field(
        default=(0, 0, 0), description="Rotate about X, then Y, then Z at the origin, in degrees")


class Feature(Transform):
    op: Literal["add", "cut"] = Field(default="add", description="Apply in list order")


class Box(Feature):
    kind: Literal["box"]
    size: tuple[Dimension, Dimension, Dimension] = Field(description="Length, width, height in mm from minimum corner")


class Cylinder(Feature):
    kind: Literal["cylinder"]
    radius: Dimension
    height: Dimension = Field(description="Height along local +Z from centre of base")


class PartSpec(Transform):
    name: Name = Field(description="Unique component occurrence name")
    material: Name
    features: Annotated[list[Annotated[Box | Cylinder, Field(discriminator="kind")]],
                        Field(min_length=1, max_length=24)]
    moving: Annotated[bool, Field(strict=True)] = False

    @model_validator(mode="after")
    def check_base(self):
        if self.features[0].op != "add":
            raise ValueError("The first feature of a part must add a solid")
        return self


class Hinge(_Schema):
    origin: XYZ = Field(description="World coordinates of a point on the hinge axis in mm")
    direction: XYZ = Field(description="Nonzero axis vector in world coordinates")
    angles_deg: Annotated[list[Degree], Field(min_length=1, max_length=13)] = Field(
        description="Sampled poses in degrees. The closed zero-degree pose is always included.")

    @model_validator(mode="after")
    def check_axis(self):
        if hypot(*self.direction) < 1e-6:
            raise ValueError("Hinge direction must have nonzero length")
        if len(set(self.angles_deg) | {0}) > 13:
            raise ValueError("Maximum 13 distinct poses including the closed pose")
        return self


class SolidSpec(_Schema):
    """One rigid assembly of up to 16 parts and 96 ordered primitive features."""
    parts: Annotated[list[PartSpec], Field(min_length=1, max_length=16)]
    hinge: Hinge | None = None

    @model_validator(mode="after")
    def check_assembly(self):
        if len({part.name for part in self.parts}) != len(self.parts):
            raise ValueError("Part names must be unique")
        if sum(len(part.features) for part in self.parts) > 96:
            raise ValueError("Maximum 96 features per assembly")
        if any(part.moving for part in self.parts) != (self.hinge is not None):
            raise ValueError("Provide a hinge when the assembly contains moving parts")
        return self


def spec_schema() -> dict:
    """Return the self-contained JSON Schema for an agent authoring a new solid model."""
    return SolidSpec.model_json_schema()


def _place(shape, transform):
    for axis, degrees in zip((Axis.X, Axis.Y, Axis.Z), transform.rotation_deg):
        if degrees:
            shape = shape.rotate(axis, degrees)
    if any(transform.origin):
        shape = shape.translate(transform.origin)
    return shape


def _build_part(part):
    shape = None
    for index, feature in enumerate(part.features, start=1):
        if isinstance(feature, Box):
            tool = Solid.make_box(*feature.size)
        else:
            tool = Solid.make_cylinder(feature.radius, feature.height)
        tool = _place(tool, feature)
        if shape is None:
            shape = tool
        else:
            result = shape.fuse(tool) if feature.op == "add" else shape.cut(tool)
            if not isinstance(result, Shape):
                if not result:
                    raise ValueError(f"{part.name} feature {index} removed the entire solid")
                # Disconnected intermediate features can be joined by a later web.
                result = Compound(children=list(result))
            shape = result
    solids = shape.solids()
    if len(solids) != 1 or not solids[0].is_valid:
        raise ValueError(f"{part.name} needs one valid connected solid; found {len(solids)}")
    return Component(part.name, part.material, _place(solids[0], part), moving=part.moving)


def build_spec(spec: dict) -> tuple[list[Component], Axis | None, tuple[float, ...]]:
    """Validate a JSON solid spec and build its parts, world hinge and pose angles."""
    model = SolidSpec.model_validate(spec)
    parts = [_build_part(part) for part in model.parts]
    if model.hinge is None:
        return parts, None, (0.0,)
    hinge = model.hinge
    return parts, Axis(hinge.origin, hinge.direction), tuple(dict.fromkeys((0.0, *hinge.angles_deg)))
