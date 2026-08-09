"""openroland-jxl: JXL job-file survey point parser and extractor adapter.

This package parses Leica/Trimble JXL job-file (``JOBFile``) XML
documents and exposes them through the same canonical
``openroland-survey-core`` extraction, XLSX, and database APIs used by the
Cube and RW5 format libraries. It never imports ``cad_server`` and has
no DXF or CAD geometry behavior; that integration lives in the
``cad-server`` project, which depends on this library instead of
embedding its own JXL parser.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from openroland_survey import database as survey_database
from openroland_survey import extractors
from openroland_survey.records import (
    ExtractionResult,
    ImportSummary,
    XlsxSummary,
)
from sqlalchemy import Engine

from openroland_jxl.extractor import JxlExtractor
from openroland_jxl.models import (
    JxlEnvironment,
    JxlParseResult,
    JxlPoint,
    JxlPointRecord,
)
from openroland_jxl.parser import JxlParseError, JxlParser

__all__ = [
    "JxlEnvironment",
    "JxlExtractor",
    "JxlParseError",
    "JxlParseResult",
    "JxlParser",
    "JxlPoint",
    "JxlPointRecord",
    "export_to_database",
    "export_to_xlsx",
    "extract_points",
]


def extract_points(
    source_path: Union[str, Path], *, include_keyed_in: bool = False
) -> ExtractionResult:
    """Extract canonical survey points from one JXL file.

    Args:
        source_path: Path of the ``.jxl`` file to extract.
        include_keyed_in: Whether ``KeyedIn`` points should be kept
            instead of excluded.

    Returns:
        The extraction result: source metadata, canonical records, and
        diagnostics.
    """
    extractor = JxlExtractor(include_keyed_in=include_keyed_in)
    return extractors.extract_file(source_path, extractor)


def export_to_xlsx(
    source_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    *,
    include_keyed_in: bool = False,
    overwrite: bool = False,
) -> XlsxSummary:
    """Extract one JXL file and write it to a single XLSX workbook.

    Args:
        source_path: Path of the ``.jxl`` file to extract.
        output_path: Destination ``.xlsx`` path. Defaults to the
            source's directory and stem with an ``.xlsx`` extension.
        include_keyed_in: Whether ``KeyedIn`` points should be kept
            instead of excluded.
        overwrite: Whether to replace an existing file at the output
            path.

    Returns:
        A summary of the written workbook.
    """
    extractor = JxlExtractor(include_keyed_in=include_keyed_in)
    return extractors.export_file_to_xlsx(
        source_path, extractor, output_path, overwrite=overwrite
    )


def export_to_database(
    source_path: Union[str, Path],
    database: Union[str, Path, Engine],
    *,
    include_keyed_in: bool = False,
    source_crs: Optional[str] = None,
) -> ImportSummary:
    """Extract one JXL file and import it into a canonical database.

    Args:
        source_path: Path of the ``.jxl`` file to extract.
        database: Either an already-configured SQLAlchemy ``Engine``, a
            full SQLAlchemy URL, or a plain SQLite file path.
        include_keyed_in: Whether ``KeyedIn`` points should be kept
            instead of excluded.
        source_crs: Coordinate reference system to use for records that
            lack their own latitude/longitude, unless the JXL
            ``Environment`` section already provided a recognizable one.

    Returns:
        A summary of what was imported, linked, or skipped.
    """
    extractor = JxlExtractor(include_keyed_in=include_keyed_in)
    engine = (
        database
        if isinstance(database, Engine)
        else survey_database.create_engine(database)
    )
    return extractors.import_file_to_database(
        source_path, extractor, engine, source_crs=source_crs
    )
