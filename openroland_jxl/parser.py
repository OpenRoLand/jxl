"""Secure, streaming parser for JXL job-file (``JOBFile``) documents.

The parser accepts namespace-qualified or unqualified documents, streams
``Reductions/Point`` and ``FieldBook/PointRecord`` elements with
:func:`lxml.etree.iterparse`, clearing completed elements as it goes so a
large JXL file never requires holding a second full in-memory copy of the
document. External entity resolution and network access are disabled so
an untrusted JXL file cannot trigger an XXE or SSRF through this parser.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import (
    Any,
    BinaryIO,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Tuple,
    Union,
)

import attrs
from lxml import etree
from openroland_survey.records import IssueSeverity, ParseIssue

from openroland_jxl.models import (
    JxlEcefDeltas,
    JxlEnvironment,
    JxlGpsTime,
    JxlGrid,
    JxlParseResult,
    JxlPoint,
    JxlPointRecord,
    JxlPrecision,
    JxlQualityControl1,
    JxlQualityControl2,
    JxlWgs84,
)

logger = logging.getLogger(__name__)

__all__ = ["JxlParser"]

#: Local (namespace-stripped) tag name expected at the document root.
_ROOT_TAG = "JOBFile"

#: Keyword arguments applied to every ``iterparse`` call in this module to
#: disable external entity resolution, network access, and DTD loading.
_SECURE_PARSER_KWARGS: Dict[str, Any] = {
    "resolve_entities": False,
    "no_network": True,
    "dtd_validation": False,
    "load_dtd": False,
    "huge_tree": False,
}

_RECORD_SCALAR_MAP = {
    "ID": "point_id",
    "Name": "name",
    "Code": "code",
    "Description": "description",
    "Method": "creation_method",
    "SurveyMethod": "survey_method",
    "Classification": "classification",
    "Deleted": "deleted",
}
_POINT_SCALAR_MAP = {
    "ID": "point_id",
    "Name": "name",
    "Code": "code",
    "SurveyMethod": "method",
    "Classification": "classification",
}
_DESCRIPTION_TAGS = frozenset({"Description", "Description1"})
_GRID_FIELD_MAP = {"North": "north", "East": "east", "Elevation": "elevation"}
_WGS84_FIELD_MAP = {
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Height": "height",
}
_PRECISION_FIELD_MAP = {"Horizontal": "horizontal", "Vertical": "vertical"}
_ECEF_DELTA_MAP = {"DeltaX": "delta_x", "DeltaY": "delta_y", "DeltaZ": "delta_z"}
_QC1_SCALAR_MAP = {
    "NumberOfSatellites": "number_of_satellites",
    "RelativeDOPs": "relative_dops",
    "PDOP": "pdop",
    "HDOP": "hdop",
    "VDOP": "vdop",
    "RMS": "rms",
    "NumberOfPositionsUsed": "number_of_positions_used",
    "HorizontalStandardDeviation": "horizontal_standard_deviation",
    "VerticalStandardDeviation": "vertical_standard_deviation",
    "MonitorStatus": "monitor_status",
}
_QC2_SCALAR_MAP = {
    "NumberOfSatellites": "number_of_satellites",
    "ErrorScale": "error_scale",
    "VCVxx": "vcv_xx",
    "VCVxy": "vcv_xy",
    "VCVxz": "vcv_xz",
    "VCVyy": "vcv_yy",
    "VCVyz": "vcv_yz",
    "VCVzz": "vcv_zz",
}
_KNOWN_POINT_RECORD_TAGS = frozenset(
    {
        "ID",
        "Name",
        "Code",
        "Description",
        "Description1",
        "Description2",
        "Method",
        "SurveyMethod",
        "Classification",
        "Deleted",
        "Grid",
        "ComputedGrid",
        "LocalGrid",
        "WGS84",
        "Local",
        "ECEF",
        "Precision",
        "QualityControl1",
        "QualityControl2",
        "ECEFDeltas",
    }
)
_KNOWN_REDUCTION_POINT_TAGS = frozenset(
    {
        "ID",
        "Name",
        "Code",
        "Description",
        "Description1",
        "Description2",
        "SurveyMethod",
        "Classification",
        "Features",
        "Grid",
        "WGS84",
        "Local",
    }
)
_CRS_HINT_NAMES = frozenset({"epsgcode", "epsg"})


class JxlParseError(ValueError):
    """Raised when a document's root element is not a JXL job file."""


