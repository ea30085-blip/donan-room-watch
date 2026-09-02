from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "collect.yml"


def load_workflow() -> tuple[str, dict[str, object]]:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    return text, workflow


def test_collect_workflow_triggers_and_jst_schedules() -> None:
    _, workflow = load_workflow()
    triggers = workflow["on"]
    assert isinstance(triggers, dict)
    assert "workflow_dispatch" in triggers

    schedules = triggers["schedule"]
    assert isinstance(schedules, list)
    assert schedules == [
        {"cron": "7,37 10-17 * * *", "timezone": "Asia/Tokyo"},
        {"cron": "7,22,37,52 18-23 * * *", "timezone": "Asia/Tokyo"},
        {"cron": "7,22,37,52 0-1 * * *", "timezone": "Asia/Tokyo"},
        {"cron": "7 2-9 * * *", "timezone": "Asia/Tokyo"},
    ]


def test_collect_workflow_uses_minimum_permissions_and_serial_queue() -> None:
    _, workflow = load_workflow()

    assert workflow["permissions"] == {"contents": "write"}
    assert workflow["concurrency"] == {
        "group": "donan-room-watch-collect-main",
        "cancel-in-progress": "false",
        "queue": "max",
    }


def test_collect_job_order_runtime_and_python_version() -> None:
    _, workflow = load_workflow()
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    collect = jobs["collect"]
    assert isinstance(collect, dict)
    assert collect["runs-on"] == "ubuntu-latest"
    assert collect["timeout-minutes"] == "10"

    steps = collect["steps"]
    assert isinstance(steps, list)
    names = [step["name"] for step in steps]
    assert names == [
        "Check out main",
        "Set up Python",
        "Install dependencies",
        "Run tests",
        "Collect availability",
        "Check data changes",
        "Commit and push data",
    ]
    assert steps[0]["uses"] == "actions/checkout@v6"
    assert steps[0]["with"] == {"ref": "main", "fetch-depth": "0"}
    assert steps[1]["uses"] == "actions/setup-python@v6"
    assert steps[1]["with"]["python-version"] == "3.13"
    assert "python -m pip install -r requirements.txt" in steps[2]["run"]
    assert steps[3]["run"] == "python -m pytest -q"
    assert steps[4]["run"] == "python src/scraper.py"


def test_commit_is_conditional_and_push_is_non_forced_with_rebase() -> None:
    text, workflow = load_workflow()
    collect = workflow["jobs"]["collect"]
    steps = collect["steps"]
    change_step = steps[5]
    commit_step = steps[6]

    assert "git diff --quiet -- data/latest.json data/history.csv" in change_step["run"]
    assert commit_step["if"] == "steps.data_changes.outputs.changed == 'true'"
    commands = commit_step["run"]
    assert 'git config user.name "github-actions[bot]"' in commands
    assert "git add -- data/latest.json data/history.csv" in commands
    assert 'git commit -m "chore(data): collect room availability"' in commands
    assert commands.index("git pull --rebase origin main") < commands.index(
        "git push origin HEAD:main"
    )
    assert "--force" not in text
    assert "git push -f" not in text
