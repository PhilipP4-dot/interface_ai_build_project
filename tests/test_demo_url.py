import pytest

from interface_automation.demo import serve, validate_demo_url


def test_accepts_running_demo_and_localhost_alias():
    with serve() as url:
        assert validate_demo_url(url + "/") == url
        assert validate_demo_url(url.replace("127.0.0.1", "localhost")) == url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://127.0.0.1:8765/private",
        "http://user:secret@127.0.0.1:8765",
        "http://127.0.0.1:8765?key=secret",
        "http://127.0.0.1",
        "file:///tmp/demo.html",
    ],
)
def test_rejects_unsupported_targets(url):
    with pytest.raises(ValueError):
        validate_demo_url(url)
