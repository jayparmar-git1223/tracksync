"""
bus.py — Bus/Subgroup data model

Represents a bus, subgroup, or aux send from the live console.
Buses become folder tracks or group channels in the DAW output.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Bus:
    """
    Represents a mix bus or subgroup on the live console.

    Attributes
    ----------
    name : str
        The bus label. e.g. "Drum Bus", "Vocal Bus", "Main LR"
    bus_type : str
        One of: "subgroup", "aux", "master", "matrix"
    channels : List[int]
        List of channel numbers that feed into this bus.
    color : str
        Hex color for DAW track coloring.
    """

    name:      str
    bus_type:  str        = "subgroup"
    channels:  List[int]  = field(default_factory=list)
    color:     str        = "#2C3E50"

    def to_dict(self) -> dict:
        return {
            "name":     self.name,
            "type":     self.bus_type,
            "channels": self.channels,
            "color":    self.color,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Bus":
        return cls(
            name=     data.get("name", "Bus"),
            bus_type= data.get("type", "subgroup"),
            channels= data.get("channels", []),
            color=    data.get("color", "#2C3E50"),
        )

    def __repr__(self) -> str:
        return f"<Bus name='{self.name}' type={self.bus_type} channels={self.channels}>"
