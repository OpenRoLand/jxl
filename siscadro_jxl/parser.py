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
from siscadro_survey.records import IssueSeverity, ParseIssue

from siscadro_jxl.models import (
    JxlEnvironment,
    JxlParseResult,
    JxlPoint,
    JxlPointRecord,
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

_RECORD_FIELD_MAP = {
    "ID": "point_id",
    "Name": "name",
    "Code": "code",
    "Description": "description",
}
_POINT_FIELD_MAP = {
    "ID": "point_id",
    "Name": "name",
    "Code": "code",
    "SurveyMethod": "method",
}
_DESCRIPTION_TAGS = frozenset({"Description", "Description1"})
_GRID_FIELD_MAP = {"North": "north", "East": "east", "Elevation": "elevation"}
_CRS_HINT_NAMES = frozenset({"epsgcode", "epsg"})


class JxlParseError(ValueError):
    """Raised when a document's root element is not a JXL job file."""


def _local_name(tag: Any) -> str:
    """Return the namespace-stripped local name of an element tag.

    Args:
        tag: The raw ``lxml`` element tag, which may be a plain string, a
            Clark-notation ``{uri}local`` string, or a non-string value
            for comments/processing instructions.

    Returns:
        The local tag name, or an empty string for non-string tags.
    """
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _text(elem: Any) -> Optional[str]:
    """Return the stripped text content of an element, or ``None``.

    Args:
        elem: The element to read text from.

    Returns:
        The stripped text, or ``None`` when the element has no text or
        the text is blank.
    """
    if elem.text is None:
        return None
    stripped = elem.text.strip()
    return stripped or None


def _release(elem: Any) -> None:
    """Free memory for a fully processed element and its earlier siblings.

    This is the standard ``lxml`` idiom for bounding memory use during a
    streaming parse: once an element's ``end`` event has fired, neither
    it nor any of its now-superseded earlier siblings are needed again.

    Args:
        elem: The just-finished element.
    """
    elem.clear()
    parent = elem.getparent()
    if parent is not None:
        while elem.getprevious() is not None:
            del parent[0]


def _check_root(stream: BinaryIO) -> None:
    """Validate that a document's root element is a JXL job file.

    Only the opening tag is read, regardless of document size.

    Args:
        stream: A readable, seek-from-start binary stream.

    Raises:
        JxlParseError: If the root element's local name is not
            :data:`_ROOT_TAG`.
        lxml.etree.XMLSyntaxError: If the document is not well-formed.
    """
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


def _build_point_record(elem: Any) -> JxlPointRecord:
    """Build a :class:`JxlPointRecord` from one ``PointRecord`` element."""
    fields: Dict[str, Optional[str]] = {}
    raw_values: Dict[str, Any] = {}
    for child in elem:
        local = _local_name(child.tag)
        attribute = _RECORD_FIELD_MAP.get(local)
        text = _text(child)
        if attribute is not None:
            fields[attribute] = text
        elif local:
            raw_values[local] = text
    return JxlPointRecord(raw_values=raw_values, **fields)


def _collect_point_records(stream: BinaryIO) -> Dict[str, JxlPointRecord]:
    """Stream every ``FieldBook/PointRecord`` into a merge-key mapping.

    Only ``PointRecord`` and ``Point`` elements are released as they are
    seen: releasing every element unconditionally would clear a parent's
    children (and their text) before the parent itself could be read,
    since ``end`` events fire bottom-up.

    Args:
        stream: A readable binary stream positioned at the start of the
            document.

    Returns:
        A mapping of merge key (point ID, falling back to name) to the
        corresponding :class:`JxlPointRecord`.
    """
    records: Dict[str, JxlPointRecord] = {}
    context = etree.iterparse(stream, events=("end",), **_SECURE_PARSER_KWARGS)
    for _, elem in context:
        local = _local_name(elem.tag)
        if local == "PointRecord":
            parent = elem.getparent()
            if parent is not None and _local_name(parent.tag) == "FieldBook":
                record = _build_point_record(elem)
                key = record.merge_key
                if key is not None:
                    records[key] = record
            _release(elem)
        elif local == "Point":
            # Not needed in this pass; release eagerly to bound memory.
            _release(elem)
    del context
    return records


def _build_point(
    elem: Any, records_by_key: Mapping[str, JxlPointRecord]
) -> JxlPoint:
    """Build a :class:`JxlPoint` from one ``Point`` element.

    Args:
        elem: The ``Reductions/Point`` element to read.
        records_by_key: Field-book records collected in an earlier pass,
            used to merge matching metadata by point ID or name.

    Returns:
        The parsed reduced point, merged with its field-book record when
        one shares its merge key.
    """
    fields: Dict[str, Optional[str]] = {}
    grid_fields: Dict[str, Optional[str]] = {}
    raw_values: Dict[str, Any] = {}
    for child in elem:
        local = _local_name(child.tag)
        if local == "Grid":
            for grid_child in child:
                grid_local = _local_name(grid_child.tag)
                grid_attribute = _GRID_FIELD_MAP.get(grid_local)
                text = _text(grid_child)
                if grid_attribute is not None:
                    grid_fields[grid_attribute] = text
                elif grid_local:
                    raw_values["Grid.%s" % grid_local] = text
            continue
        attribute = _POINT_FIELD_MAP.get(local)
        text = _text(child)
        if attribute is not None:
            fields[attribute] = text
        elif local in _DESCRIPTION_TAGS:
            fields["description"] = text
        elif local:
            raw_values[local] = text

    point_id = fields.get("point_id")
    name = fields.get("name")
    merge_key = point_id or name
    record = records_by_key.get(merge_key) if merge_key is not None else None

    return JxlPoint(
        point_id=point_id,
        name=name,
        code=fields.get("code"),
        description=fields.get("description"),
        method=fields.get("method"),
        north=grid_fields.get("north"),
        east=grid_fields.get("east"),
        elevation=grid_fields.get("elevation"),
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
    """Build a :class:`JxlEnvironment` from one ``Environment`` element.

    A coordinate reference system identifier is recognized heuristically
    from any leaf element whose local tag name is ``EPSG`` or
    ``EPSGCode``, taking its digits as the EPSG code.
    """
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
    """Stream every ``Reductions/Point`` and the ``Environment`` section.

    Args:
        stream: A readable binary stream positioned at the start of the
            document.
        records_by_key: Field-book records to merge into matching points.

    Returns:
        A tuple of the parsed points, in document order, and the parsed
        environment metadata (``None`` when the document has none).
    """
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
            # Not needed in this pass; release eagerly to bound memory.
            _release(elem)
    del context
    return points, environment


@attrs.define
class JxlParser:
    """Parses JXL job-file documents into raw, format-specific models.

    An instance has no configurable state; it is a class only so it can
    be swapped or mocked the same way as other parser/extractor
    collaborators in this library.
    """

    def parse_file(self, path: Union[str, Path]) -> JxlParseResult:
        """Parse a JXL document from a file on disk.

        Args:
            path: Path of the ``.jxl`` file to parse.

        Returns:
            The parsed points, environment metadata, and diagnostics. A
            malformed document or unrecognized root element is reported
            as an :class:`~siscadro_survey.records.ParseIssue` rather
            than raised.
        """
        resolved = Path(path)

        def _opener() -> BinaryIO:
            return open(resolved, "rb")

        return self._parse(_opener, str(resolved))

    def parse_bytes(
        self, content: bytes, source_label: str = "<bytes>"
    ) -> JxlParseResult:
        """Parse a JXL document already loaded into memory.

        Args:
            content: Raw XML bytes of the document.
            source_label: Label used as the
                :attr:`~siscadro_survey.records.ParseIssue.source_path`
                of any reported diagnostics.

        Returns:
            The parsed points, environment metadata, and diagnostics.
        """

        def _opener() -> BinaryIO:
            return io.BytesIO(content)

        return self._parse(_opener, source_label)

    def _parse(
        self, opener: Callable[[], BinaryIO], source_label: str
    ) -> JxlParseResult:
        """Run the two-pass parse shared by :meth:`parse_file`/`parse_bytes`.

        The first pass validates the root element and collects field-book
        records; the second streams reduced points and the environment
        section, merging in the field-book metadata collected in the
        first pass. Each pass opens a fresh stream from ``opener`` so
        neither pass needs to hold the whole document tree in memory.
        """
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

        return JxlParseResult(points=points, environment=environment)
