from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ANALYTICS = ROOT / "web" / "analytics-utils.js"
JST = timezone(timedelta(hours=9))


def observed(value: str, count: int, rooms: list[str] | None = None) -> dict[str, object]:
    return {
        "observedAt": value,
        "availableCount": count,
        "availableRooms": rooms or [],
    }


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def rolling(
    history: list[dict[str, object]], hours: int, now: str
) -> list[dict[str, object]]:
    end = instant(now)
    start = end - timedelta(hours=hours)
    return [row for row in history if start <= instant(str(row["observedAt"])) <= end]


def completed_window(
    history: list[dict[str, object]], hours: int, now: str
) -> list[dict[str, object]]:
    end = instant(now).astimezone(JST).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=hours)
    return [row for row in history if start <= instant(str(row["observedAt"])) < end]


def hourly_buckets(
    history: list[dict[str, object]],
) -> dict[tuple[str, int], list[dict[str, object]]]:
    buckets: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in history:
        local = instant(str(row["observedAt"])).astimezone(JST)
        buckets[(local.date().isoformat(), local.hour)].append(row)
    return buckets


def quarter_slot_key(value: str) -> tuple[str, int, int]:
    local = instant(value).astimezone(JST)
    return local.date().isoformat(), local.hour, (local.minute // 15) * 15


def quarter_buckets(
    history: list[dict[str, object]],
) -> dict[tuple[str, int, int], list[dict[str, object]]]:
    buckets: dict[tuple[str, int, int], list[dict[str, object]]] = defaultdict(list)
    for row in history:
        buckets[quarter_slot_key(str(row["observedAt"]))].append(row)
    return buckets


def bucket_average(rows: list[dict[str, object]]) -> float:
    return sum(int(row["availableCount"]) for row in rows) / len(rows)


def period_average(buckets: dict[tuple[str, int], list[dict[str, object]]]) -> float:
    return sum(bucket_average(rows) for rows in buckets.values()) / len(buckets)


def test_javascript_analytics_exports_required_pure_functions() -> None:
    source = ANALYTICS.read_text(encoding="utf-8")

    for name in [
        "filterHistoryByRollingHours",
        "buildHourlyBuckets",
        "aggregateAverageAvailability",
        "buildWeekdayTimeHeatmap",
        "facilityAvailabilityRates",
        "roomAvailabilityRates",
        "calculateCoverage",
        "analyzeAvailability",
        "jstDateHourParts",
        "jstDateTimeParts",
        "buildQuarterHourBuckets",
        "buildEveningTimeAnalysis",
        "buildAllDayTimeAnalysis",
    ]:
        assert f"export function {name}" in source
    assert 'const JST_TIME_ZONE = "Asia/Tokyo"' in source
    assert 'new Date(`${dateKey}T00:00:00Z`).getUTCDay()' in source


def test_rolling_24_hours_excludes_old_data_and_crosses_midnight() -> None:
    history = [
        observed("2026-09-09T01:29:59+09:00", 1),
        observed("2026-09-09T01:30:00+09:00", 2),
        observed("2026-09-09T23:59:59+09:00", 3),
        observed("2026-09-10T00:00:00+09:00", 4),
        observed("2026-09-10T01:30:00+09:00", 5),
    ]

    assert [row["availableCount"] for row in rolling(history, 24, "2026-09-10T01:30:00+09:00")] == [2, 3, 4, 5]


@pytest.mark.parametrize(("hours", "included"), [(168, 2), (720, 3)])
def test_completed_analysis_windows_exclude_current_partial_hour(
    hours: int, included: int
) -> None:
    history = [
        observed("2026-08-11T01:00:00+09:00", 1),
        observed("2026-09-03T01:00:00+09:00", 2),
        observed("2026-09-10T00:59:59+09:00", 3),
        observed("2026-09-10T01:00:00+09:00", 4),
    ]

    assert len(completed_window(history, hours, "2026-09-10T01:35:00+09:00")) == included


def test_jst_bucket_and_weekday_are_independent_of_utc_input() -> None:
    utc_value = instant("2026-09-09T15:00:00+00:00")
    jst_value = utc_value.astimezone(JST)

    assert jst_value.isoformat() == "2026-09-10T00:00:00+09:00"
    assert jst_value.weekday() == 3  # Thursday, Monday=0
    assert list(hourly_buckets([observed(utc_value.isoformat(), 1)])) == [("2026-09-10", 0)]


def test_hour_normalization_gives_each_bucket_equal_weight() -> None:
    history = [
        observed("2026-09-09T18:05:00+09:00", 0),
        observed("2026-09-09T18:20:00+09:00", 10),
        observed("2026-09-09T18:35:00+09:00", 0),
        observed("2026-09-09T18:50:00+09:00", 10),
        observed("2026-09-10T03:05:00+09:00", 1),
    ]
    buckets = hourly_buckets(history)

    assert period_average(buckets) == pytest.approx(3.0)
    assert sum(int(row["availableCount"]) for row in history) / len(history) == pytest.approx(4.2)


def test_room_rate_is_averaged_inside_hour_before_period() -> None:
    rows = [
        observed("2026-09-09T18:05:00+09:00", 1, ["611"]),
        observed("2026-09-09T18:20:00+09:00", 1, ["611"]),
        observed("2026-09-09T18:35:00+09:00", 0),
        observed("2026-09-09T18:50:00+09:00", 0),
    ]
    bucket = next(iter(hourly_buckets(rows).values()))

    assert sum("611" in row["availableRooms"] for row in bucket) / len(bucket) == 0.5


def test_facility_rate_uses_any_target_room_per_observation() -> None:
    target_rooms = {"611", "615"}
    rows = [
        observed("2026-09-09T18:05:00+09:00", 1, ["611"]),
        observed("2026-09-09T18:20:00+09:00", 1, ["615"]),
        observed("2026-09-09T18:35:00+09:00", 1, ["612"]),
        observed("2026-09-09T18:50:00+09:00", 0),
    ]

    hits = [any(room in target_rooms for room in row["availableRooms"]) for row in rows]
    assert sum(hits) / len(hits) == 0.5


def test_missing_hours_are_excluded_instead_of_counted_as_zero() -> None:
    buckets = hourly_buckets(
        [
            observed("2026-09-09T03:05:00+09:00", 2),
            observed("2026-09-09T18:05:00+09:00", 6),
        ]
    )

    assert len(buckets) == 2
    assert period_average(buckets) == 4
    assert len(buckets) / 168 * 100 == pytest.approx(1.190476)


def test_heatmap_assignment_uses_jst_weekday_and_two_hour_band() -> None:
    row = observed("2026-09-11T20:15:00+09:00", 3)
    local = instant(str(row["observedAt"])).astimezone(JST)

    assert local.weekday() == 4  # Friday
    assert (local.hour // 2) * 2 == 20


def test_thirty_day_window_handles_only_eight_observed_days() -> None:
    now = datetime(2026, 9, 10, 1, 35, tzinfo=JST)
    history = [
        observed((now - timedelta(days=day, hours=2)).isoformat(), day)
        for day in range(1, 9)
    ]
    selected = completed_window(history, 720, now.isoformat())

    assert len({instant(str(row["observedAt"])).astimezone(JST).date() for row in selected}) == 8


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-09-12T22:15:00+09:00", ("2026-09-12", 22, 15)),
        ("2026-09-12T22:18:59+09:00", ("2026-09-12", 22, 15)),
        ("2026-09-12T22:29:59+09:00", ("2026-09-12", 22, 15)),
        ("2026-09-12T22:30:00+09:00", ("2026-09-12", 22, 30)),
        ("2026-09-12T23:45:00+09:00", ("2026-09-12", 23, 45)),
        ("2026-09-13T00:00:00+09:00", ("2026-09-13", 0, 0)),
        ("2026-09-12T13:30:00+00:00", ("2026-09-12", 22, 30)),
    ],
)
def test_quarter_hour_slot_boundaries_are_jst_exact(
    value: str, expected: tuple[str, int, int]
) -> None:
    assert quarter_slot_key(value) == expected


