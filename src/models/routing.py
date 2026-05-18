"""
routing.py — Routing data model

Represents a signal routing connection between two points in the session.
Used to capture console routing assignments for reproduction in the DAW.
"""

from dataclasses import dataclass


@dataclass
class Routing:
    """
    Represents a single routing assignment from a source to a destination.

    Attributes
    ----------
    source : str
        The origin of the signal. e.g. "Channel 1", "Drum Bus"
    destination : str
        Where the signal is routed. e.g. "Main LR", "Matrix 1"
    send_level : float
        The send level in dB. 0.0 = unity (0 dB).
    pre_fader : bool
        True if this is a pre-fader send (PFL).
    """

    source:      str
    destination: str
    send_level:  float = 0.0
    pre_fader:   bool  = False

    def to_dict(self) -> dict:
        return {
            "source":      self.source,
            "destination": self.destination,
            "send_level":  self.send_level,
            "pre_fader":   self.pre_fader,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Routing":
        return cls(
            source=      data.get("source", ""),
            destination= data.get("destination", ""),
            send_level=  data.get("send_level", 0.0),
            pre_fader=   data.get("pre_fader", False),
        )

    def __repr__(self) -> str:
        return f"<Routing {self.source} → {self.destination}>"
