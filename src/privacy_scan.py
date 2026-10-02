"""Fail when likely confidential strings or credentials appear in repository text."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".csv", ".yml", ".yaml", ".toml"}
SKIP_PARTS = {".git", ".venv", ".artifact_build", "__pycache__"}
PATTERNS = {
    "absolute Windows path": re.compile(r"[A-Za-z]:\\Users\\", re.I),
    "email address": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "private key": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY", re.I),
    "generic secret assignment": re.compile(r"(?:api[_-]?key|secret|password)\s*[=:]\s*['\"][^'\"]+", re.I),
}


def main() -> None:
    findings: list[str] = []
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if (not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES
                or any(part in SKIP_PARTS for part in relative.parts)
                or relative.parts[:2] == ("outputs", "qa")):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{path.relative_to(ROOT)}: {label}")
    if findings:
        raise SystemExit("Privacy scan failed:\n" + "\n".join(findings))
    print("Privacy scan passed.")


if __name__ == "__main__":
    main()
