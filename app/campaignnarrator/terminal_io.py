"""Terminal-backed PlayerIO implementation."""

from __future__ import annotations

from typing import TextIO


class TerminalIO:
    """PlayerIO implementation backed by stdin/stdout."""

    def __init__(self, stdin: TextIO, stdout: TextIO) -> None:
        self._stdin = stdin
        self._stdout = stdout

    def prompt(self, text: str) -> str:
        self._stdout.write(text)
        self._stdout.flush()
        while True:
            raw = self._stdin.readline()
            if not raw:  # EOF — treat as "exit" to exit cleanly
                return "exit"
            line = raw.rstrip("\r\n")
            if line.strip():
                return line

    def prompt_optional(self, text: str) -> str:
        self._stdout.write(text)
        self._stdout.flush()
        return self._stdin.readline().rstrip("\r\n")

    def prompt_multiline(self, text: str) -> str:
        self._stdout.write(text)
        self._stdout.flush()
        lines: list[str] = []
        while True:
            raw = self._stdin.readline()
            if not raw:  # EOF
                break
            line = raw.rstrip("\r\n")
            if not line and lines:  # blank line after content = done
                break
            lines.append(line)
        return "\n".join(lines)

    def display(self, text: str) -> None:
        self._stdout.write(text + "\n")
        self._stdout.flush()
