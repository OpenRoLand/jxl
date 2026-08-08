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
    "JxlEcefDeltas",
    "JxlEnvironment",
    "JxlGpsTime",
    "JxlGrid",
    "JxlParseResult",
    "JxlPoint",
    "JxlPointRecord",
    "JxlPrecision",
    "JxlQualityControl1",
    "JxlQualityControl2",
    "JxlWgs84",
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
    """Convert an iterable of points into an immutable tuple."""
    return tuple(value)


def _freeze_issues(value: Iterable[ParseIssue]) -> Tuple[ParseIssue, ...]:
    """Convert an iterable of parse issues into an immutable tuple."""
    return tuple(value)


@attrs.define(frozen=True, kw_only=True)
class JxlGrid:
    """Projected grid coordinates from a ``Grid`` or ``ComputedGrid`` element.

    Attributes:
        north: Raw ``North`` text value.
        east: Raw ``East`` text value.
        elevation: Raw ``Elevation`` text value.
    """

    north: Optional[str] = None
    east: Optional[str] = None
    elevation: Optional[str] = None


@attrs.define(frozen=True, kw_only=True)
class JxlWgs84:
    """WGS-84 geographic coordinates from a ``WGS84`` element.

    Attributes:
        latitude: Raw ``Latitude`` text value, in decimal degrees.
        longitude: Raw ``Longitude`` text value, in decimal degrees.
        height: Raw ``Height`` text value, ellipsoidal height in metres.
    """

    latitude: Optional[str] = None
    longitude: Optional[str] = None
    height: Optional[str] = None


@attrs.define(frozen=True, kw_only=True)
class JxlPrecision:
    """RTK/VRS precision estimates from a ``Precision`` element.

    Attributes:
        horizontal: Raw ``Horizontal`` text value, in metres.
        vertical: Raw ``Vertical`` text value, in metres.
    """

    horizontal: Optional[str] = None
    vertical: Optional[str] = None


@attrs.define(frozen=True, kw_only=True)
class JxlGpsTime:
    """GPS week and seconds-of-week from ``StartTime``/``EndTime`` elements.

    Attributes:
        gps_week: GPS week number.
        seconds: Seconds elapsed since the start of ``gps_week``, as raw
            text (Survey Pro may include fractional seconds).
    """

    gps_week: Optional[int] = None
    seconds: Optional[str] = None


@attrs.define(frozen=True, kw_only=True)
class JxlQualityControl1:
    """GPS quality-control block from a ``QualityControl1`` element.

    Attributes:
        number_of_satellites: Satellites used in the solution.
        relative_dops: Whether DOP values are relative.
        pdop: Position dilution of precision.
        hdop: Horizontal dilution of precision.
        vdop: Vertical dilution of precision.
        rms: RMS value reported by the receiver.
        number_of_positions_used: Positions averaged into the fix.
        horizontal_standard_deviation: Horizontal SD, when present.
        vertical_standard_deviation: Vertical SD, when present.
        start_time: GPS observation window start.
        end_time: GPS observation window end.
        monitor_status: Monitor status text, when present.
    """

    number_of_satellites: Optional[str] = None
    relative_dops: Optional[str] = None
    pdop: Optional[str] = None
    hdop: Optional[str] = None
    vdop: Optional[str] = None
    rms: Optional[str] = None
    number_of_positions_used: Optional[str] = None
    horizontal_standard_deviation: Optional[str] = None
    vertical_standard_deviation: Optional[str] = None
    start_time: Optional[JxlGpsTime] = None
    end_time: Optional[JxlGpsTime] = None
    monitor_status: Optional[str] = None


@attrs.define(frozen=True, kw_only=True)
class JxlQualityControl2:
    """Extended GPS quality-control block from ``QualityControl2``.

    Attributes:
        number_of_satellites: Satellites used in the solution.
        error_scale: Error scale factor.
        vcv_xx: Variance-covariance term XX.
        vcv_xy: Variance-covariance term XY.
        vcv_xz: Variance-covariance term XZ.
        vcv_yy: Variance-covariance term YY.
        vcv_yz: Variance-covariance term YZ.
        vcv_zz: Variance-covariance term ZZ.
    """

    number_of_satellites: Optional[str] = None
    error_scale: Optional[str] = None
    vcv_xx: Optional[str] = None
    vcv_xy: Optional[str] = None
    vcv_xz: Optional[str] = None
    vcv_yy: Optional[str] = None
    vcv_yz: Optional[str] = None
    vcv_zz: Optional[str] = None


@attrs.define(frozen=True, kw_only=True)
class JxlEcefDeltas:
    """Baseline deltas from an ``ECEFDeltas`` element.

    Attributes:
        delta_x: Raw ``DeltaX`` text value.
        delta_y: Raw ``DeltaY`` text value.
        delta_z: Raw ``DeltaZ`` text value.
    """

    delta_x: Optional[str] = None
    delta_y: Optional[str] = None
    delta_z: Optional[str] = None


