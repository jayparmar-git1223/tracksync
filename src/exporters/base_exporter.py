"""
base_exporter.py — Abstract Base Exporter

All DAW exporters must inherit from BaseExporter and implement
the export() method. This enforces a consistent interface
across all DAW adapters (REAPER, Cubase, Nuendo, etc.)

Architecture:

    Session → BaseExporter → DAW Project File
                  ↑
          All exporters inherit
          from this class.
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from models.session import Session

logger = logging.getLogger(__name__)


class BaseExporter(ABC):
    """
    Abstract base class for all DAW exporters.

    Subclasses must implement:
        - export(session: Session, output_path: str) -> str

    All exporters must:
        - Accept a Session object
        - Write a valid DAW project file to output_path
        - Return the path to the written file
        - Log all major steps
        - Raise ExporterError on fatal failures
    """

    def __init__(self, daw_name: str, file_extension: str):
        """
        Parameters
        ----------
        daw_name : str
            Human-readable name of the target DAW.
            e.g. "REAPER", "Cubase", "Nuendo"
        file_extension : str
            The file extension for this DAW's project format.
            e.g. ".rpp", ".cpr"
        """
        self.daw_name       = daw_name
        self.file_extension = file_extension
        self.logger         = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def export(self, session: Session, output_path: str) -> str:
        """
        Export a Session to a DAW project file.

        Parameters
        ----------
        session : Session
            The Universal Session object to export.
        output_path : str
            The path where the DAW project file should be written.
            The file extension will be added if not present.

        Returns
        -------
        str
            The absolute path to the written project file.

        Raises
        ------
        ExporterError
            If the session cannot be exported.
        """
        ...

    def _ensure_output_dir(self, output_path: str) -> Path:
        """
        Ensures the output directory exists, creating it if needed.

        Returns the output path as a Path object with the correct extension.
        """
        path = Path(output_path)

        # Add the correct file extension if missing
        if path.suffix.lower() != self.file_extension:
            path = path.with_suffix(self.file_extension)

        # Create parent directories
        path.parent.mkdir(parents=True, exist_ok=True)

        return path

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} daw='{self.daw_name}' ext='{self.file_extension}'>"


class ExporterError(Exception):
    """
    Raised when an exporter encounters a fatal error.

    This might happen if:
    - The session has no tracks
    - A required template file is missing
    - The output path is not writable
    - The session data is invalid for this DAW format
    """
    pass
