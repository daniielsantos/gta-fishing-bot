from __future__ import annotations

import ctypes
import ctypes.wintypes
import time


INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MAPVK_VK_TO_VSC = 0

VK_MAP = {
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
    "e": 0x45,
    "w": 0x57,
    "a": 0x41,
    "s": 0x53,
    "d": 0x44,
}

_user32 = ctypes.windll.user32


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


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
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("union", _INPUTUNION),
    ]


def _vk_for(key: str) -> int:
    normalized = key.lower()
    if normalized not in VK_MAP:
        raise ValueError(f"Tecla nao suportada: {key}")
    return VK_MAP[normalized]


def _scan_for_vk(vk: int) -> int:
    return int(_user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)) & 0xFF


def _send_input_keyboard(ki: KEYBDINPUT) -> None:
    event = INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=ki))
    sent = _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        raise OSError(f"SendInput falhou (vk={ki.wVk}, scan={ki.wScan}, flags={ki.dwFlags})")


def _press_vk(vk: int) -> None:
    _send_input_keyboard(KEYBDINPUT(vk, 0, 0, 0, None))


def _release_vk(vk: int) -> None:
    _send_input_keyboard(KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, None))


def _press_scan(scan: int) -> None:
    _send_input_keyboard(KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE, 0, None))


def _release_scan(scan: int) -> None:
    _send_input_keyboard(KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, None))


def hold_key(key: str, hold_ms: float = 50.0, use_scancode: bool = True) -> None:
    """Segura tecla por hold_ms. Jogos DirectX preferem scancode."""
    vk = _vk_for(key)
    scan = _scan_for_vk(vk)

    if use_scancode:
        _press_scan(scan)
    else:
        _press_vk(vk)

    time.sleep(max(hold_ms, 0) / 1000.0)

    if use_scancode:
        _release_scan(scan)
    else:
        _release_vk(vk)


def tap_key(key: str, hold_ms: float = 50.0, use_scancode: bool = True) -> None:
    hold_key(key, hold_ms=hold_ms, use_scancode=use_scancode)


def debug_key_info(key: str) -> str:
    vk = _vk_for(key)
    scan = _scan_for_vk(vk)
    return f"key={key!r} vk=0x{vk:02X} scan=0x{scan:02X}"
