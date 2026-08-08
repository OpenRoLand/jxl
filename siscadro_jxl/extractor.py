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

from siscadro_jxl.gps_time import gps_time_to_utc, parse_gps_seconds
from siscadro_jxl.models import JxlPoint, JxlPointRecord, JxlQualityControl1, JxlWgs84
from siscadro_jxl.parser import JxlParser

logger = logging.getLogger(__name__)

__all__ = ["JxlExtractor"]


def _to_coordinate(value: Optional[str]) -> Optional[Decimal]:
    """Convert one raw Grid coordinate string to a finite ``Decimal``."""
    if value is None:
        return None
    try:
        decimal_value = Decimal(value.strip())
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    return decimal_value


def _to_float(value: Optional[str]) -> Optional[float]:
    """Convert one raw numeric string to ``float``, or ``None``."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        parsed = float(stripped)
    except ValueError:
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def _to_int(value: Optional[str]) -> Optional[int]:
    """Convert one raw integer string to ``int``, or ``None``."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _merged_text(point: JxlPoint, attribute: str) -> Optional[str]:
    """Return ``point``'s own value for ``attribute``, or its record's."""
    own_value = getattr(point, attribute)
    if own_value:
        return own_value
    if point.record is not None:
        return getattr(point.record, attribute)
    return None


def _survey_method_token(point: JxlPoint) -> Optional[str]:
    """Return the SurveyMethod token from Reductions or field book."""
    if point.method:
        return point.method
    if point.record is not None and point.record.survey_method:
        return point.record.survey_method
    return None


def _effective_wgs84(point: JxlPoint) -> Optional[JxlWgs84]:
    """Return WGS84 from Reductions, falling back to the field-book record."""
    if point.wgs84 is not None:
        return point.wgs84
    if point.record is not None and point.record.wgs84 is not None:
        return point.record.wgs84
    return None


def _observed_at_utc(record: Optional[JxlPointRecord]) -> Optional[Any]:
    """Build ``observed_at_utc`` from QC1 GPS ``StartTime``, when present."""
    if record is None or record.quality_control_1 is None:
        return None
    start = record.quality_control_1.start_time
    if start is None or start.gps_week is None:
        return None
    seconds = parse_gps_seconds(start.seconds)
    if seconds is None:
        return None
    return gps_time_to_utc(start.gps_week, seconds)


def _quality_metrics(
    record: Optional[JxlPointRecord],
) -> Dict[str, Optional[Union[float, int]]]:
    """Map typed field-book quality blocks onto canonical metric names."""
    metrics: Dict[str, Optional[Union[float, int]]] = {
        "hrms": None,
        "vrms": None,
        "pdop": None,
        "hdop": None,
        "vdop": None,
        "satellite_count": None,
    }
    if record is None:
        return metrics
    if record.precision is not None:
        metrics["hrms"] = _to_float(record.precision.horizontal)
        metrics["vrms"] = _to_float(record.precision.vertical)
    qc1: Optional[JxlQualityControl1] = record.quality_control_1
    if qc1 is not None:
        metrics["pdop"] = _to_float(qc1.pdop)
        metrics["hdop"] = _to_float(qc1.hdop)
        metrics["vdop"] = _to_float(qc1.vdop)
        metrics["satellite_count"] = _to_int(qc1.number_of_satellites)
    return metrics


def _build_source_values(
    point: JxlPoint, survey_method: Optional[str]
) -> Dict[str, Any]:
    """Build a compact ``source_values`` trace for one canonical record."""
    source_values: Dict[str, Any] = dict(point.raw_values)
    if survey_method is not None:
        source_values.setdefault("SurveyMethod", survey_method)
    if point.record is not None:
        if point.record.timestamp is not None:
            source_values["TimeStamp"] = point.record.timestamp
        if point.record.creation_method is not None:
            source_values.setdefault("Method", point.record.creation_method)
        if point.record.raw_values:
            source_values["field_book"] = dict(point.record.raw_values)
    return source_values


def _classify_survey_method(
    raw: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Map JXL ``SurveyMethod`` onto canonical method, status, and kind."""
    if raw is None:
        return None, None, None
    token = raw.strip()
    if not token:
        return None, None, None
    folded = token.casefold()
    if folded in {"fix", "networkfix"}:
        return None, "FIXED", None
    if folded in {"float", "networkfloat"}:
        return None, "FLOAT", None
    if folded == "code":
        return None, None, "imported"
    if _is_base_survey_method(folded):
        return None, None, "base"
    return token, None, None


def _is_base_survey_method(folded: str) -> bool:
    """Return whether a casefolded SurveyMethod names a base station."""
    if folded in {
        "base",
        "base station",
        "basestation",
        "reference",
        "reference station",
        "referencestation",
        "ref station",
    }:
        return True
    if folded.startswith("base ") or folded.endswith(" base"):
        return True
    return False


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
        """Initialize the extractor."""
        self.include_keyed_in = include_keyed_in

    def can_read(self, path: Union[str, Path]) -> bool:
        """Return whether this extractor can read the file at ``path``."""
        return Path(path).suffix.lower() in self.extensions

    def extract(self, path: Union[str, Path]) -> ExtractionResult:
        """Extract canonical survey points and issues from a JXL file."""
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
        """Convert one raw point into a canonical record, or an issue."""
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

        survey_method = _survey_method_token(point)
        method, status, kind = _classify_survey_method(survey_method)
        if (
            status is not None
            and point.record is not None
            and point.record.creation_method
        ):
            method = point.record.creation_method

        wgs84 = _effective_wgs84(point)
        quality = _quality_metrics(point.record)

        record = SurveyPointRecord(
            north=north,
            east=east,
            height=height,
            name=_merged_text(point, "name"),
            code=_merged_text(point, "code"),
            description=_merged_text(point, "description"),
            latitude=_to_float(wgs84.latitude) if wgs84 else None,
            longitude=_to_float(wgs84.longitude) if wgs84 else None,
            wgs84_altitude=_to_float(wgs84.height) if wgs84 else None,
            observed_at_utc=_observed_at_utc(point.record),
            method=method,
            status=status,
            kind=kind,
            satellite_count=quality["satellite_count"],
            hrms=quality["hrms"],
            vrms=quality["vrms"],
            hdop=quality["hdop"],
            vdop=quality["vdop"],
            pdop=quality["pdop"],
            source_record_id=point.point_id,
            source_values=_build_source_values(point, survey_method),
        )
        return record, None
