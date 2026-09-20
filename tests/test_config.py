from pathlib import Path

import pytest

from interface_automation.config import api_key


@pytest.mark.parametrize("value", ["test-value", '"test-value"', "'test-value' # comment"])
def test_local_key_preferred_without_shell_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "environment-value")
    path = tmp_path / ".env"
    path.write_text("OTHER=ignored\nOPENAI_API_KEY=" + value)
    assert api_key(path) == "test-value"


def test_missing_file_uses_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "environment-value")
    assert api_key(tmp_path / ".env") == "environment-value"


def test_invalid_file_does_not_fall_back(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text('OPENAI_API_KEY="unterminated')
    with pytest.raises(ValueError, match="Invalid local key format"):
        api_key(path)