def _local_name(tag: Any) -> str:
    """Return the namespace-stripped local name of an element tag."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _text(elem: Any) -> Optional[str]:
    """Return the stripped text content of an element, or ``None``."""
    if elem.text is None:
        return None
    stripped = elem.text.strip()
    return stripped or None


def _parse_boolean(text: Optional[str]) -> Optional[bool]:
    """Parse JobXML ``booleanType`` text."""
    if text is None:
        return None
    folded = text.strip().casefold()
    if folded == "true":
        return True
    if folded == "false":
        return False
    return None


def _parse_int(text: Optional[str]) -> Optional[int]:
    """Parse integer text, returning ``None`` on failure."""
    if text is None:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _release(elem: Any) -> None:
    """Free memory for a fully processed element and its earlier siblings."""
    elem.clear()
    parent = elem.getparent()
    if parent is not None:
        while elem.getprevious() is not None:
            del parent[0]


def _check_root(stream: BinaryIO) -> None:
    """Validate that a document's root element is a JXL job file."""
    context = etree.iterparse(
        stream, events=("start",), **_SECURE_PARSER_KWARGS
    )
    for _, elem in context:
        if _local_name(elem.tag) != _ROOT_TAG:
            raise JxlParseError(
                "root element is %r; expected %r"
                % (_local_name(elem.tag), _ROOT_TAG)
            )
        return
    raise JxlParseError("document has no root element")


def _parse_grid(elem: Any) -> Tuple[JxlGrid, Dict[str, str]]:
    """Build a :class:`JxlGrid` and leftover grid leaf values."""
    fields: Dict[str, Optional[str]] = {}
    extras: Dict[str, str] = {}
    for child in elem:
        local = _local_name(child.tag)
        attribute = _GRID_FIELD_MAP.get(local)
        text = _text(child)
        if attribute is not None:
            fields[attribute] = text
        elif local and text is not None:
            extras[local] = text
    return JxlGrid(**fields), extras


def _parse_wgs84(elem: Any) -> JxlWgs84:
    """Build a :class:`JxlWgs84` from one ``WGS84`` element."""
    fields: Dict[str, Optional[str]] = {}
    for child in elem:
        local = _local_name(child.tag)
        attribute = _WGS84_FIELD_MAP.get(local)
        if attribute is not None:
            fields[attribute] = _text(child)
    return JxlWgs84(**fields)


def _parse_precision(elem: Any) -> JxlPrecision:
    """Build a :class:`JxlPrecision` from one ``Precision`` element."""
    fields: Dict[str, Optional[str]] = {}
    for child in elem:
        local = _local_name(child.tag)
        attribute = _PRECISION_FIELD_MAP.get(local)
        if attribute is not None:
            fields[attribute] = _text(child)
    return JxlPrecision(**fields)


def _parse_gps_time(elem: Any) -> JxlGpsTime:
    """Build a :class:`JxlGpsTime` from ``StartTime``/``EndTime``."""
    gps_week: Optional[int] = None
    seconds: Optional[str] = None
    for child in elem:
        local = _local_name(child.tag)
        if local == "GPSWeek":
            gps_week = _parse_int(_text(child))
        elif local == "Seconds":
            seconds = _text(child)
    return JxlGpsTime(gps_week=gps_week, seconds=seconds)


def _parse_quality_control1(elem: Any) -> JxlQualityControl1:
    """Build a :class:`JxlQualityControl1` from one ``QualityControl1``."""
    fields: Dict[str, Any] = {}
    for child in elem:
        local = _local_name(child.tag)
        if local == "StartTime":
            fields["start_time"] = _parse_gps_time(child)
            continue
        if local == "EndTime":
            fields["end_time"] = _parse_gps_time(child)
            continue
        attribute = _QC1_SCALAR_MAP.get(local)
        if attribute is not None:
            fields[attribute] = _text(child)
    return JxlQualityControl1(**fields)


def _parse_quality_control2(elem: Any) -> JxlQualityControl2:
    """Build a :class:`JxlQualityControl2` from one ``QualityControl2``."""
    fields: Dict[str, Optional[str]] = {}
    for child in elem:
        local = _local_name(child.tag)
        attribute = _QC2_SCALAR_MAP.get(local)
        if attribute is not None:
            fields[attribute] = _text(child)
    return JxlQualityControl2(**fields)


def _parse_ecef_deltas(elem: Any) -> JxlEcefDeltas:
    """Build a :class:`JxlEcefDeltas` from one ``ECEFDeltas`` element."""
    fields: Dict[str, Optional[str]] = {}
    for child in elem:
        local = _local_name(child.tag)
        attribute = _ECEF_DELTA_MAP.get(local)
        if attribute is not None:
            fields[attribute] = _text(child)
    return JxlEcefDeltas(**fields)


