from __future__ import annotations

import ctypes
import ctypes.wintypes
import time

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000

_user32 = ctypes.windll.user32


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


def _screen_size() -> tuple[int, int]:
    return (
        int(_user32.GetSystemMetrics(0)),
        int(_user32.GetSystemMetrics(1)),
    )


def _to_absolute(x: int, y: int) -> tuple[int, int]:
    width, height = _screen_size()
    abs_x = int(x * 65535 / max(width - 1, 1))
    abs_y = int(y * 65535 / max(height - 1, 1))
    return abs_x, abs_y


def _send_mouse(flags: int, *, x: int = 0, y: int = 0) -> None:
    event = INPUT(
        type=INPUT_MOUSE,
        union=_INPUTUNION(mi=MOUSEINPUT(x, y, 0, flags, 0, None)),
    )
    sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        raise OSError("SendInput falhou ao mover/clicar mouse")


def move_mouse(x: int, y: int) -> None:
    abs_x, abs_y = _to_absolute(x, y)
    _send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, x=abs_x, y=abs_y)


def click_mouse(x: int, y: int, *, hold_ms: float = 30.0) -> None:
    move_mouse(x, y)
    time.sleep(0.02)
    _send_mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(max(hold_ms, 0) / 1000.0)
    _send_mouse(MOUSEEVENTF_LEFTUP)


def drag_mouse(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    hold_before_ms: float = 80.0,
    drag_ms: float = 200.0,
    hold_after_ms: float = 80.0,
) -> None:
    """Arrasta do ponto 1 ao ponto 2 (inventario: bolso -> porta-malas)."""
    move_mouse(x1, y1)
    time.sleep(0.03)
    _send_mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(max(hold_before_ms, 0) / 1000.0)

    steps = max(8, int(drag_ms / 25))
    for step in range(1, steps + 1):
        t = step / steps
        x = int(x1 + (x2 - x1) * t)
        y = int(y1 + (y2 - y1) * t)
        move_mouse(x, y)
        time.sleep(drag_ms / steps / 1000.0)

    time.sleep(max(hold_after_ms, 0) / 1000.0)
    _send_mouse(MOUSEEVENTF_LEFTUP)
