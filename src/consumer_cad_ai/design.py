"""Millimetre parameters of the serviceable hinged battery compartment."""

from dataclasses import asdict, dataclass, fields
from math import isfinite
from typing import Mapping


@dataclass(frozen=True)
class Design:
    length: float = 72.0
    width: float = 40.0
    height: float = 13.0
    wall: float = 1.6
    lid_thickness: float = 1.2
    lid_gap: float = 0.25
    fixed_cover_length: float = 32.0
    pcb_length: float = 24.0
    pcb_width: float = 28.0
    pcb_thickness: float = 1.6
    battery_length: float = 25.0
    battery_width: float = 20.0
    battery_thickness: float = 5.0
    clearance: float = 0.4
    open_angle_deg: float = 110.0
    sweep_step_deg: float = 15.0

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ValueError(f"{f.name} must be a finite number")
        for key in ("wall", "lid_thickness", "pcb_thickness", "battery_thickness"):
            if getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")
        if not (0 <= self.lid_gap <= 2 and 0 < self.clearance <= 5):
            raise ValueError("Require 0 <= lid_gap <= 2 and 0 < clearance <= 5 mm")
        if min(self.width, self.length) <= 2 * self.wall + 12 or self.height <= self.wall:
            raise ValueError("Tray dimensions must leave space for a cavity and hinge")
        if not 12 < self.fixed_cover_length < self.length - 8:
            raise ValueError("fixed_cover_length must leave space for both panels")
        if min(self.pcb_length, self.pcb_width) <= 9 or min(self.battery_length, self.battery_width) <= 6:
            raise ValueError("PCB or battery is too small for the template's mounting features")
        if not (0 < self.open_angle_deg <= 180 and 1 <= self.sweep_step_deg <= 90):
            raise ValueError("Require 0 < open_angle_deg <= 180 and 1 <= sweep_step_deg <= 90")

    @classmethod
    def from_dict(cls, data: Mapping) -> "Design":
        if not isinstance(data, Mapping):
            raise ValueError("Design must be an object")
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError("Unknown design parameters: " + ", ".join(sorted(map(str, unknown))))
        return cls(**data)

    def to_dict(self) -> dict:
        return asdict(self)
