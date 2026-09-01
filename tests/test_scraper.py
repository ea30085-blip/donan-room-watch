from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scraper import ParseError, ValidationError, parse_availability  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
OBSERVED_AT = datetime(2026, 9, 2, 2, 30, tzinfo=ZoneInfo("Asia/Tokyo"))


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_available_rooms_deduplicates_and_sorts() -> None:
    result = parse_availability(fixture("available.html"), OBSERVED_AT)

    assert result == {
        "observed_at": "2026-09-02T02:30:00+09:00",
        "available_count": 2,
        "preparing_count": 1,
        "rooms": [
            {"room": "213", "type": "D"},
            {"room": "516", "type": "E"},
        ],
    }


def test_parse_zero_rooms_as_normal_state_without_room_list() -> None:
    result = parse_availability(fixture("zero.html"), OBSERVED_AT)

    assert result["available_count"] == 0
    assert result["preparing_count"] == 2
    assert result["rooms"] == []


def test_duplicate_room_links_produce_one_room() -> None:
    result = parse_availability(fixture("duplicate.html"), OBSERVED_AT)

    assert result["rooms"] == [{"room": "501", "type": "F"}]


def test_malformed_structure_is_not_treated_as_zero_rooms() -> None:
    with pytest.raises(ParseError, match="空室サマリー"):
        parse_availability(fixture("malformed.html"), OBSERVED_AT)


def test_count_mismatch_is_rejected() -> None:
    html = fixture("available.html").replace("2室", "3室", 1)

    with pytest.raises(ValidationError, match="空室総数"):
        parse_availability(html, OBSERVED_AT)


def test_missing_type_heading_is_rejected() -> None:
    html = fixture("duplicate.html").replace("<h3>Type F</h3>", "<h3>客室</h3>")

    with pytest.raises(ParseError, match="Type見出し"):
        parse_availability(html, OBSERVED_AT)


def test_invalid_room_number_is_rejected() -> None:
    html = fixture("duplicate.html").replace("501", "50A")

    with pytest.raises(ValidationError, match="3桁"):
        parse_availability(html, OBSERVED_AT)


def test_naive_observation_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_availability(fixture("zero.html"), datetime(2026, 9, 2, 2, 30))
