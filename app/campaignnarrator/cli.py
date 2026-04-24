"""Command-line entrypoint for Campaign Narrator."""

from __future__ import annotations

import argparse
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from campaignnarrator.adapters.embedding_adapter import (
    EmbeddingAdapter,
    OllamaEmbeddingAdapter,
    StubEmbeddingAdapter,
)
from campaignnarrator.application_factory import ApplicationFactory, ApplicationGraph
from campaignnarrator.logging_config import configure_logging
from campaignnarrator.settings import Settings


def _build_embedding_adapter(settings: Settings) -> EmbeddingAdapter:
    """Construct the correct EmbeddingAdapter from settings."""
    if settings.embedding_provider == "stub":
        return StubEmbeddingAdapter()
    return OllamaEmbeddingAdapter(
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
    )


def _build_application_graph(
    data_root: Path, stdin: TextIO, stdout: TextIO
) -> ApplicationGraph:
    """Build the production application graph. Delegates to ApplicationFactory."""
    return ApplicationFactory(data_root, stdin, stdout).build()


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Parse CLI arguments and run the appropriate orchestrator."""

    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout

    parser = argparse.ArgumentParser(prog="campaignnarrator")
    parser.add_argument("--data-root", type=Path, default=None)
    args = parser.parse_args(argv)

    settings = Settings()
    if args.data_root is not None:
        data_root = args.data_root
    else:
        data_root = Path(settings.data_root)
    configure_logging(
        data_root=data_root,
        console_logging=settings.console_logging,
        log_level=settings.log_level,
    )
    graph = _build_application_graph(data_root, stdin=stdin, stdout=stdout)

    def _sigterm_handler(signum: int, frame: object) -> None:
        graph.game_orchestrator.save_state()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm_handler)

    try:
        graph.game_orchestrator.run()
    except KeyboardInterrupt:
        graph.game_orchestrator.save_state()

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
