from __future__ import annotations

from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).with_name("fishing_bot.log.txt")

_log_file = None


def init_bot_log() -> Path:
    global _log_file
    if _log_file is None:
        _log_file = LOG_PATH.open("a", encoding="utf-8")
        _log_file.write(f"\n=== sessao {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        _log_file.flush()
    return LOG_PATH


def bot_log(message: str) -> None:
    line = message.rstrip("\n")
    print(line, flush=True)
    if _log_file is None:
        init_bot_log()
    assert _log_file is not None
    _log_file.write(line + "\n")
    _log_file.flush()


def close_bot_log() -> None:
    global _log_file
    if _log_file is not None:
        _log_file.flush()
        _log_file.close()
        _log_file = None
