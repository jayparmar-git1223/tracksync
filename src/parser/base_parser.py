"""
base_parser.py — Abstract Base Parser

All console parsers must inherit from BaseParser and implement
the parse() method. This enforces a consistent interface across
all console adapters (DiGiCo, Yamaha, Allen & Heath, etc.)

The parse() method must always return a Session object.
This Session object then flows into any DAW exporter.

Architecture:
    BaseParser (abstract)
        └── DiGiCoParser
        └── YamahaParser  (future)
        └── AllenHeathParser (future)
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from models.session import Session

# Set up module-level logger
logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """
    Abstract base class for all console session parsers.

    Subclasses must implement:
        - parse(file_path: str) -> Session

    All parsers must:
        - Read the source file
        - Extract all track/channel data
        - Return a fully-populated Session object
        - Log warnings for any data that couldn't be parsed
        - Raise ParserError on fatal failures
    """

    def __init__(self, console_name: str):
        """
        Parameters
        ----------
        console_name : str
            The human-readable name of the console this parser handles.
            e.g. "DiGiCo SD Range", "Yamaha CL Series"
        """
        self.console_name = console_name
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def parse(self, file_path: str) -> Session:
        """
        Parse a console session file and return a Session object.

        Parameters
        ----------
        file_path : str
            The path to the console session/report file.

        Returns
        -------
        Session
            A fully-populated Universal Session object.

        Raises
        ------
        ParserError
            If the file cannot be read or parsed.
        FileNotFoundError
            If the file does not exist.
        """
        ...

    def _validate_file(self, file_path: str) -> Path:
        """
        Validates that the file exists and is readable.

        Parameters
        ----------
        file_path : str
            Path to the file to validate.

        Returns
        -------
        Path
            A pathlib.Path object for the validated file.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ParserError
            If the file is empty.
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Session file not found: {file_path}")

        if path.stat().st_size == 0:
            raise ParserError(f"Session file is empty: {file_path}")

        self.logger.info(f"[INFO] Validated file: {file_path} ({path.stat().st_size} bytes)")
        return path

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} console='{self.console_name}'>"


class ParserError(Exception):
    """
    Raised when a parser encounters a fatal error it cannot recover from.

    This might happen if:
    - The file format is unrecognized
    - The RTF is so malformed it cannot be decoded
    - Required section headers are missing
    - The channel list is completely empty after parsing
    """
    pass
