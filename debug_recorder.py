from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

import cv2


def _safe_label(value: str) -> str:
    return re.sub(r"[^\w.-]+", "_", value)[:48]


class DebugFrameRecorder:
    """Grava frames do debug overlay em debug_frames/<sessao>/."""

    def __init__(
        self,
        base_dir: Path,
        *,
        fps: float = 5.0,
        max_frames: int = 5000,
        save_on_action_change: bool = True,
        only_minigame: bool = True,
    ) -> None:
        self.base_dir = base_dir
        self.min_interval = 1.0 / max(float(fps), 0.25)
        self.max_frames = max(1, int(max_frames))
        self.save_on_action_change = save_on_action_change
        self.only_minigame = only_minigame
        self.session_dir: Path | None = None
        self.saved_count = 0
        self.last_save_at = 0.0
        self.last_action: str | None = None

    @property
    def active(self) -> bool:
        return self.session_dir is not None

    def start_session(self) -> Path:
        if self.session_dir is not None:
            return self.session_dir
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.base_dir / stamp
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.saved_count = 0
        self.last_save_at = 0.0
        self.last_action = None
        return self.session_dir

    def end_session(self) -> tuple[Path | None, int]:
        session = self.session_dir
        count = self.saved_count
        self.session_dir = None
        self.saved_count = 0
        self.last_save_at = 0.0
        self.last_action = None
        return session, count

    def should_record(self, bot_enabled: bool, minigame_active: bool) -> bool:
        if not bot_enabled:
            return False
        if self.only_minigame and not minigame_active:
            return False
        return True

    def maybe_save(
        self,
        overlay,
        *,
        action: str,
        error: float | None,
        hook_x: float | None,
        zone_x: float | None,
        active: bool,
    ) -> Path | None:
        if self.session_dir is None or self.saved_count >= self.max_frames:
            return None

        now = time.perf_counter()
        action_changed = (
            self.save_on_action_change
            and self.last_action is not None
            and action != self.last_action
        )
        interval_due = (now - self.last_save_at) >= self.min_interval
        if not action_changed and not interval_due:
            return None

        err_txt = "na" if error is None else f"{error:.0f}"
        hook_txt = "na" if hook_x is None else f"{hook_x:.0f}"
        zone_txt = "na" if zone_x is None else f"{zone_x:.0f}"
        status = "on" if active else "off"
        filename = (
            f"{self.saved_count:06d}_{_safe_label(action)}"
            f"_act{status}_e{err_txt}_a{hook_txt}_z{zone_txt}.png"
        )
        path = self.session_dir / filename
        cv2.imwrite(str(path), overlay)
        self.saved_count += 1
        self.last_save_at = now
        self.last_action = action
        return path
