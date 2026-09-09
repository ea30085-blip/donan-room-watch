from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from storage import ALLOWED_FACILITIES, StorageError, load_room_master, validate_room_master  # noqa: E402


EXPECTED_ROOMS = {
    "sauna": {"611", "615"},
    "karaoke": {"216", "316", "416", "516", "611", "612", "613", "615"},
    "bath_tv": {
        "201", "202", "203", "205", "301", "302", "303", "305",
        "401", "402", "403", "405", "501", "502", "503", "505",
        "611", "612", "615",
    },
    "massage_chair": {"611", "612", "615"},
    "collagen_machine": {"611", "612", "615"},
    "rainbow_blower_bath": {
        "101", "102", "201", "202", "203", "205", "301", "302", "303",
        "305", "401", "402", "403", "405", "501", "502", "503", "505",
    },
    "blower_bath": {
        "211", "212", "213", "215", "216", "217", "218", "311", "312",
        "313", "315", "316", "317", "318", "411", "412", "413", "415",
        "416", "417", "418", "511", "512", "513", "515", "516", "517",
        "518", "611", "612", "613", "615",
    },
}


def official_master() -> list[dict[str, object]]:
    return load_room_master(ROOT / "config" / "rooms.json")


def test_official_master_has_valid_facility_arrays_and_expected_keys() -> None:
    master = official_master()

    assert len(master) == 50
    for room in master:
        facilities = room["facilities"]
        assert isinstance(facilities, list)
        assert len(facilities) == len(set(facilities))
        assert set(facilities) <= ALLOWED_FACILITIES


@pytest.mark.parametrize(("facility", "expected"), EXPECTED_ROOMS.items())
def test_official_facility_room_mapping(
    facility: str, expected: set[str]
) -> None:
    actual = {
        room["room"] for room in official_master() if facility in room["facilities"]
    }

    assert actual == expected


@pytest.mark.parametrize(
    ("facilities", "message"),
    [
        ("sauna", "配列"),
        (["unknown_facility"], "未知"),
        (["sauna", "sauna"], "重複"),
    ],
)
def test_invalid_facilities_are_rejected(
    facilities: object, message: str
) -> None:
    with pytest.raises(StorageError, match=message):
        validate_room_master(
            [{"room": "101", "type": "A", "facilities": facilities}]
        )


def test_empty_facility_array_is_supported() -> None:
    assert validate_room_master(
        [{"room": "101", "type": "A", "facilities": []}]
    )[0]["facilities"] == []


def test_available_room_facility_filter_expectations() -> None:
    master = official_master()
    available = {"515", "611", "612"}

    def filtered(facility: str) -> list[str]:
        return [
            room["room"]
            for room in master
            if room["room"] in available and facility in room["facilities"]
        ]

    assert filtered("sauna") == ["611"]
    assert filtered("karaoke") == ["611", "612"]
    assert filtered("rainbow_blower_bath") == []
