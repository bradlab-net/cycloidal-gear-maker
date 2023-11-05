import inspect
import json
import math
from dataclasses import asdict, dataclass, field


@dataclass
class CycloidalGearSettings:
    rotor_thickness: float = field(
        default=0.4, metadata={"canonical_name": "Rotor Thickness", "units": "mm"}
    )
    rotor_diameter: float = field(
        default=3.4, metadata={"canonical_name": "Rotor Diameter", "units": "mm"}
    )
    rotor_bearing_hole_diameter: float = field(
        default=1.5875,
        metadata={"canonical_name": "Rotor Bearing Hole Diameter", "units": "mm"},
    )
    rotor_spacing: float = field(
        default=0.1, metadata={"canonical_name": "Rotor Spacing", "units": "mm"}
    )

    camshaft_diameter: float = field(
        default=1.0, metadata={"canonical_name": "Camshaft Diameter", "units": "mm"}
    )

    ring_gear_margin: float = field(
        default=0.02, metadata={"canonical_name": "Ring Gear Margin", "units": "mm"}
    )

    ring_gear_wall_thickness: float = field(
        default=0.5,
        metadata={"canonical_name": "Ring Gear Wall Thickness", "units": "mm"},
    )

    ring_gear_pins: int = field(
        default=20, metadata={"canonical_name": "Ring Gear Pins"}
    )

    output_hole_count: int = field(
        default=6, metadata={"canonical_name": "Output Hole Count"}
    )

    output_pin_diameter: float = field(
        default=0.305, metadata={"canonical_name": "Output Pin Diameter", "units": "mm"}
    )

    output_plate_thickness: float = field(
        default=0.3,
        metadata={"canonical_name": "Output Plate Thickness", "units": "mm"},
    )

    @property
    def ring_gear_thickness(self):
        """{"canonical_name": "Ring Gear Thickness", "units": "mm"}"""
        return self.rotor_thickness * 2 + self.rotor_spacing * 3

    @property
    def ring_gear_outer_diameter(self):
        """{"canonical_name": "Ring Gear Outer Diamter", "units": "mm"}"""
        return self.rotor_diameter + self.ring_gear_wall_thickness

    @property
    def rotor_radius(self):
        """{"canonical_name": "Rotor Radius", "units": "mm"}"""
        return self.rotor_diameter / 2

    @property
    def rotor_lobes(self):
        """{"canonical_name": "Rotor Lobes"}"""
        return self.ring_gear_pins - 1

    @property
    def ring_gear_pin_radius(self):
        """{"canonical_name": "Ring Gear Pin Radius", "units": "mm"}"""
        return self.rotor_diameter * math.pi / self.ring_gear_pins / 4

    @property
    def eccentric_offset(self):
        """{"canonical_name": "Eccentric Offset", "units": "mm"}"""
        return 0.5 * self.ring_gear_pin_radius

    @property
    def output_circle_diameter(self):
        """{"canonical_name": "Output Circle Diameter", "units": "mm"}"""
        return (
            self.rotor_diameter + self.rotor_bearing_hole_diameter
        ) / 2 - self.ring_gear_pin_radius * 1.5

    @property
    def output_hole_diameter(self) -> float:
        """{"canonical_name": "Output Hole Diameter", "units": "mm"}"""
        return self.output_pin_diameter + self.ring_gear_pin_radius

    @property
    def maximum_distance(self):
        """{"canonical_name": "Maximum Distance", "units": "mm"}"""
        return 0.25 * self.ring_gear_pin_radius

    @property
    def minimum_distance(self):
        """{"canonical_name": "Minimum Distance"}"""
        return 0.5 * self.maximum_distance
    
    @property
    def reduction_rate(self) -> str:
        """{"canonical_name": "Reduction Rate"}"""
        return f"1:{self.rotor_lobes}"

    def get_fields(self) -> dict:
        members = inspect.getmembers(self)
        fields: dict = dict(
            [
                (field.name, field)
                for field in list(
                    list(filter(lambda x: x[0] == "__dataclass_fields__", members))[0][
                        1
                    ].values()
                )
            ]
        )
        return fields

    @classmethod
    def _get_property_list(cls) -> list:
        return [x for x in dir(cls) if isinstance(getattr(cls, x), property)]

    def get_properties(self) -> dict:
        property_names: list = CycloidalGearSettings._get_property_list()
        property_name: str
        properties: dict = dict(
            [
                (
                    property_name,
                    json.loads(getattr(CycloidalGearSettings, property_name).__doc__),
                )
                for property_name in property_names
            ]
        )

        return properties

    def dumps(self) -> str:
        settings: dict = asdict(self)
        return json.dumps(settings)
