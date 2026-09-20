"""Configuration can narrow the demo surface's fixed read-only safety boundary."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field

from .schema import Contract

ActionName = Literal["fill_member", "search", "open_accounts", "read_balance"]


def default_actions() -> list[ActionName]:
    return ["fill_member", "search", "open_accounts", "read_balance"]


class Policy(Contract):
    allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1"])
    allowed_paths: list[str] = Field(default_factory=lambda: ["/"])
    allowed_actions: list[ActionName] = Field(default_factory=default_actions)

    def permits_url(self, url: str) -> bool:
        target = urlsplit(url)
        return target.hostname in self.allowed_hosts and (target.path or "/") in self.allowed_paths
