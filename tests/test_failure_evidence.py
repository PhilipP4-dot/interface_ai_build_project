from pathlib import Path

from test_replay import capability

from interface_automation.demo import serve
from interface_automation.replay import replay
from interface_automation.schema import Inputs


def test_failure_writes_masked_png(tmp_path: Path) -> None:
    target = tmp_path / "failure.png"
    events: list[dict[str, object]] = []
    with serve() as url:
        result = replay(
            capability(),
            Inputs(member_id="12345"),
            url,
            "permission_denied",
            events=events,
            failure_screenshot=target,
        )
    assert result.code == "permission_denied"
    assert target.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert any(event["event"] == "failure_screenshot" for event in events)


def test_capture_never_overwrites_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "failure.png"
    target.write_bytes(b"existing")
    events: list[dict[str, object]] = []
    with serve() as url:
        replay(
            capability(),
            Inputs(member_id="12345"),
            url,
            "permission_denied",
            events=events,
            failure_screenshot=target,
        )
    assert target.read_bytes() == b"existing"
    assert any(event["event"] == "failure_screenshot_unavailable" for event in events)
