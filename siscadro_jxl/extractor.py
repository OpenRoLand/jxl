"""Canonical survey point extractor adapter for JXL job files.

:class:`JxlExtractor` implements the
:class:`siscadro_survey.extractors.SurveyPointExtractor` protocol,
translating the raw models produced by :mod:`siscadro_jxl.parser` into the
canonical :class:`~siscadro_survey.records.SurveyPointRecord` shape shared
by every source format adapter. Canonical-model decisions (which points
to keep, how to map fields, what to report as an issue) live only here;
:mod:`siscadro_jxl.parser` and :mod:`siscadro_jxl.models` stay usable on
their own for callers that only need the raw JXL structure.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Union

from siscadro_survey import services
from siscadro_survey.records import (
    ExtractionResult,
    IssueSeverity,
    ParseIssue,
    SourceFormat,
    SurveyPointRecord,
)

from siscadro_jxl.models import JxlPoint
from siscadro_jxl.parser import JxlParser

logger = logging.getLogger(__name__)

__all__ = ["JxlExtractor"]


def _to_coordinate(value: Optional[str]) -> Optional[Decimal]:
    """Convert one raw Grid coordinate string to a finite ``Decimal``.

    Args:
        value: The raw text value read from a ``Grid`` element, or
            ``None`` when the element was missing.

    Returns:
        The parsed ``Decimal``, or ``None`` when ``value`` is missing,
        non-numeric, or not finite.
    """
    if value is None:
        return None
    try:
        decimal_value = Decimal(value.strip())
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    return decimal_value


def _merged_text(point: JxlPoint, attribute: str) -> Optional[str]:
    """Return ``point``'s own value for ``attribute``, or its record's.

    Args:
        point: The reduced point to read from.
        attribute: Name of the attribute shared by ``JxlPoint`` and
            ``JxlPointRecord`` (``name``, ``code``, or ``description``).

    Returns:
        The point's own value when non-empty, otherwise the matching
        field-book record's value, otherwise ``None``.
    """
    own_value = getattr(point, attribute)
    if own_value:
        return own_value
    if point.record is not None:
        return getattr(point.record, attribute)
    return None


def _build_source_values(point: JxlPoint) -> Dict[str, Any]:
    """Build the ``source_values`` mapping for one point's canonical record."""
    source_values: Dict[str, Any] = dict(point.raw_values)
    if point.record is not None and point.record.raw_values:
        source_values["field_book"] = dict(point.record.raw_values)
    return source_values


class JxlExtractor:
    """Extracts canonical survey points from JXL job-file documents.

    Attributes:
        include_keyed_in: Whether ``KeyedIn`` points (manually entered,
            not measured GPS observations) are included in extraction
            results. Defaults to excluding them, matching historical
            JXL export behavior.
    """

    format_name: ClassVar[str] = SourceFormat.JXL.value
    extensions: ClassVar[Tuple[str, ...]] = (".jxl",)

    def __init__(self, *, include_keyed_in: bool = False) -> None:
        """Initialize the extractor.

        Args:
            include_keyed_in: Whether ``KeyedIn`` points should be kept
                in extraction results instead of being excluded.
        """
        self.include_keyed_in = include_keyed_in

    def can_read(self, path: Union[str, Path]) -> bool:
        """Return whether this extractor can read the file at ``path``.

        Args:
            path: Path of the candidate source file.

        Returns:
            ``True`` when ``path`` has a case-insensitive ``.jxl``
            extension.
        """
        return Path(path).suffix.lower() in self.extensions

    def extract(self, path: Union[str, Path]) -> ExtractionResult:
        """Extract canonical survey points and issues from a JXL file.

        Args:
            path: Path of the ``.jxl`` file to extract.

        Returns:
            The extraction result: source metadata, canonical records
            (excluding ``KeyedIn`` points unless :attr:`include_keyed_in`
            is set, and excluding points with incomplete or non-numeric
            Grid coordinates), and diagnostics for anything skipped.
        """
        parse_result = JxlParser().parse_file(path)
        source_crs = (
            parse_result.environment.crs_identifier
            if parse_result.environment is not None
            else None
        )
        parser_metadata: Dict[str, Any] = (
            dict(parse_result.environment.raw_values)
            if parse_result.environment is not None
            else {}
        )
        source = services.build_source_metadata(
            path,
            SourceFormat.JXL,
            source_crs=source_crs,
            parser_metadata=parser_metadata,
        )

        issues: List[ParseIssue] = list(parse_result.issues)
        records: List[SurveyPointRecord] = []
        for point in parse_result.points:
            if point.is_keyed_in and not self.include_keyed_in:
                continue
            record, issue = self._to_record(point, source.resolved_path)
            if issue is not None:
                issues.append(issue)
                continue
            if record is not None:
                records.append(record)

        return ExtractionResult(source=source, records=records, issues=issues)

    def _to_record(
        self, point: JxlPoint, source_path: Path
    ) -> Tuple[Optional[SurveyPointRecord], Optional[ParseIssue]]:
        """Convert one raw point into a canonical record, or an issue.

        Args:
            point: The raw reduced point to convert.
            source_path: Resolved path of the source file, used to label
                any reported issue.

        Returns:
            A tuple of either ``(record, None)`` on success, or
            ``(None, issue)`` when the point's Grid coordinates are
            incomplete or non-numeric.
        """
        north = _to_coordinate(point.north)
        east = _to_coordinate(point.east)
        height = _to_coordinate(point.elevation)
        if north is None or east is None or height is None:
            issue = ParseIssue(
                source_path=source_path,
                record_id=point.point_id or point.name,
                severity=IssueSeverity.WARNING,
                message=(
                    "skipped point with incomplete or non-numeric Grid "
                    "coordinates (north=%r, east=%r, elevation=%r)"
                    % (point.north, point.east, point.elevation)
                ),
            )
            return None, issue

        record = SurveyPointRecord(
            north=north,
            east=east,
            height=height,
            name=_merged_text(point, "name"),
            code=_merged_text(point, "code"),
            description=_merged_text(point, "description"),
            method=point.method,
            source_record_id=point.point_id,
            source_values=_build_source_values(point),
        )
        return record, None
