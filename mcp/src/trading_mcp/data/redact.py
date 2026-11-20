"""Secret redaction for logs and error texts (DATA-14).

API keys travel in query strings for some vendors (FMP, Alpha Vantage). A
failed request puts the full URL into the exception text, and the text then
reaches a log line or a tool payload. :func:`redact` masks the value of every
key-like query parameter, and :func:`install_log_redaction` applies it to
every log record of the process.
"""

from __future__ import annotations

import logging
import re
import threading

_SECRET_PARAM = re.compile(
    r"(?i)\b(apikey|api_key|api-key|access_token|token|key|secret|password|crumb)=([^&\s\"'<>]+)"
)
_SECRET_HEADER = re.compile(r"(?i)\b(x-cg-demo-api-key|x-cg-pro-api-key|authorization)(['\"]?\s*[:=]\s*['\"]?)([^\s'\",}]+)")
_MASK = "***"

_install_lock = threading.Lock()
_installed = False


def redact(text: object) -> str:
    """Return ``text`` with secret query parameters and headers masked."""
    value = str(text)
    value = _SECRET_PARAM.sub(lambda m: f"{m.group(1)}={_MASK}", value)
    return _SECRET_HEADER.sub(lambda m: f"{m.group(1)}{m.group(2)}{_MASK}", value)


def _redact_arg(arg: object) -> object:
    if isinstance(arg, str):
        return redact(arg)
    if isinstance(arg, BaseException):
        return redact(f"{type(arg).__name__}: {arg}")
    return arg


def install_log_redaction() -> None:
    """Mask secrets in every log record created from now on (idempotent).

    The record factory runs before any handler, so the filter also covers
    handlers that are configured later (for example by ``logging.basicConfig``)
    and third-party loggers such as ``urllib3``.
    """
    global _installed  # pylint: disable=global-statement
    with _install_lock:
        if _installed:
            return
        previous = logging.getLogRecordFactory()

        def factory(*args: object, **kwargs: object) -> logging.LogRecord:
            record = previous(*args, **kwargs)
            try:
                if isinstance(record.msg, str):
                    record.msg = redact(record.msg)
                if isinstance(record.args, tuple):
                    record.args = tuple(_redact_arg(arg) for arg in record.args)
                elif isinstance(record.args, dict):
                    record.args = {key: _redact_arg(val) for key, val in record.args.items()}
                if record.exc_info and record.exc_info[1] is not None and not record.exc_text:
                    record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            return record

        logging.setLogRecordFactory(factory)
        _installed = True
