"""Raw, format-specific models produced by the low-level JXL parser.

These attrs classes describe exactly what one JXL job-file document
contains, before any translation into the canonical
:class:`siscadro_survey.records.SurveyPointRecord` model. They are kept
public and independent from :mod:`siscadro_jxl.extractor` so callers that
only need the raw parsed structure (for example CAD-oriented tooling) do
not have to depend on the canonical survey model.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

import attrs
from siscadro_survey.records import ParseIssue

__all__ = [
    "JxlEnvironment",
    "JxlParseResult",
    "JxlPoint",
    "JxlPointRecord",
]


def _freeze_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Return a read-only copy of a mapping, defaulting to empty.

    Args:
        value: The mapping to freeze, or ``None``.

    Returns:
        An immutable :class:`~types.MappingProxyType` wrapping a shallow
        copy of ``value``, or an empty one when ``value`` is ``None``.
    """
    if value is None:
        return MappingProxyType({})
    return MappingProxyType(dict(value))


def _freeze_points(value: Iterable["JxlPoint"]) -> Tuple["JxlPoint", ...]:
    """Convert an iterable of points into an immutable tuple.

    A concretely typed converter is used (rather than the bare ``tuple``
    builtin) so mypy's attrs plugin resolves the generated ``__init__``
    parameter to a concrete element type instead of an unbound generic.

    Args:
        value: The points to freeze.

    Returns:
        ``value`` copied into a plain ``tuple``.
    """
    return tuple(value)


def _freeze_issues(value: Iterable[ParseIssue]) -> Tuple[ParseIssue, ...]:
    """Convert an iterable of parse issues into an immutable tuple.

    See :func:`_freeze_points` for why a concrete element type is needed.

    Args:
        value: The issues to freeze.

    Returns:
        ``value`` copied into a plain ``tuple``.
    """
    return tuple(value)


@attrs.define(frozen=True, kw_only=True)
class JxlPointRecord:
    """One raw ``FieldBook/PointRecord`` entry.

    ``PointRecord`` entries carry field-book metadata that is merged into
    the corresponding ``Reductions/Point`` entry sharing the same point
    identity, so a reduced point can inherit a code or description that
    was only recorded in the field book.

    Attributes:
        point_id: Stable point identifier used to merge this record with
            its corresponding ``Reductions/Point`` entry. Falls back to
            ``name`` when the source has no explicit ID element.
        name: Point name/number as recorded in the field book.
        code: Point code/feature code.
        description: Free-text description or comment.
        raw_values: JSON-compatible mapping of every other leaf value
            found on this record, keyed by its local (namespace-stripped)
            tag name. Read-only.
    """

    point_id: Optional[str] = None
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    raw_values: Mapping[str, Any] = attrs.field(
        factory=dict, converter=_freeze_mapping
    )

    @property
    def merge_key(self) -> Optional[str]:
        """Return the key used to merge this record with a reduced point.

        Returns:
            ``point_id`` when present, otherwise ``name``, otherwise
            ``None`` when neither is available.
        """
        return self.point_id or self.name


@attrs.define(frozen=True, kw_only=True)
class JxlPoint:
    """One raw ``Reductions/Point`` reduced point.

    Grid coordinates are kept as the raw source text (rather than parsed
    numbers) so that incomplete or non-numeric values can be reported as
    diagnostics by the caller instead of silently becoming zero.

    Attributes:
        point_id: Stable point identifier, when the source provides one.
        name: Point name/number.
        code: Point feature code.
        description: Free-text description or comment.
        method: Survey method reported for this point (for example
            ``"GPS"`` or ``"KeyedIn"``).
        north: Raw ``Grid/North`` text value.
        east: Raw ``Grid/East`` text value.
        elevation: Raw ``Grid/Elevation`` text value.
        record: Matching field-book metadata merged in by point ID or
            name, when a corresponding ``PointRecord`` was found.
        raw_values: JSON-compatible mapping of every other leaf value
            found directly on this point (outside of ``Grid``), keyed by
            its local tag name. Read-only.
    """

    point_id: Optional[str] = None
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    method: Optional[str] = None
    north: Optional[str] = None
    east: Optional[str] = None
    elevation: Optional[str] = None
    record: Optional[JxlPointRecord] = None
    raw_values: Mapping[str, Any] = attrs.field(
        factory=dict, converter=_freeze_mapping
    )

    @property
    def merge_key(self) -> Optional[str]:
        """Return the key used to merge this point with a field-book record.

        Returns:
            ``point_id`` when present, otherwise ``name``, otherwise
            ``None`` when neither is available.
        """
        return self.point_id or self.name

    @property
    def is_keyed_in(self) -> bool:
        """Return whether this point's survey method is ``KeyedIn``.

        Returns:
            ``True`` when ``method`` case-insensitively equals
            ``"KeyedIn"``; ``False`` otherwise, including when ``method``
            is ``None``.
        """
        return (self.method or "").strip().casefold() == "keyedin"


@attrs.define(frozen=True, kw_only=True)
class JxlEnvironment:
    """Coordinate-system and job metadata from the JXL ``Environment``.

    Attributes:
        crs_identifier: Coordinate reference system identifier (for
            example ``"EPSG:3844"``), recognized from the environment
            metadata when possible; ``None`` when no recognizable
            identifier was found.
        raw_values: JSON-compatible mapping of every leaf element found
            under ``Environment``, keyed by its local tag name. Read-only.
    """

    crs_identifier: Optional[str] = None
    raw_values: Mapping[str, Any] = attrs.field(
        factory=dict, converter=_freeze_mapping
    )


@attrs.define(frozen=True, kw_only=True)
class JxlParseResult:
    """Outcome of parsing one JXL document.

    Attributes:
        points: Every reduced point found, in document order, including
            ``KeyedIn`` points; callers filter those out as needed.
        environment: Coordinate-system/job metadata, when the document
            has an ``Environment`` section.
        issues: Diagnostics raised while parsing.
    """

    points: Sequence[JxlPoint] = attrs.field(
        factory=tuple, converter=_freeze_points
    )
    environment: Optional[JxlEnvironment] = None
    issues: Sequence[ParseIssue] = attrs.field(
        factory=tuple, converter=_freeze_issues
    )