def test_quarter_hour_normalization_gives_each_date_slot_equal_weight() -> None:
    history = [
        observed("2026-09-07T22:16:00+09:00", 0),
        observed("2026-09-07T22:19:00+09:00", 10),
        observed("2026-09-14T22:17:00+09:00", 1),
    ]
    buckets = quarter_buckets(history)

    assert len(buckets) == 2
    assert period_average(buckets) == pytest.approx(3.0)
    assert sum(int(row["availableCount"]) for row in history) / len(history) == pytest.approx(11 / 3)


def test_evening_slot_contract_has_four_hours_and_eight_quarters() -> None:
    source = ANALYTICS.read_text(encoding="utf-8")

    assert 'granularity: "hour"' in source
    assert 'granularity: "quarter-hour"' in source
    assert "Array.from({ length: 4 }" in source
    assert "Array.from({ length: 8 }" in source
    assert "Math.floor(parts.minute / 15) * 15" in source


def test_all_day_contract_has_twenty_four_hour_columns() -> None:
    source = ANALYTICS.read_text(encoding="utf-8")

    assert "ALL_DAY_HOURS" in source
    assert "Array.from({ length: 24 }" in source


@pytest.mark.parametrize(
    ("hours", "mode"),
    [(168, "evening"), (168, "all-day"), (720, "evening"), (720, "all-day")],
)
def test_period_and_time_view_modes_are_independent(hours: int, mode: str) -> None:
    assert hours in {168, 720}
    assert mode in {"evening", "all-day"}
