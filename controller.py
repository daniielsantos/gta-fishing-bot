from __future__ import annotations

import ctypes
import ctypes.wintypes

from detector import DetectionResult


INPUT_MOUSE = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("union", _INPUTUNION),
    ]


def _send_mouse_button(flags: int) -> None:
    event = INPUT(
        type=INPUT_MOUSE,
        union=_INPUTUNION(mi=MOUSEINPUT(0, 0, 0, flags, 0, None)),
    )
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        raise OSError("SendInput falhou ao enviar clique do mouse")


class MouseController:
    """Segura mouse -> zona direita. Solta -> zona esquerda."""

    def __init__(self, deadband_px: float = 4.0) -> None:
        self.deadband_px = deadband_px
        self._holding = False

    @property
    def holding(self) -> bool:
        return self._holding

    def press(self) -> None:
        if not self._holding:
            _send_mouse_button(MOUSEEVENTF_LEFTDOWN)
            self._holding = True

    def release(self) -> None:
        if self._holding:
            _send_mouse_button(MOUSEEVENTF_LEFTUP)
            self._holding = False

    def pause(self) -> str:
        return "hold-pause" if self._holding else "pause"

    def stop(self) -> str:
        self.release()
        return "idle"

    def update(self, result: DetectionResult) -> str:
        x_hook = result.x_hook_control if result.x_hook_control is not None else result.x_hook
        left = result.blue_left_control if result.blue_left_control is not None else result.blue_left
        right = result.blue_right_control if result.blue_right_control is not None else result.blue_right
        error = result.error_control if result.error_control is not None else result.error

        assert x_hook is not None and left is not None and right is not None and error is not None

        if x_hook > right:
            self.press()
            return "chase-right"

        if x_hook < left:
            self.release()
            return "chase-left"

        db = self.deadband_px
        if error > db:
            self.press()
            return "track-left"

        if error < -db:
            self.release()
            return "track-right"

        if self._holding:
            if error <= 0:
                self.release()
                return "center"
            return "track-left"

        return "center"
