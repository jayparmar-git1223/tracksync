"""
dante_patchsheet.py — Dante / AES67 Patch Sheet Exporter

Generates network audio routing documentation from a Universal Session.

In a live show workflow, once the DAW session is created, the engineer
needs to configure the Dante (or AES67) network audio routing so that
physical inputs reach the correct DAW tracks.

This module generates:
  1. Dante Controller-style routing tables (CSV)
  2. AES67 stream assignment sheets
  3. HTML patch sheet (printable, color-coded)
  4. JSON network audio configuration

The patch sheet maps:
  Console Output → Dante Network → DAW Input

Example:
  DiGiCo Local Output 1 → Dante "Kick In" → REAPER Track 1
  DiGiCo Local Output 2 → Dante "Snare Top" → REAPER Track 2

Usage:
    from dante_patchsheet import DantePatchSheetExporter

    exporter = DantePatchSheetExporter()
    exporter.export(session, "output/patch_sheet")
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from models.session import Session
from models.track import Track, GROUP_COLORS

logger = logging.getLogger(__name__)


@dataclass
class DanteChannel:
    """Represents a single Dante network audio channel."""
    channel:        int
    name:           str
    dante_tx_name:  str   = ""    # Transmitter (source) channel name
    dante_rx_name:  str   = ""    # Receiver (destination) channel name
    device_tx:      str   = ""    # Dante transmitter device name
    device_rx:      str   = ""    # Dante receiver device name
    sample_rate:    int   = 48000
    bit_depth:      int   = 24
    latency_ms:     float = 1.0   # Dante network latency in ms
    group:          str   = "MISC"
    color:          str   = "#95A5A6"

    def to_dict(self) -> dict:
        return {
            "channel":       self.channel,
            "name":          self.name,
            "dante_tx":      f"{self.device_tx}/{self.dante_tx_name}",
            "dante_rx":      f"{self.device_rx}/{self.dante_rx_name}",
            "sample_rate":   self.sample_rate,
            "bit_depth":     self.bit_depth,
            "latency_ms":    self.latency_ms,
            "group":         self.group,
        }


class DantePatchSheetExporter:
    """
    Generates Dante/AES67 patch sheet documentation.

    Takes a Universal Session and produces routing documentation
    for the network audio layer between the console and DAW.

    The generated patch sheet tells the Dante engineer exactly
    which Dante channels to route where.

    Supported outputs:
      - HTML  (color-coded printable patch sheet)
      - CSV   (Dante Controller import format)
      - JSON  (machine-readable network config)
      - TXT   (plain text summary)
    """

    def __init__(
        self,
        console_device:  str = "Console",
        daw_device:      str = "DAW Interface",
        network_latency: float = 1.0,
    ):
        """
        Parameters
        ----------
        console_device : str
            Dante device name for the console's output interface.
            e.g. "DiGiCo SD Rack", "Yamaha TF-RACK"
        daw_device : str
            Dante device name for the DAW's input interface.
            e.g. "MADI Bridge", "Dante Virtual Soundcard"
        network_latency : float
            Target Dante network latency in milliseconds.
        """
        self.console_device  = console_device
        self.daw_device      = daw_device
        self.network_latency = network_latency

    def export(self, session: Session, output_base: str) -> dict[str, str]:
        """
        Export all patch sheet formats.

        Parameters
        ----------
        session : Session
            The session to document.
        output_base : str
            Base path for output files (no extension).

        Returns
        -------
        dict
            Mapping of format name → file path.
        """
        base = Path(output_base)
        base.parent.mkdir(parents=True, exist_ok=True)

        channels = self._build_dante_channels(session)
        outputs  = {}

        # HTML patch sheet
        html_path = base.with_name(base.name + "_dante_patch.html")
        html_path.write_text(self._build_html(session, channels), encoding="utf-8")
        outputs["html"] = str(html_path)

        # CSV (Dante Controller format)
        csv_path = base.with_name(base.name + "_dante_routes.csv")
        csv_path.write_text(self._build_csv(session, channels), encoding="utf-8")
        outputs["csv"] = str(csv_path)

        # JSON network config
        json_path = base.with_name(base.name + "_dante_config.json")
        config = {
            "session":        session.session_name,
            "console":        session.console,
            "console_device": self.console_device,
            "daw_device":     self.daw_device,
            "sample_rate":    session.sample_rate,
            "latency_ms":     self.network_latency,
            "channels":       [c.to_dict() for c in channels],
        }
        json_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        outputs["json"] = str(json_path)

        # Plain text summary
        txt_path = base.with_name(base.name + "_dante_summary.txt")
        txt_path.write_text(self._build_txt(session, channels), encoding="utf-8")
        outputs["txt"] = str(txt_path)

        logger.info(
            f"[SUCCESS] DantePatchSheet: Generated {len(outputs)} files for "
            f"'{session.session_name}' ({len(channels)} channels)"
        )
        return outputs

    # ──────────────────────────────────────────────────────────────────
    # Builders
    # ──────────────────────────────────────────────────────────────────

    def _build_dante_channels(self, session: Session) -> list[DanteChannel]:
        """Map Session tracks to Dante channel assignments."""
        channels = []
        for track in session.tracks:
            ch = DanteChannel(
                channel=       track.channel,
                name=          track.name,
                dante_tx_name= f"{track.name} O{track.channel:02d}",
                dante_rx_name= f"{track.name} I{track.channel:02d}",
                device_tx=     self.console_device,
                device_rx=     self.daw_device,
                sample_rate=   session.sample_rate,
                bit_depth=     24,
                latency_ms=    self.network_latency,
                group=         track.group,
                color=         track.color,
            )
            channels.append(ch)
        return channels

    def _build_html(self, session: Session, channels: list[DanteChannel]) -> str:
        """Build a color-coded printable HTML patch sheet."""
        now    = datetime.now().strftime("%Y-%m-%d %H:%M")
        groups = {}
        for ch in channels:
            groups.setdefault(ch.group, []).append(ch)

        rows_html = ""
        for group, chs in groups.items():
            color   = GROUP_COLORS.get(group, "#475569")
            bg_dark = self._darken_hex(color, 0.15)

            # Group header row
            rows_html += f"""
            <tr class="group-header">
              <td colspan="5" style="background:{bg_dark};color:{color};
                  padding:6px 12px;font-size:11px;font-weight:700;
                  letter-spacing:2px;border-top:2px solid {color};">
                ▶ {group}
              </td>
            </tr>"""

            for ch in chs:
                stereo = "⇌" if ch.channel % 2 == 0 and ch.group == ch.group else ""
                rows_html += f"""
            <tr>
              <td style="color:#94A3B8;text-align:center;">{ch.channel}</td>
              <td style="color:#F1F5F9;font-weight:600;">{ch.name}</td>
              <td style="color:#64748B;">{self.console_device} / {ch.dante_tx_name}</td>
              <td style="color:#64748B;">→</td>
              <td style="color:#64748B;">{self.daw_device} / {ch.dante_rx_name}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Dante Patch Sheet — {session.session_name}</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:#0A0E1A; color:#CBD5E1;
         font-family:'SF Mono','JetBrains Mono','Consolas',monospace;
         font-size:12px; padding:24px; }}
  .header {{ border-bottom:2px solid #1DB954; padding-bottom:16px; margin-bottom:24px; }}
  .header h1 {{ color:#1DB954; font-size:20px; letter-spacing:3px; }}
  .header .meta {{ color:#475569; font-size:11px; margin-top:6px; }}
  .meta span {{ margin-right:24px; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ background:#020509; color:#475569; font-size:10px; letter-spacing:2px;
        padding:8px 12px; text-align:left; border-bottom:1px solid #1E293B; }}
  td {{ padding:6px 12px; border-bottom:1px solid #0F172A; }}
  tr:hover td {{ background:#0F172A; }}
  .group-header td {{ }}
  .footer {{ margin-top:24px; color:#334155; font-size:10px; }}
  @media print {{
    body {{ background:#fff; color:#000; }}
    .header h1 {{ color:#16a34a; }}
    td,th {{ color:#374151; border-color:#e5e7eb; }}
  }}
</style>
</head>
<body>
<div class="header">
  <h1>DANTE PATCH SHEET</h1>
  <div class="meta">
    <span>Session: <strong style="color:#CBD5E1;">{session.session_name}</strong></span>
    <span>Console: {session.console}</span>
    <span>TX Device: {self.console_device}</span>
    <span>RX Device: {self.daw_device}</span>
    <span>Sample Rate: {session.sample_rate} Hz</span>
    <span>Latency: {self.network_latency} ms</span>
    <span>Generated: {now}</span>
  </div>
</div>
<table>
  <thead>
    <tr>
      <th style="width:50px;">CH</th>
      <th style="width:200px;">CHANNEL NAME</th>
      <th>DANTE TRANSMITTER (Source)</th>
      <th style="width:30px;"></th>
      <th>DANTE RECEIVER (Destination / DAW)</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
<div class="footer">
  Generated by Live Console → DAW Mirror &nbsp;|&nbsp;
  {len(channels)} channels &nbsp;|&nbsp; {now}
</div>
</body>
</html>"""

    def _build_csv(self, session: Session, channels: list[DanteChannel]) -> str:
        """Build a Dante Controller import CSV."""
        lines = [
            "# Dante Controller Route Export",
            f"# Session: {session.session_name}",
            f"# Console: {session.console}",
            f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "#",
            "Transmitter Device,Transmitter Channel,Receiver Device,Receiver Channel",
        ]
        for ch in channels:
            lines.append(
                f'"{self.console_device}","{ch.dante_tx_name}",'
                f'"{self.daw_device}","{ch.dante_rx_name}"'
            )
        return "\n".join(lines)

    def _build_txt(self, session: Session, channels: list[DanteChannel]) -> str:
        """Build a plain text patch summary."""
        lines = [
            "=" * 64,
            "DANTE PATCH SHEET",
            f"Session:     {session.session_name}",
            f"Console:     {session.console}",
            f"TX Device:   {self.console_device}",
            f"RX Device:   {self.daw_device}",
            f"Sample Rate: {session.sample_rate} Hz",
            f"Latency:     {self.network_latency} ms",
            "=" * 64,
            "",
            f"  {'CH':>3}  {'NAME':<24}  {'TX → RX'}",
            "─" * 64,
        ]
        current_group = None
        for ch in channels:
            if ch.group != current_group:
                lines.append(f"\n  ── {ch.group} ──")
                current_group = ch.group
            lines.append(
                f"  {ch.channel:>3}  {ch.name:<24}  "
                f"{self.console_device}/{ch.dante_tx_name} → "
                f"{self.daw_device}/{ch.dante_rx_name}"
            )
        lines += ["", "=" * 64, "Live Console → DAW Mirror", "=" * 64]
        return "\n".join(lines)

    @staticmethod
    def _darken_hex(hex_color: str, factor: float) -> str:
        """Darken a hex color by factor (0.0–1.0)."""
        hex_color = hex_color.lstrip("#")
        try:
            r = int(int(hex_color[0:2], 16) * factor)
            g = int(int(hex_color[2:4], 16) * factor)
            b = int(int(hex_color[4:6], 16) * factor)
            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError):
            return "#0a0e1a"
