from datetime import UTC, datetime, timedelta

import pytest

from forte_visual.cli import main
from forte_visual.gates import resource
from forte_visual.inputs import export
from forte_visual.io import read, write
from forte_visual.synthetic import create


def test_dry_run_never_enters_executor_or_resource_gate(tmp_path, monkeypatch, capsys):
    source = create(tmp_path / "release")
    export(source, tmp_path / "run")

    def forbidden(*a, **kw):
        raise AssertionError("Dry run must not infer")

    monkeypatch.setattr("forte_visual.cli.run_model", forbidden)
    assert (
        main(
            [
                "compare",
                "--release",
                str(source),
                "--inputs",
                str(tmp_path / "run/inference/inputs.json"),
                "--output",
                str(tmp_path / "dry"),
                "--dry-run",
            ]
        )
        == 0
    )
    assert read(tmp_path / "dry/preflight.json")["gates"]
    assert not (tmp_path / "dry/8b").exists()
    assert (
        main(
            [
                "train",
                "--release",
                str(source),
                "--inputs",
                str(tmp_path / "run/inference/inputs.json"),
                "--output",
                str(tmp_path / "train-dry"),
                "--dry-run",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "compare",
                "--release",
                str(source),
                "--inputs",
                str(tmp_path / "run/inference/inputs.json"),
                "--output",
                str(tmp_path / "blocked"),
            ]
        )
        == 2
    )
    assert "cashier" not in capsys.readouterr().out


def test_resource_receipt_requires_explicit_exclusive_owner_and_fresh_budget(tmp_path):
    now = datetime.now(UTC)
    receipt = {
        "owner": "visual-learning",
        "project": "forte26",
        "network_mode": "none",
        "project_resource_id": "synthetic-only",
        "live_state_sha256": "b" * 64,
        "cleanup_armed": True,
        "live_checked_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "remaining_project_usd": 20,
        "reserve_usd": 1,
        "total_project_ceiling_usd": 30,
        "hourly_total_usd": 1.35672,
        "reserved_usd": 1.0,
    }
    p = tmp_path / "resource.json"
    write(p, receipt)
    with resource(p):
        with pytest.raises(BlockingIOError), resource(p):
            pass
    for key, value in [
        ("owner", "steps-1-2"),
        ("network_mode", "bridge"),
        ("remaining_project_usd", 0),
        ("live_checked_at", (now - timedelta(hours=1)).isoformat()),
    ]:
        changed = {**receipt, key: value}
        p.write_text(__import__("json").dumps(changed))
        with pytest.raises(ValueError), resource(p):
            pass
    with pytest.raises(ValueError), resource(None):
        pass
