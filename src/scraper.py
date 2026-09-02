"""Fetch and parse the current room availability for DONAN Room Watch."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag

TARGET_URL = "https://www.hotenavi.com/donan-m/empty"
JST = ZoneInfo("Asia/Tokyo")
USER_AGENT = "DONAN-Room-Watch/Phase2 (+personal technical verification)"
COUNT_PATTERN = re.compile(r"^\s*(\d+)\s*室\s*$")
ROOM_PATTERN = re.compile(r"^\d{3}$")
TYPE_PATTERN = re.compile(r"^Type\s+(.+?)\s*$", re.IGNORECASE)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOM_MASTER_PATH = PROJECT_ROOT / "config" / "rooms.json"
LATEST_PATH = PROJECT_ROOT / "data" / "latest.json"
HISTORY_PATH = PROJECT_ROOT / "data" / "history.csv"


class ScraperError(Exception):
    """Base class for expected scraper failures."""


class FetchError(ScraperError):
    """Raised when the target page cannot be fetched safely."""


class ParseError(ScraperError):
    """Raised when required page structure cannot be parsed."""


class ValidationError(ScraperError):
    """Raised when parsed values are internally inconsistent."""


def _parse_count(container: Tag, selector: str, label: str) -> int:
    element = container.select_one(selector)
    if element is None:
        raise ParseError(f"{label}の要素が見つかりません: {selector}")

    text = element.get_text(" ", strip=True)
    match = COUNT_PATTERN.fullmatch(text)
    if match is None:
        raise ParseError(f"{label}を解析できません: {text!r}")
    return int(match.group(1))


def _find_availability_section(soup: BeautifulSoup) -> Tag:
    for heading in soup.find_all("h2"):
        if "空室一覧" in heading.get_text(" ", strip=True):
            section = heading.find_parent("section")
            if section is None:
                raise ParseError("空室一覧の親sectionが見つかりません")
            return section
    raise ParseError("空室一覧が見つかりません")


def _parse_rooms(soup: BeautifulSoup, available_count: int) -> list[dict[str, str]]:
    if available_count == 0:
        # The live template omits the room-list section when no room is available.
        # If it is present, continue parsing so contradictory room data is detected.
        try:
            section = _find_availability_section(soup)
        except ParseError:
            return []
    else:
        section = _find_availability_section(soup)

    rooms_by_number: dict[str, str] = {}
    type_headings = [
        heading
        for heading in section.find_all("h3")
        if TYPE_PATTERN.fullmatch(heading.get_text(" ", strip=True))
    ]
    if available_count > 0 and not type_headings:
        raise ParseError("空室のType見出しが見つかりません")

    for heading in type_headings:
        heading_text = heading.get_text(" ", strip=True)
        type_match = TYPE_PATTERN.fullmatch(heading_text)
        if type_match is None:
            continue
        room_type = type_match.group(1).strip()
        if not room_type:
            raise ParseError(f"Typeを解析できません: {heading_text!r}")

        sibling = heading.find_next_sibling()
        found_for_type = False
        while sibling is not None and sibling.name != "h3":
            if isinstance(sibling, Tag):
                for anchor in sibling.select("a[href]"):
                    room = anchor.get_text(strip=True)
                    if not room:
                        continue
                    href = anchor.get("href", "")
                    if "RoomDetail=" not in href and "/room/detail/" not in href:
                        continue
                    if not ROOM_PATTERN.fullmatch(room):
                        raise ValidationError(
                            f"部屋番号が3桁の数字ではありません: {room!r}"
                        )
                    found_for_type = True
                    previous_type = rooms_by_number.get(room)
                    if previous_type is not None and previous_type != room_type:
                        raise ValidationError(
                            f"部屋番号 {room} が複数のTypeに属しています: "
                            f"{previous_type!r}, {room_type!r}"
                        )
                    rooms_by_number[room] = room_type
            sibling = sibling.find_next_sibling()

        if not found_for_type:
            raise ParseError(f"{heading_text!r} に対応する部屋番号が見つかりません")

    rooms = [
        {"room": room, "type": rooms_by_number[room]}
        for room in sorted(rooms_by_number, key=int)
    ]
    return rooms


def _validate_result(result: dict[str, Any]) -> None:
    rooms = result["rooms"]
    room_numbers = [room["room"] for room in rooms]

    if len(rooms) != result["available_count"]:
        raise ValidationError(
            "空室総数と一意な部屋番号の件数が一致しません: "
            f"available_count={result['available_count']}, rooms={len(rooms)}"
        )
    if len(room_numbers) != len(set(room_numbers)):
        raise ValidationError("出力する部屋番号に重複があります")

    for room in rooms:
        if not ROOM_PATTERN.fullmatch(room["room"]):
            raise ValidationError(
                f"部屋番号が3桁の数字ではありません: {room['room']!r}"
            )
        if not isinstance(room["type"], str) or not room["type"].strip():
            raise ValidationError(f"部屋 {room['room']} のTypeを取得できません")


def parse_availability(
    html: str, observed_at: datetime | None = None
) -> dict[str, Any]:
    """Parse one availability page and return a validated serializable result."""
    soup = BeautifulSoup(html, "html.parser")
    summary = soup.select_one(".epEmptyCleanRoom")
    if summary is None:
        raise ParseError("空室サマリー (.epEmptyCleanRoom) が見つかりません")

    available_count = _parse_count(
        summary, ".epEmptyRoom .epEmptyRoomTxt", "空室総数"
    )
    preparing_count = _parse_count(
        summary, ".epCleanRoom .epCleanRoomTxt", "準備中室数"
    )
    rooms = _parse_rooms(soup, available_count)

    timestamp = observed_at or datetime.now(JST)
    if timestamp.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    timestamp = timestamp.astimezone(JST).replace(microsecond=0)

    result: dict[str, Any] = {
        "observed_at": timestamp.isoformat(),
        "available_count": available_count,
        "preparing_count": preparing_count,
        "rooms": rooms,
    }
    _validate_result(result)
    return result


def fetch_html(url: str = TARGET_URL) -> str:
    """Fetch the page using exactly one HTTP request (redirects are not followed)."""
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=(5, 20),
            allow_redirects=False,
        )
    except requests.Timeout as exc:
        raise FetchError(f"対象ページの取得がタイムアウトしました: {url}") from exc
    except requests.RequestException as exc:
        raise FetchError(f"対象ページへのHTTP接続に失敗しました: {url}: {exc}") from exc

    if response.status_code != requests.codes.ok:
        raise FetchError(
            f"対象ページがHTTP {response.status_code}を返しました: {url}"
        )
    content_type = response.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type:
        raise FetchError(
            f"対象ページがHTMLではありません: Content-Type={content_type!r}"
        )
    return response.text


def scrape(url: str = TARGET_URL) -> dict[str, Any]:
    """Fetch once, timestamp the observation in JST, then parse and validate."""
    html = fetch_html(url)
    return parse_availability(html, observed_at=datetime.now(JST))


def main() -> int:
    from storage import StorageError, save_observation

    try:
        result = scrape()
        latest, history_appended = save_observation(
            result,
            master_path=ROOM_MASTER_PATH,
            latest_path=LATEST_PATH,
            history_path=HISTORY_PATH,
        )
    except (ScraperError, StorageError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output = {
        **result,
        "available_rooms": latest["available_rooms"],
        "history_appended": history_appended,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
