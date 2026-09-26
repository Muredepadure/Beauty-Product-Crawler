"""Logging setup shared by the CLIs: human-readable text or one JSON object per line.

JSON lines carry the standard fields (`ts`, `level`, `logger`, `message`) plus anything
passed via ``extra=``, so a scheduler/log shipper can filter on e.g. ``retailer``:

    log.info("crawl finished", extra={"event": "crawl_finished", "retailer": "notino"})
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Literal, TextIO

LogFormat = Literal["text", "json"]
_HANDLER_NAME = "beautycrawler"

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
}


class _StderrHandler(logging.StreamHandler[TextIO]):
    """Writes to whatever `sys.stderr` is at emit time (it may be swapped after setup,
    e.g. by test capture), not the stream that existed when the handler was made."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        super().emit(record)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(verbose: bool = False, fmt: LogFormat = "text") -> None:
    """Configure the root logger. Safe to re-call: replaces only the handler it added
    before (other handlers, e.g. pytest's, are left alone)."""
    handler = _StderrHandler()
    handler.set_name(_HANDLER_NAME)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    for old in [h for h in root.handlers if h.get_name() == _HANDLER_NAME]:
        root.removeHandler(old)
    root.addHandler(handler)
    root.setLevel(logging.INFO if verbose else logging.WARNING)
