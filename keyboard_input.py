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
    "g": 0x47,
    "i": 0x49,
    "esc": 0x1B,
    "escape": 0x1B,
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


def press_key(key: str, use_scancode: bool = True) -> None:
    """Pressiona tecla (down) sem soltar."""
    vk = _vk_for(key)
    scan = _scan_for_vk(vk)
    if use_scancode:
        _press_scan(scan)
    else:
        _press_vk(vk)


def release_key(key: str, use_scancode: bool = True) -> None:
    """Solta tecla (up)."""
    vk = _vk_for(key)
    scan = _scan_for_vk(vk)
    if use_scancode:
        _release_scan(scan)
    else:
        _release_vk(vk)


def release_keys(keys: list[str], use_scancode: bool = True) -> None:
    for key in reversed(keys):
        release_key(key, use_scancode=use_scancode)


def _keyboard_event(key: str, *, key_up: bool = False, use_scancode: bool = True) -> KEYBDINPUT:
    vk = _vk_for(key)
    scan = _scan_for_vk(vk)
    if use_scancode:
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
        return KEYBDINPUT(vk, scan, flags, 0, None)
    flags = KEYEVENTF_KEYUP if key_up else 0
    return KEYBDINPUT(vk, 0, flags, 0, None)


def _send_keyboard_batch(events: list[KEYBDINPUT]) -> None:
    if not events:
        return
    inputs = (INPUT * len(events))(
        *[INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=event)) for event in events]
    )
    sent = _user32.SendInput(len(events), ctypes.byref(inputs[0]), ctypes.sizeof(INPUT))
    if sent != len(events):
        raise OSError(f"SendInput batch falhou ({sent}/{len(events)})")


def press_keys(keys: list[str], use_scancode: bool = True) -> None:
    """Pressiona varias teclas no mesmo batch SendInput (combo simultaneo)."""
    if not keys:
        return
    _send_keyboard_batch(
        [_keyboard_event(key, key_up=False, use_scancode=use_scancode) for key in keys]
    )


def release_keys_batch(keys: list[str], use_scancode: bool = True) -> None:
    """Solta varias teclas no mesmo batch SendInput."""
    if not keys:
        return
    _send_keyboard_batch(
        [_keyboard_event(key, key_up=True, use_scancode=use_scancode) for key in reversed(keys)]
    )


KEY_PRESS_ORDER = ("w", "a", "s", "d")


def sort_movement_keys(keys: list[str] | set[str]) -> list[str]:
    order = {key: index for index, key in enumerate(KEY_PRESS_ORDER)}
    return sorted(keys, key=lambda key: order.get(key, len(KEY_PRESS_ORDER)))


def sync_movement_combo(
    target_keys: list[str] | set[str],
    *,
    currently_held: set[str],
    use_scancode: bool = True,
) -> set[str]:
    """
    Sincroniza combo no jogo.
    - Ao ADICIONAR: pressiona so as teclas novas (nao re-envia as ja seguradas).
    - Ao REMOVER: solta so as que sairam.
    """
    target = set(target_keys)
    to_release = sort_movement_keys(currently_held - target)
    to_press = sort_movement_keys(target - currently_held)

    if to_release:
        release_keys_batch(to_release, use_scancode=use_scancode)

    for key in to_press:
        press_key(key, use_scancode=use_scancode)

    return target


def is_key_physically_down(key: str) -> bool:
    vk = _vk_for(key)
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def read_movement_keys_held() -> frozenset[str]:
    """Le estado real do teclado (hardware) para gravacao precisa de toques."""
    return frozenset(key for key in KEY_PRESS_ORDER if is_key_physically_down(key))


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


def hold_keys(keys: list[str], hold_ms: float = 50.0, use_scancode: bool = True) -> None:
    """Segura varias teclas ao mesmo tempo por hold_ms (ex.: w + d na diagonal)."""
    if not keys:
        return
    vks = [_vk_for(key) for key in keys]
    scans = [_scan_for_vk(vk) for vk in vks]

    if use_scancode:
        for scan in scans:
            _press_scan(scan)
    else:
        for vk in vks:
            _press_vk(vk)

    time.sleep(max(hold_ms, 0) / 1000.0)

    if use_scancode:
        for scan in reversed(scans):
            _release_scan(scan)
    else:
        for vk in reversed(vks):
            _release_vk(vk)


def debug_key_info(key: str) -> str:
    vk = _vk_for(key)
    scan = _scan_for_vk(vk)
    return f"key={key!r} vk=0x{vk:02X} scan=0x{scan:02X}"