@attrs.define(frozen=True, kw_only=True)
class JxlPointRecord:
    """One raw ``FieldBook/PointRecord`` entry.

    ``PointRecord`` entries carry field-book metadata that is merged into
    the corresponding ``Reductions/Point`` entry sharing the same point
    identity.

    Attributes:
        point_id: Stable point identifier from ``@ID`` or child ``ID``.
        timestamp: ``@TimeStamp`` attribute text, when present.
        name: Point name/number as recorded in the field book.
        code: Point code/feature code.
        description: Free-text description or comment.
        creation_method: Point creation ``Method`` (for example
            ``GpsStaticObservation``).
        survey_method: ``SurveyMethod`` token (for example ``Fix``).
        classification: Point ``Classification`` token.
        deleted: Whether the record is marked deleted in the field book.
        grid: Keyed-in or imported grid coordinates, when present.
        computed_grid: Computed grid coordinates from observed data.
        wgs84: WGS-84 coordinates, when present on the record.
        precision: RTK/VRS precision block, when present.
        quality_control_1: Primary GPS quality-control block.
        quality_control_2: Extended GPS quality-control block.
        ecef_deltas: RTK baseline deltas, when present.
        raw_values: Unrecognized leftover leaf values. Read-only.
    """

    point_id: Optional[str] = None
    timestamp: Optional[str] = None
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    creation_method: Optional[str] = None
    survey_method: Optional[str] = None
    classification: Optional[str] = None
    deleted: Optional[bool] = None
    grid: Optional[JxlGrid] = None
    computed_grid: Optional[JxlGrid] = None
    wgs84: Optional[JxlWgs84] = None
    precision: Optional[JxlPrecision] = None
    quality_control_1: Optional[JxlQualityControl1] = None
    quality_control_2: Optional[JxlQualityControl2] = None
    ecef_deltas: Optional[JxlEcefDeltas] = None
    raw_values: Mapping[str, Any] = attrs.field(
        factory=dict, converter=_freeze_mapping
    )

    @property
    def merge_key(self) -> Optional[str]:
        """Return the key used to merge this record with a reduced point."""
        return self.point_id or self.name


@attrs.define(frozen=True, kw_only=True)
class JxlPoint:
    """One raw ``Reductions/Point`` reduced point.

    Grid coordinates are kept as raw source text inside :class:`JxlGrid`
    so incomplete or non-numeric values can be reported as diagnostics.

    Attributes:
        point_id: Stable point identifier, when the source provides one.
        name: Point name/number.
        code: Point feature code.
        description: Free-text description or comment.
        method: ``SurveyMethod`` reported for this point (for example
            ``Fix`` or ``KeyedIn``).
        classification: Point ``Classification`` token.
        grid: Best grid coordinates from the ``Grid`` element.
        wgs84: WGS-84 coordinates from the ``WGS84`` element.
        record: Matching field-book metadata merged by point ID or name.
        raw_values: Unrecognized leftover leaf values. Read-only.
    """

    point_id: Optional[str] = None
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    method: Optional[str] = None
    classification: Optional[str] = None
    grid: Optional[JxlGrid] = None
    wgs84: Optional[JxlWgs84] = None
    record: Optional[JxlPointRecord] = None
    raw_values: Mapping[str, Any] = attrs.field(
        factory=dict, converter=_freeze_mapping
    )

    @property
    def north(self) -> Optional[str]:
        """Raw ``Grid/North`` text, when a grid is present."""
        if self.grid is None:
            return None
        return self.grid.north

    @property
    def east(self) -> Optional[str]:
        """Raw ``Grid/East`` text, when a grid is present."""
        if self.grid is None:
            return None
        return self.grid.east

    @property
    def elevation(self) -> Optional[str]:
        """Raw ``Grid/Elevation`` text, when a grid is present."""
        if self.grid is None:
            return None
        return self.grid.elevation

    @property
    def merge_key(self) -> Optional[str]:
        """Return the key used to merge this point with a field-book record."""
        return self.point_id or self.name

    @property
    def is_keyed_in(self) -> bool:
        """Return whether this point's survey method is ``KeyedIn``."""
        return (self.method or "").strip().casefold() == "keyedin"


@attrs.define(frozen=True, kw_only=True)
class JxlEnvironment:
    """Coordinate-system and job metadata from the JXL ``Environment``.

    Attributes:
        crs_identifier: Coordinate reference system identifier (for
            example ``"EPSG:3844"``), when recognizable.
        raw_values: Every other leaf element under ``Environment``.
    """

    crs_identifier: Optional[str] = None
    raw_values: Mapping[str, Any] = attrs.field(
        factory=dict, converter=_freeze_mapping
    )


@attrs.define(frozen=True, kw_only=True)
class JxlParseResult:
    """Outcome of parsing one JXL document.

    Attributes:
        points: Every reduced point found, in document order.
        environment: Coordinate-system/job metadata, when present.
        issues: Diagnostics raised while parsing.
    """

    points: Sequence[JxlPoint] = attrs.field(
        factory=tuple, converter=_freeze_points
    )
    environment: Optional[JxlEnvironment] = None
    issues: Sequence[ParseIssue] = attrs.field(
        factory=tuple, converter=_freeze_issues
    )