def _collect_unknown_leaves(elem: Any, prefix: str = "") -> Dict[str, str]:
    """Flatten unrecognized leaf elements under ``elem``."""
    result: Dict[str, str] = {}
    for child in elem:
        local = _local_name(child.tag)
        if not local:
            continue
        key = "%s.%s" % (prefix, local) if prefix else local
        if len(child):
            result.update(_collect_unknown_leaves(child, key))
            continue
        text = _text(child)
        if text is not None:
            result[key] = text
    return result


def _build_point_record(elem: Any) -> JxlPointRecord:
    """Build a :class:`JxlPointRecord` from one ``PointRecord`` element."""
    scalars: Dict[str, Any] = {}
    raw_values: Dict[str, Any] = {}
    typed: Dict[str, Any] = {}

    point_id = elem.get("ID")
    timestamp = elem.get("TimeStamp")

    for child in elem:
        local = _local_name(child.tag)
        if local in _DESCRIPTION_TAGS:
            scalars["description"] = _text(child)
            continue
        if local == "Grid":
            parsed_grid, grid_extras = _parse_grid(child)
            typed["grid"] = parsed_grid
            for extra_key, extra_value in grid_extras.items():
                raw_values["Grid.%s" % extra_key] = extra_value
            continue
        if local == "ComputedGrid":
            typed["computed_grid"] = _parse_grid(child)[0]
            continue
        if local == "WGS84":
            typed["wgs84"] = _parse_wgs84(child)
            continue
        if local == "Precision":
            typed["precision"] = _parse_precision(child)
            continue
        if local == "QualityControl1":
            typed["quality_control_1"] = _parse_quality_control1(child)
            continue
        if local == "QualityControl2":
            typed["quality_control_2"] = _parse_quality_control2(child)
            continue
        if local == "ECEFDeltas":
            typed["ecef_deltas"] = _parse_ecef_deltas(child)
            continue
        attribute = _RECORD_SCALAR_MAP.get(local)
        text = _text(child)
        if attribute == "deleted":
            scalars["deleted"] = _parse_boolean(text)
        elif attribute == "point_id" and point_id is None:
            scalars["point_id"] = text
        elif attribute is not None:
            scalars[attribute] = text
        elif local and local not in _KNOWN_POINT_RECORD_TAGS:
            if len(child):
                raw_values.update(_collect_unknown_leaves(child, local))
            elif text is not None:
                raw_values[local] = text

    if point_id is not None:
        scalars["point_id"] = point_id
    if timestamp is not None:
        scalars["timestamp"] = timestamp

    return JxlPointRecord(raw_values=raw_values, **scalars, **typed)


def _collect_point_records(stream: BinaryIO) -> Dict[str, JxlPointRecord]:
    """Stream every ``FieldBook/PointRecord`` into a merge-key mapping."""
    records: Dict[str, JxlPointRecord] = {}
    context = etree.iterparse(stream, events=("end",), **_SECURE_PARSER_KWARGS)
    for _, elem in context:
        local = _local_name(elem.tag)
        if local == "PointRecord":
            parent = elem.getparent()
            if parent is not None and _local_name(parent.tag) == "FieldBook":
                record = _build_point_record(elem)
                if record.deleted:
                    logger.log(
                        1,
                        "skipping deleted PointRecord %r",
                        record.point_id or record.name,
                    )
                else:
                    key = record.merge_key
                    if key is not None:
                        records[key] = record
            _release(elem)
        elif local == "Point":
            _release(elem)
    del context
    return records


