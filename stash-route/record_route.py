"""
Grava uma rota a pe (WASD + tempo) para replay posterior.

Timestamps no instante do press/release (pynput + perf_counter), nao polling.

Uso:
  1. Personagem no ponto inicial (ex.: grade azul no pier)
  2. Jogo em foco, mesma camera/resolucao do bot
  3. Rode: python stash-route/record_route.py
  4. Ande ate o destino (ex.: carro) usando so W/A/S/D
  5. F10 = salvar rota | F11 = desfazer ultimo evento | ESC = sair sem salvar
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from pynput import keyboard

ROOT = Path(__file__).resolve().parent.parent
STASH_ROUTE_DIR = Path(__file__).resolve().parent
for path in (ROOT, STASH_ROUTE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from config_loader import load_config
from keyboard_input import sort_movement_keys
from route_utils import (
    MOVEMENT_KEYS,
    ROUTES_DIR,
    close_stash_log,
    new_event_route,
    route_summary,
    save_route,
    stamp_ms,
    stash_log,
)


def _key_char(key: keyboard.Key | keyboard.KeyCode) -> str | None:
    if isinstance(key, keyboard.KeyCode) and key.char:
        return key.char.lower()
    return None


class EventRouteRecorder:
    def __init__(self) -> None:
        self.pressed: set[str] = set()
        self.events: list[dict[str, str | int]] = []
        self.started_at: float | None = None
        self.running = True
        self.save_requested = False

    def _record_event(self, key: str, action: str) -> None:
        t_ms, self.started_at = stamp_ms(self.started_at)
        event = {"t_ms": t_ms, "key": key, "action": action}
        self.events.append(event)

        if action == "down":
            held = set(self.pressed)
            held.add(key)
            held_label = "+".join(sort_movement_keys(held))
            stash_log(
                f"[record] down {key} @ {t_ms}ms "
                f"| toque em {key} | combo agora: {held_label}"
            )
        else:
            remaining = set(self.pressed)
            remaining.discard(key)
            remaining_label = "+".join(sort_movement_keys(remaining)) or "(nenhuma)"
            stash_log(
                f"[record] up {key} @ {t_ms}ms "
                f"| soltou {key} | continua: {remaining_label}"
            )

    def on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if key == keyboard.Key.f10:
            self.save_requested = True
            self.running = False
            return

        if key == keyboard.Key.f11:
            self.undo_last_event()
            return

        if key == keyboard.Key.esc:
            self.running = False
            stash_log("[record] cancelado (ESC) — nada salvo")
            return

        char = _key_char(key)
        if char in MOVEMENT_KEYS and char not in self.pressed:
            self.pressed.add(char)
            self._record_event(char, "down")

    def on_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        char = _key_char(key)
        if char in MOVEMENT_KEYS and char in self.pressed:
            self.pressed.discard(char)
            self._record_event(char, "up")

    def undo_last_event(self) -> None:
        if not self.events:
            stash_log("[record] nenhum evento para remover")
            return

        removed = self.events.pop()
        key = str(removed["key"])
        if removed["action"] == "down":
            self.pressed.discard(key)
        else:
            self.pressed.add(key)
        stash_log(
            f"[record] removido: {removed['action']} {key} @ {removed['t_ms']}ms"
        )

    def total_duration_ms(self) -> int:
        if not self.events:
            return 0
        t_ms, _ = stamp_ms(self.started_at)
        return t_ms


def main() -> None:
    config = load_config()
    resolution = config["resolution"]
    route_name = "pier_to_car"
    output_path = ROUTES_DIR / f"{route_name}.json"
    description = "Grade azul -> escada -> SUV branco no pier"

    stash_log(__doc__.strip())
    stash_log(f"[record] Destino: {output_path}")
    stash_log("[record] Timestamps: instante do press/release (perf_counter)")
    stash_log("[record] F10 salvar | F11 desfazer ultimo evento | ESC cancelar")
    stash_log("[record] Segure W; toque A/D para curvar")
    stash_log("[record] Ande com W/A/S/D. Nao use mouse.")
    stash_log(
        f"[record] Resolucao de referencia: "
        f"{resolution['width']}x{resolution['height']}"
    )

    recorder = EventRouteRecorder()
    listener = keyboard.Listener(
        on_press=recorder.on_press,
        on_release=recorder.on_release,
    )
    listener.start()

    try:
        while recorder.running:
            time.sleep(0.05)
    finally:
        listener.stop()

    if not recorder.save_requested:
        close_stash_log()
        return

    if not recorder.events:
        stash_log("[record] Nenhum evento gravado — arquivo nao criado")
        close_stash_log()
        return

    total_duration_ms = recorder.total_duration_ms()
    route = new_event_route(
        route_name,
        recorder.events,
        resolution=resolution,
        description=description,
        total_duration_ms=total_duration_ms,
    )
    save_route(route, output_path)
    stash_log(f"[record] Salvo: {output_path}")
    stash_log(f"[record] {route_summary(route)}")
    close_stash_log()


if __name__ == "__main__":
    main()
