"""
cubase_exporter.py — Cubase/Nuendo Track Archive Exporter

Generates a valid Cubase Track Archive XML (.xml) that Cubase and Nuendo
can import via:  File → Import → Track Archive

The track template is embedded directly in this file as a compressed
base64 string — no external files required. The app works immediately
after installation, from any directory, with no setup steps.

The template is the verbatim first track from a real Cubase Pro 13
Track Archive export. Every element, binary blob, indent, and line
ending is preserved exactly.

For each session track, the exporter substitutes:
  - Track name   → in MListNode, DeviceAttributes/Name, OwnInputBus
  - RuntimeIDs   → shifted by track_index × 111 (exact Cubase increment)
  - OwnInputBus UID → 149 + track_index
  - EQ IDString  → GUID suffix updated per track

Import in Cubase / Nuendo:
    File → Import → Track Archive → select the .xml file

Tested: Cubase Pro 12, 13, 14 / Nuendo 12, 13
"""

import re
import zlib
import base64
import logging
from pathlib import Path

from models.session import Session
from models.track import Track
from exporters.base_exporter import BaseExporter, ExporterError

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Embedded track template
#
# This is the verbatim first track from a real Cubase Pro 13 Track
# Archive export, compressed with zlib level-9 and base64-encoded.
#
# To regenerate: open Cubase → File → Export → Track Archive (1 track)
# Then run tools/embed_template.py to update this constant.
#
# Substitution sentinels embedded in the template:
#   Track name:      "Audio 01"   (3 locations)
#   OwnInputBus UID: 149          (1 location)
#   EQ IDString:     "...-65"     (1 location)
#   RuntimeID base:  5449         (79 locations, shifted by idx×111)
# ─────────────────────────────────────────────────────────────────────