def _build_point(
    elem: Any, records_by_key: Mapping[str, JxlPointRecord]
) -> JxlPoint:
    """Build a :class:`JxlPoint` from one ``Reductions/Point`` element."""
    scalars: Dict[str, Optional[str]] = {}
    raw_values: Dict[str, Any] = {}
    grid: Optional[JxlGrid] = None
    wgs84: Optional[JxlWgs84] = None

    for child in elem:
        local = _local_name(child.tag)
        if local == "Grid":
            grid, grid_extras = _parse_grid(child)
            for extra_key, extra_value in grid_extras.items():
                raw_values["Grid.%s" % extra_key] = extra_value
            continue
        if local == "WGS84":
            wgs84 = _parse_wgs84(child)
            continue
        if local in _DESCRIPTION_TAGS:
            scalars["description"] = _text(child)
            continue
        attribute = _POINT_SCALAR_MAP.get(local)
        text = _text(child)
        if attribute is not None:
            scalars[attribute] = text
        elif local and local not in _KNOWN_REDUCTION_POINT_TAGS:
            if len(child):
                raw_values.update(_collect_unknown_leaves(child, local))
            elif text is not None:
                raw_values[local] = text

    point_id = scalars.get("point_id")
    name = scalars.get("name")
    merge_key = point_id or name
    record = records_by_key.get(merge_key) if merge_key is not None else None

    return JxlPoint(
        point_id=point_id,
        name=name,
        code=scalars.get("code"),
        description=scalars.get("description"),
        method=scalars.get("method"),
        classification=scalars.get("classification"),
        grid=grid,
        wgs84=wgs84,
        record=record,
        raw_values=raw_values,
    )


def _flatten_leaves(elem: Any, prefix: str = "") -> Dict[str, str]:
    """Flatten every leaf element under ``elem`` into a dotted mapping."""
    result: Dict[str, str] = {}
    for child in elem:
        local = _local_name(child.tag)
        if not local:
            continue
        key = "%s.%s" % (prefix, local) if prefix else local
        if len(child):
            result.update(_flatten_leaves(child, key))
            continue
        text = _text(child)
        if text is not None:
            result[key] = text
    return result


def _build_environment(elem: Any) -> JxlEnvironment:
    """Build a :class:`JxlEnvironment` from one ``Environment`` element."""
    raw_values = _flatten_leaves(elem)
    crs_identifier: Optional[str] = None
    for key, value in raw_values.items():
        local_key = key.rsplit(".", 1)[-1]
        if local_key.casefold() in _CRS_HINT_NAMES:
            digits = "".join(
                character for character in value if character.isdigit()
            )
            if digits:
                crs_identifier = "EPSG:%s" % (digits,)
                break
    return JxlEnvironment(crs_identifier=crs_identifier, raw_values=raw_values)


def _collect_points_and_environment(
    stream: BinaryIO, records_by_key: Mapping[str, JxlPointRecord]
) -> Tuple[List[JxlPoint], Optional[JxlEnvironment]]:
    """Stream every ``Reductions/Point`` and the ``Environment`` section."""
    points: List[JxlPoint] = []
    environment: Optional[JxlEnvironment] = None
    context = etree.iterparse(stream, events=("end",), **_SECURE_PARSER_KWARGS)
    for _, elem in context:
        local = _local_name(elem.tag)
        if local == "Point":
            parent = elem.getparent()
            if parent is not None and _local_name(parent.tag) == "Reductions":
                points.append(_build_point(elem, records_by_key))
            _release(elem)
        elif local == "Environment":
            environment = _build_environment(elem)
            _release(elem)
        elif local == "PointRecord":
            _release(elem)
    del context
    return points, environment


@attrs.define
class JxlParser:
    """Parses JXL job-file documents into raw, format-specific models."""

    def parse_file(self, path: Union[str, Path]) -> JxlParseResult:
        """Parse a JXL document from a file on disk."""
        resolved = Path(path)

        def _opener() -> BinaryIO:
            return open(resolved, "rb")

        return self._parse(_opener, str(resolved))

    def parse_bytes(
        self, content: bytes, source_label: str = "<bytes>"
    ) -> JxlParseResult:
        """Parse a JXL document already loaded into memory."""

        def _opener() -> BinaryIO:
            return io.BytesIO(content)

        return self._parse(_opener, source_label)

    def _parse(
        self, opener: Callable[[], BinaryIO], source_label: str
    ) -> JxlParseResult:
        """Run the two-pass parse shared by :meth:`parse_file`/`parse_bytes`."""
        source_path = Path(source_label)
        try:
            with opener() as stream:
                _check_root(stream)
            with opener() as stream:
                records_by_key = _collect_point_records(stream)
            with opener() as stream:
                points, environment = _collect_points_and_environment(
                    stream, records_by_key
                )
        except (JxlParseError, etree.XMLSyntaxError) as exc:
            logger.debug(
                "failed to parse JXL document %s: %s",
                source_label,
                exc,
                exc_info=True,
            )
            return JxlParseResult(
                issues=(
                    ParseIssue(
                        source_path=source_path,
                        severity=IssueSeverity.ERROR,
                        message=str(exc),
                    ),
                )
            )

        logger.debug(
            "parsed %d survey points from %s", len(points), source_label
        )
        return JxlParseResult(points=points, environment=environment)
