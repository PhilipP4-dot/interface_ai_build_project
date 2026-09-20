"""Load only the API key from the owner's local file; never execute dotenv content."""

import os
from pathlib import Path


def api_key(path: Path, variable: str = "OPENAI_API_KEY") -> str:
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.strip().removeprefix("export ").partition("=")
            if separator and name.strip() == variable:
                value = value.strip()
                if value.startswith(('"', "'")):
                    quote = value[0]
                    end = value.find(quote, 1)
                    tail = value[end + 1 :].strip()
                    if end < 0 or (tail and not tail.startswith("#")):
                        raise ValueError("Invalid local key format")
                    value = value[1:end]
                else:
                    value = value.split(" #", 1)[0].strip()
                if not value or any(character.isspace() for character in value):
                    raise ValueError("Invalid local key format")
                return value
    value = os.environ.get(variable, "")
    if not value:
        raise ValueError(f"{variable} is not configured")
    return value