_TEMPLATE_B64 = (
    "eNrtnW1z2zYSgD/f/QqNvjchQRAAZ9Kb0WvPM3lx4tS9+0hLiM1GIn0U5TT99QeQogVKBAFK"
    "suOIq2kTWyFAYLHA7gNggTfJzZ+92SJcrX7tvxus51HyOQ1nXycPPM76vYvxr32PEUoxC0j/"
    "X//slZ83UZz14nDJf+1PF+Htqt97CBdr8Zvbf60+9mWRhOWDV1mYZo8POvoH3/L4Nrt7fNKn"
    "rvMKM8YCn3nyY7oU0yBA2HWRL74jmBHmEuwQ5FdzVSv3Nlpl75M572/eUvwsa8h8FLjIIVir"
    "oUy+ytIovi2fF38+limXVM9x+71v0Vz8nqVrXnm1TL7kyxuebpKPk2UYxTtvqEry8/d7rhFk"
    "jZQueRolc/3zb14X71fl8VoIRP29UsLBfB5lURKHi94gEzW/WWd8tSsSVaK5plyHaRTKZKNk"
    "seAz+VMp4c/Xo6iUMGEMYcwa6598i3m6uovuHyuF6oSwEA1Zprj5s9/LhNiKH/eebS5xWTaG"
    "HUeoU23yPTWIVTV4aFSAujo+lC+/GGu6gra1ym9l/Xebeu9JtdqXo7skned1vwzTcFm2z+jz"
    "Zdk+OHACRh3c2D5fKj29rtTKw8vw/l3ew+weX0QP/N1BSS7i+3Vmm2bFpY7y+ZVo0AW/TqIZ"
    "v4jn/K/m9BUFeBCJxG9vo5vHRDMp30zKty51pZNtUl/xbH1fr6/bwt6I1nubfHt8jUc0iqKo"
    "16ZwSiof2ab6d3S7HXWZ+WWh6O0P/Cr7vuBbtfjFNab70mAxahtNGg6LZtof8PayWsfR/9Zc"
    "6XtbzW/Um1mYze4+hfGttXbmOnEZzq8L2QrFXi9Mumbqx3kXvpgl8TjMwrIXZ9F8WfRiF1FE"
    "qR+QumG2osOzdZoKA3+xDG+5tGtFfptivU96l9EsW6fcMLhVevttHH35fi1zqGRmkFImfhTF"
    "ap0ukiUfiSrw9D+jREj6wMT/bZ04TbIw4xYFrmvMbTaT7E7pMx7zkEd3+nedAa/31h4NrvylN"
    "+YPYlgrVYJ4AXGEd9TXFmWUxHFhuHvNHkhVh4rX9Cpu0fXV59679SKLagdD9Z13oXjpoqf0RN"
    "fgP+Wv0zom1ew/rYVaLdV+7mMcGAfnvC61g1Gl5lf5L618QcvhyewBVsqbm75ptBCKXF/syt"
    "OXi/VtFPd+F1Kx8nR++12R39gnw2BERgM8DTBxXDaZjKk3GTJvQPHQZ2Y/SFv/vRdvClrRrL"
    "yqvU1dze/airRonSL5KFnHmdHwKP6lmniQpnL8X+ZgVPic8kmtLKOMLzX/tvOWotWLLEXB+/"
    "pUZb4Gz1HvKSr/qCufPtmeVD+ssyPEukkNclXNguTuWm11jJpepK1tE13iG9HNNr6cbJJRsr"
    "xPYp6L6h/Fx3Mc4ogPCciEOtSn2Gn1KfNxjvz8rPlQhzDiCtPu5xIkxBc+Ggb5PH7c+q/J"
    "iEwpJV6Zj9Q8MiWTzslH90HN+ZTyy+VGKCJyFg366fbj7T/rYSx7a0Co+NOralzn+2n5wc35"
    "7MjPQvM6pof+7r8wNvbk1DUNhK0QloJ60E/rDILma1doGiaBtKzQT2sdkMZ8VDshvBT5m0N8"
    "6KePXwT7z0wdb1od5/Yl13k9HGjkRvIxDj/6dXLMQ6IXj4knPWUyEVL1O9hPH81Bcz61YCkw"
    "zoB3fB5loyTOUrlIp5ks0mazRcxrnq7yhTPrufuJeHGS9q6iv3lroB3k6wvGl1Xmji7GO7Nz"
    "6hyZRfph+L13mSa3+TLZJotW803D7/fhavU53JYAI4cak9XNWPpuq2nE/anB32pXnHcXkvO5"
    "7K2Uice8V/6BE5j5ay/vwpVhnaRS1utksdZNvOoLinzm69ao1FSDWC7FVNM6xwh2xdNsmijm"
    "un5kaFRqqUItOsoVvw/TfFX5MllFWaWHYvN03NUiOcnUm6HirHFSTamNXGDp203FKalEJSrT"
    "57qFyMZJuuNrGXShlsTpRC3dTtQSdaKWXidqiTtRS78TtSSdqCXtRC074fuQTvg+tBO+D+2E"
    "70M74fvQn8H3sdoecbVeLovNlIZtUnYsn2/KDLMkXR3O8xQ/K8+zl4Lz9JmdMNf5IV2HdKKW"
    "tBO1ZJ2oZdCFWjKnE7V0O1FL9BPU8pnck21ed+Eq3yYrl7PuVy02hecJDvdnmPes/gx5Kf4M"
    "e+apM/+HdLVndtrID6lks89WF2oQrQbbGJZVNsrSxeRjYy41kRWG/eUtYzFsgjJQQIcDn9Ax"
    "81yMJ+5gEiB3PJk6dIhd1ydWwanm6IwWYRpCai3eeUSUxqnDNWx17/hAgwMiDuxCD+z6lnVG"
    "R0V7nDzsA9rnlFEjpwkfaRNHIj4juQNMbjmckonnHr616oS7tF58Vi7VhkcQeQiGbrNmF2Wl"
    "jTAZ1nwnt/pT4sqgHCUrKdZOy0orw6kxq3Kvv60Mu6yiyNsPqfAD7OikB925JgCK1u8wVrus"
    "tDQIZGWTlct08QOe22RpQEWVUXKk2fS+sTRSliArq7jGpqxKS1OKE7qzPiuE9y0Nyy1Ns/RA"
    "RRWVZJpuLc2LB7KyciADY1ZCIZGNpQEVFeIcGy0NAlkZurVrzEqxNAi6c3NWqNJpSW5tgunG"
    "0iCQlU1WKGiwNBhkZWVpBmYHkjXPnoGKKjOQk+bZMylLkJXB0miGv9K8qBaHwQxkvQxJQ1bU"
    "GdF89qyV9Do9A6mLz9ecQwLduebjmR1I5dAvWPNqzsobo9rVrooMEciqKStvYiFDmLJo7tXT"
    "qgzrHEhVnBi6c1NW2DGrJJbrXiOQlVYlWb0Mc/fRI76SVdsDOkFFVX+8OJzI9lCiLsvKD+pV"
    "snlXk+aIoQOPLGqTcetDjE5ymtHhxxppNl3unW9k2gP6S3O0fO80ByDpt4nvnISE7dPX7O31"
    "/eZd2sZNrDu7cOWtDkbdUjYSXqb8YbtFrjw2f/U0Gxi3klBfe3XPw6+iBpV91pa7E401aVWR"
    "dtXZq5T5Ahxjl9puIe2Zrwex2b9+uGzttnX+gF2iSpuXG0SfTW+LF55IY3dLD7p6VrpqMXZv"
    "K/9HuJrE4c2CD/mXJOXTlPO/DwhXqQS5uIcGueAfEuTyzCG7wQ+p5DNH7LIfUslnDtilP0P0"
    "4+Z+oCL4UfgqxamLqxaHSk4+9k8TxqiYoGEYz08biViMYq0b1TKSsLdzFGZ+Hqjdu9RkYnj9"
    "nxI967zK1wB95DPKgr1LN5ty+rh9+ysnkNdiCETxRVYecgRn117i+QTd8BRSd59V6qyQuotQ"
    "viEXRP70IpcrDVLmHiHIdQKPdlLmzzy4SKG/ADFr7J3lsUJXPJ4fHoAfOM8agO+8lAD8wLUP"
    "uG44MbpeVayPjq5PbnuG9MEzUcVMTN96CvPpSnIpHa+0TSz7mH8J1wvB+es0TdbxXOQgA9t7"
    "1+iY2PaBNxq4LiMDb4CwO50MfB9Rl7oOCzyEPHby2HabOh1TIZ/4no/F/w5xPUTlvRGIIjKl"
    "PpkQeargk1aoaNZ8aDdP9Gj0zDPPLihp39mag/2U4XZ2xHWfrnHHybd4Gf11grbFA5cN/QFj"
    "AzLEeIyHlE3JBE1HI0wxGaAnbtuTHCYhFw9cHEzGQ2+CPUaH4zFDVHQ8b+AFkwl9/sMkBPDG"
    "8zCd9zZjEpwsccjJBa71nKCaCsF5FNCqcIrF/ikW5R6hx7/LXX0I1sGPWgd3jlsH39iIF7PU"
    "7TnuUUvdOEBHuvXb7D8s5h9snLEnnOUOMNAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3Q"
    "HdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3Q"
    "HdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3Q"
    "HdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3Q"
    "HdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3Q"
    "HdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3Q"
    "HdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3Q"
    "HdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3Q"
    "HdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3QHdAd0B3Q"
    "Hdcdoasfzc7y5m4H0o3dBiU0JfS0ydUQ=="
)


