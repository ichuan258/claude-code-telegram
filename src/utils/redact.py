"""Token redaction for logs.

Both stdlib `logging` (httpx, python-telegram-bot) and structlog (our own
loggers) get hooked so the bot token can never appear in disk logs even if
some library decides to log a full URL.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

MASK = "[REDACTED]"


def _token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


class TokenRedactFilter(logging.Filter):
    """Stdlib logging filter that masks the bot token in any record's message.

    The token is read once at filter construction time. Restart the bot if the
    token rotates.
    """

    def __init__(self) -> None:
        super().__init__()
        self._token = _token()

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._token:
            return True
        try:
            formatted = record.getMessage()
        except Exception:
            return True
        if self._token in formatted:
            record.msg = formatted.replace(self._token, MASK)
            record.args = ()
        return True


def structlog_redact_processor(
    logger: Any, method: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Structlog processor: walk event dict and replace token in any string value."""
    token = _token()
    if not token:
        return event_dict
    for key, value in list(event_dict.items()):
        if isinstance(value, str) and token in value:
            event_dict[key] = value.replace(token, MASK)
    return event_dict


def install_root_filter() -> None:
    """Attach the redact filter to every handler on the stdlib root logger.

    Filters on Logger objects don't apply to records from child loggers
    (httpx, telegram, etc.); attaching to the handler does.
    """
    flt = TokenRedactFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, TokenRedactFilter) for f in handler.filters):
            handler.addFilter(flt)
