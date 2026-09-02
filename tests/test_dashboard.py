from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"


class IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(attributes["id"])


def test_dashboard_files_and_primary_sections_exist() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert 'name="viewport"' in index
    assert "viewport-fit=cover" in index
    assert '<html lang="ja">' in index
    assert '<main>' in index
    assert '<script type="module" src="./app.js"></script>' in index
    for element_id in [
        "available-count",
        "total-rooms",
        "featured-rooms",
        "available-rooms",
        "type-summary",
        "availability-chart",
        "featured-timeline",
    ]:
        assert f'id="{element_id}"' in index

    parser = IdCollector()
    parser.feed(index)
    assert len(parser.ids) == len(set(parser.ids))
    assert (WEB / "styles.css").is_file()
    assert (WEB / "app.js").is_file()
    assert (WEB / "data-utils.js").is_file()
    assert (WEB / "favicon.svg").is_file()


def test_dashboard_css_is_mobile_first_and_safe_area_aware() -> None:
    styles = (WEB / "styles.css").read_text(encoding="utf-8")

    assert "min-width: 320px" in styles
    assert "overflow-x: hidden" in styles
    assert "env(safe-area-inset-top)" in styles
    assert "env(safe-area-inset-bottom)" in styles
    assert "min-height: 44px" in styles
    assert "@media (min-width: 620px)" in styles
    assert ".timeline-scroll" in styles
    assert "overflow-x: auto" in styles


def test_dashboard_uses_same_origin_data_and_periodic_cache_busting() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert 'latest: "./data/latest.json"' in app
    assert 'history: "./data/history.csv"' in app
    assert 'rooms: "./config/rooms.json"' in app
    assert 'cache: "no-store"' in app
    assert "Date.now()" in app
    assert "setInterval(pollLatest, 300000)" in app
    assert "raw.githubusercontent.com" not in app


def test_dashboard_data_utilities_cover_required_aggregations() -> None:
    utilities = (WEB / "data-utils.js").read_text(encoding="utf-8")

    for export_name in [
        "parseCsv",
        "parseHistory",
        "summarizeTypes",
        "tokyoDateKey",
        "todaysHistory",
        "roomTimeline",
    ]:
        assert f"export function {export_name}" in utilities
    assert 'const JST_TIME_ZONE = "Asia/Tokyo"' in utilities
    assert 'values[4].split("|")' in utilities


def test_current_public_data_matches_dashboard_contract() -> None:
    latest = json.loads((ROOT / "data" / "latest.json").read_text(encoding="utf-8"))
    rooms = json.loads((ROOT / "config" / "rooms.json").read_text(encoding="utf-8"))["rooms"]

    assert latest["total_rooms"] == len(rooms) == 50
    assert latest["available_count"] == len(latest["available_rooms"])
    assert {room["room"] for room in rooms}.issuperset({"611", "612", "615"})
    assert [room["room"] for room in latest["rooms"]] == sorted(
        (room["room"] for room in latest["rooms"]), key=int
    )


def test_pages_workflow_builds_same_origin_artifact_with_minimum_permissions() -> None:
    text = PAGES_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)

    triggers = workflow["on"]
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["push"]["paths"] == [
        "web/**",
        "data/**",
        "config/**",
        ".github/workflows/pages.yml",
    ]
    assert "workflow_dispatch" in triggers
    assert triggers["workflow_run"]["workflows"] == ["Collect room availability"]
    assert triggers["workflow_run"]["types"] == ["completed"]
    assert workflow["permissions"] == {}
    assert workflow["concurrency"] == {
        "group": "github-pages",
        "cancel-in-progress": "true",
    }

    build = workflow["jobs"]["build"]
    deploy = workflow["jobs"]["deploy"]
    assert build["permissions"] == {"contents": "read"}
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert build["if"] == "github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'"
    assert build["steps"][0]["uses"] == "actions/checkout@v6"
    assert build["steps"][1]["uses"] == "actions/configure-pages@v6"
    assert build["steps"][3]["uses"] == "actions/upload-pages-artifact@v5"
    assert build["steps"][3]["with"]["path"] == "_site"
    assert deploy["steps"][0]["uses"] == "actions/deploy-pages@v5"

    assemble = build["steps"][2]["run"]
    assert "cp -R web/. _site/" in assemble
    assert "cp data/latest.json data/history.csv _site/data/" in assemble
    assert "cp config/rooms.json _site/config/" in assemble
    assert "PAT" not in text
    assert "force" not in text.lower()