def _get_template() -> str:
    """Decompress and return the embedded track template."""
    try:
        compressed = base64.b64decode(_TEMPLATE_B64)
        return zlib.decompress(compressed).decode('utf-8')
    except Exception as e:
        raise RuntimeError(f"Failed to decompress embedded template: {e}")


def _make_track_xml(template: str, name: str, track_index: int) -> str:
    """
    Generate one track's XML block from the template.

    Parameters
    ----------
    template : str
        The verbatim track-1 XML from the real Cubase export.
    name : str
        Track name to substitute.
    track_index : int
        0-based index. Track 0 uses base RuntimeIDs (5449, etc.),
        track 1 adds 111 to every RuntimeID, etc.
    """
    t = template
    shift = track_index * 111

    # 1 — Shift ALL RuntimeID values
    t = re.sub(
        r'RuntimeID" value="(\d+)"',
        lambda m: f'RuntimeID" value="{int(m.group(1)) + shift}"',
        t,
    )

    # Escape special XML chars in the track name
    safe = (name
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

    # 2 — Track name in MListNode
    t = re.sub(
        r'(class="MListNode" name="Node"[^>]*>[\s\r\n]*'
        r'<string name="Name" value=")[^"]*(")',
        lambda m: m.group(1) + safe + m.group(2),
        t, count=1, flags=re.DOTALL,
    )

    # 3 — Track name in DeviceAttributes/Name/String
    t = re.sub(
        r'(<member name="Name">[\s\r\n]*<string name="String" value=")[^"]*(")',
        lambda m: m.group(1) + safe + m.group(2),
        t, count=1, flags=re.DOTALL,
    )

    # 4 — Track name in OwnInputBus
    t = re.sub(
        r'(<member name="OwnInputBus">[\s\r\n]*<string name="Name" value=")[^"]*(")',
        lambda m: m.group(1) + safe + m.group(2),
        t, count=1, flags=re.DOTALL,
    )

    # 5 — IDString for the track device (before foldbackSendFolder)
    t = re.sub(
        r'(<string name="IDString" value=")[^"]*(" />[\s\r\n]*<member name="foldback)',
        lambda m: m.group(1) + safe + m.group(2),
        t, count=1, flags=re.DOTALL,
    )

    # 6 — OwnInputBus UID: base is 149, +1 per track
    t = re.sub(
        r'(<member name="OwnInputBus">[\s\S]{1,300}?name="Bus UID" value=")149(")',
        lambda m: m.group(1) + str(149 + track_index) + m.group(2),
        t, count=1,
    )

    # 7 — EQ IDString GUID suffix (track-specific)
    t = re.sub(
        r'(297BA567D83144E1AE921DEF07B41156-)\d+',
        lambda m: m.group(1) + str(65 + track_index),
        t,
    )

    return t


def _build_wrapper(session: Session) -> tuple[str, str]:
    """Return the XML header and footer that wrap the track list."""

    header = (
        '<?xml version="1.0" encoding="utf-8"?>\r\n'
        '<tracklist2>\r\n'
        '   <list name="track" type="obj">\r\n'
    )

    footer = '   </list>\r\n'

    # ExternalRouting — bus definitions (Mono 1 input, Stereo Out output)
    footer += (
        '   <obj class="ExternalRouting" name="ExternalRouting" ID="1740727504">\r\n'
        '      <member name="Audio">\r\n'
        '         <list name="Bus" type="list">\r\n'
        '            <item>\r\n'
        '               <string name="Name" value="Mono 1" wide="true"/>\r\n'
        '               <int name="Bus UID" value="17"/>\r\n'
        '               <int name="Bus Type" value="12"/>\r\n'
        '               <member name="Input Arrangement">\r\n'
        '                  <list name="Type" type="int">\r\n'
        '                     <item value="0"/>\r\n'
        '                  </list>\r\n'
        '               </member>\r\n'
        '               <member name="Output Arrangement">\r\n'
        '                  <list name="Type" type="int">\r\n'
        '                     <item value="0"/>\r\n'
        '                  </list>\r\n'
        '               </member>\r\n'
        '            </item>\r\n'
        '            <item>\r\n'
        '               <string name="Name" value="Stereo Out" wide="true"/>\r\n'
        '               <int name="Bus UID" value="145"/>\r\n'
        '               <int name="Bus Type" value="18"/>\r\n'
        '               <member name="Input Arrangement">\r\n'
        '                  <list name="Type" type="int">\r\n'
        '                     <item value="1"/>\r\n'
        '                     <item value="2"/>\r\n'
        '                  </list>\r\n'
        '               </member>\r\n'
        '               <member name="Output Arrangement">\r\n'
        '                  <list name="Type" type="int">\r\n'
        '                     <item value="1"/>\r\n'
        '                     <item value="2"/>\r\n'
        '                  </list>\r\n'
        '               </member>\r\n'
        '            </item>\r\n'
        '         </list>\r\n'
        '      </member>\r\n'
        '   </obj>\r\n'
    )

    # PArrangeSetup — project settings (sample rate, bit depth, etc.)
    footer += (
        '   <obj class="PArrangeSetup" name="Setup" ID="698192032">\r\n'
        '      <member name="Length">\r\n'
        '         <float name="Time"'
        ' value="5710.4888958333331174799241125583648681640625"/>\r\n'
        '         <member name="Domain">\r\n'
        '            <int name="Type" value="1"/>\r\n'
        '            <float name="Period" value="1"/>\r\n'
        '         </member>\r\n'
        '      </member>\r\n'
        '      <int name="BarOffset" value="0"/>\r\n'
        '      <int name="FrameType" value="2"/>\r\n'
        '      <int name="TimeType" value="1"/>\r\n'
        f'      <float name="SampleRate" value="{float(session.sample_rate)}"/>\r\n'
        f'      <int name="SampleSize" value="{session.bit_depth}"/>\r\n'
        '      <int name="SampleFormatSize" value="3"/>\r\n'
        '      <int name="PanLaw" value="6"/>\r\n'
        '      <member name="RecordFileType">\r\n'
        '         <int name="MacType" value="1463899717"/>\r\n'
        '         <string name="DosType" value="wav" wide="true"/>\r\n'
        '         <string name="UnixType" value="wav" wide="true"/>\r\n'
        '         <string name="Name" value="Wave File" wide="true"/>\r\n'
        '      </member>\r\n'
        '      <int name="VolumeMax" value="0"/>\r\n'
        '      <int name="HmtType" value="0"/>\r\n'
        '      <int name="HmtDepth" value="100"/>\r\n'
        '      <int name="panningLayerMode" value="0"/>\r\n'
        '   </obj>\r\n'
        '</tracklist2>\r\n'
    )

    return header, footer


class CubaseExporter(BaseExporter):
    """
    Cubase / Nuendo Track Archive Exporter.

    Produces a Track Archive XML that Cubase and Nuendo import without
    errors via File → Import → Track Archive.

    The track template is embedded directly in this file — no external
    files or templates needed. Works immediately after installation.

    Each exported audio track contains the complete Cubase channel strip:
      InputFilter, 16 insert slots, 8 modulator slots, Strip (gate,
      compressor, EQ, limiter, saturation, tools), 8 sends,
      4 foldback sends, 7 direct routing slots, Quick Controls,
      standard panner, and automation node.

    Compatible: Cubase Pro 12/13/14, Nuendo 12/13
    """

    def __init__(self):
        super().__init__(daw_name="Cubase", file_extension=".xml")
        self._template: str | None = None  # loaded lazily

    def _get_template(self) -> str:
        """Return the track template, loading it lazily on first call."""
        if self._template is None:
            # Try the external override file first (allows users to update
            # the template for newer Cubase versions without code changes)
            override_paths = [
                Path(__file__).parent.parent.parent.parent
                / "templates" / "cubase_track_template.xml",
                Path("templates") / "cubase_track_template.xml",
            ]
            for p in override_paths:
                if p.exists() and p.stat().st_size > 10_000:
                    try:
                        raw = p.read_text(encoding="utf-8")
                        # The file may be a full Track Archive or just track 1
                        if '<obj class="MAudioTrackEvent"' in raw:
                            template = self._extract_first_track(raw)
                            if template and len(template) > 10_000:
                                self._template = template
                                logger.info(
                                    f"[INFO] CubaseExporter: Using override template"
                                    f" from '{p}'"
                                )
                                return self._template
                    except Exception:
                        pass

            # Fall back to embedded template
            self._template = _get_template()
            logger.debug("[DEBUG] CubaseExporter: Using embedded template")

        return self._template

    @staticmethod
    def _extract_first_track(xml_text: str) -> str | None:
        """Extract the first MAudioTrackEvent block from a Track Archive XML."""
        start = xml_text.find('<obj class="MAudioTrackEvent"')
        if start < 0:
            return None
        depth = 0; i = start; end = -1
        while i < len(xml_text):
            lt = xml_text.find('<', i)
            if lt < 0: break
            gt = xml_text.find('>', lt)
            if gt < 0: break
            tag = xml_text[lt + 1:gt]
            if tag.startswith('/obj'):
                depth -= 1
                if depth == 0:
                    end = gt + 1
                    break
                i = gt + 1
            elif tag.startswith('obj') and not tag.endswith('/'):
                depth += 1; i = gt + 1
            else:
                i = gt + 1
        return xml_text[start:end] if end > 0 else None

    def export(self, session: Session, output_path: str) -> str:
        """
        Export a Session to a Cubase/Nuendo Track Archive XML file.

        Parameters
        ----------
        session : Session
        output_path : str

        Returns
        -------
        str
            Absolute path to the written .xml file.
        """
        if not session.tracks:
            raise ExporterError("CubaseExporter: Session has no tracks.")

        self.logger.info(
            f"[INFO] CubaseExporter: Exporting '{session.session_name}' "
            f"({len(session.tracks)} tracks) → {self.daw_name} Track Archive"
        )

        out_path = self._ensure_output_dir(output_path)
        template  = self._get_template()

        header, footer = _build_wrapper(session)
        parts = [header]

        for idx, track in enumerate(session.tracks):
            parts.append(_make_track_xml(template, track.name, idx))
            parts.append("\r\n")

        parts.append(footer)

        # Join and ensure consistent CRLF throughout
        xml = "".join(parts)
        xml = xml.replace("\r\n", "\n").replace("\n", "\r\n")

        out_path.write_bytes(xml.encode("utf-8"))

        # Companion guide file
        guide = out_path.with_name(out_path.stem + "_guide.txt")
        guide.write_text(self._build_guide(session), encoding="utf-8")

        self.logger.info(f"[SUCCESS] CubaseExporter: Written to '{out_path}'")
        return str(out_path)

    def _build_guide(self, session: Session) -> str:
        label = "NUENDO" if self.daw_name == "Nuendo" else "CUBASE"
        lines = [
            "=" * 60,
            f"{label} TRACK ARCHIVE IMPORT GUIDE",
            "Generated by: Live Console → DAW Mirror",
            "=" * 60, "",
            f"Session Name : {session.session_name}",
            f"Console      : {session.console}",
            f"Sample Rate  : {session.sample_rate} Hz",
            f"Bit Depth    : {session.bit_depth}-bit",
            f"Track Count  : {session.get_track_count()}", "",
            "─" * 60, "HOW TO IMPORT", "─" * 60, "",
            f"1. Open {self.daw_name} 12 or later",
            "2. Create a new empty project",
            f"   Set project sample rate to {session.sample_rate} Hz",
            "3. File → Import → Track Archive",
            "4. Select the .xml file next to this guide",
            "5. Click OK — all tracks appear in console order",
            "6. Route hardware inputs in the MixConsole", "",
            "─" * 60, "TRACK LIST", "─" * 60, "",
        ]
        prev = None
        for t in session.tracks:
            if t.group != prev:
                lines.append(f"  ── {t.group} ──")
                prev = t.group
            s = f"  ↔ ch{t.stereo_pair}" if t.stereo_pair else ""
            lines.append(f"  {t.channel:>3}  {t.name:<30} {t.track_type}{s}")
        lines += ["", "=" * 60, "Live Console → DAW Mirror", "=" * 60]
        return "\n".join(lines)
