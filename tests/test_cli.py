import pytest

from interface_automation.cli import main


@pytest.mark.parametrize("other", ["--events", "--failure-screenshot"])
def test_replay_rejects_overlapping_outputs(tmp_path, monkeypatch, other):
    target = str(tmp_path / "shared-output")
    monkeypatch.setattr(
        "sys.argv",
        [
            "interface-automation",
            "replay",
            "--member-id",
            "12345",
            "--updated-artifact",
            target,
            other,
            target,
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert not (tmp_path / "shared-output").exists()
