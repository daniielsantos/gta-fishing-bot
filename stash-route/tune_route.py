"""
Re-grava um trecho da rota a partir de um ponto (correcao manual).

Quando o replay quase funciona mas desvia perto da escada/carro:
  1. Rode o replay e anote o t_ms do log onde desviou (ex.: 25000)
  2. Posicione o personagem como no replay ate esse ponto
  3. Rode:
       python stash-route/tune_route.py --route pier_to_car --from-ms 25000
  4. O bot repete ate 25000ms, voce corrige daqui ate o fim
  5. F10 salva a rota mesclada

Substitui todos os eventos apos --from-ms pela nova gravacao.
"""

from __future__ import annotations

import argparse
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
    ROUTE_VERSION_EVENTS,
    close_stash_log,
    load_route,
    merge_event_routes,
    new_event_route,
    resolve_route_path,
    route_summary,
    save_route,
    stamp_ms,
    stash_log,
    wait_until,
)
from walk_route import ComboPlayer, countdown


def _key_char(key: keyboard.Key | keyboard.KeyCode) -> str | None:
    if isinstance(key, keyboard.KeyCode) and key.char:
        return key.char.lower()
    return None


MOVEMENT_KEYS = frozenset({"w", "a", "s", "d"})


class PatchRecorder:
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
        held = "+".join(sort_movement_keys(self.pressed)) or "(nenhuma)"
        stash_log(f"[tune] {action} {key} @ +{t_ms}ms | segurando: {held}")

    def on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if key == keyboard.Key.f10:
            self.save_requested = True
            self.running = False
            return
        if key == keyboard.Key.esc:
            self.running = False
            stash_log("[tune] cancelado (ESC)")
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


def play_until(route: dict, until_ms: int, *, countdown_sec: int) -> None:
    events = [event for event in route["events"] if int(event["t_ms"]) < until_ms]
    if not events:
        stash_log(f"[tune] Nenhum evento antes de {until_ms}ms — va manualmente ao ponto")
        countdown(countdown_sec)
        return

    stash_log(f"[tune] Reproduzindo {len(events)} eventos ate {until_ms}ms")
    countdown(countdown_sec)

    player = ComboPlayer(use_scancode=True)
    route_start = time.perf_counter()
    try:
        for event in events:
            target_at = route_start + int(event["t_ms"]) / 1000.0
            wait_until(target_at)
            if event["action"] == "down":
                player.apply_down(str(event["key"]))
            else:
                player.apply_up(str(event["key"]))
        wait_until(route_start + until_ms / 1000.0)
    finally:
        player.release_all()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Corrige trecho final de rota gravada")
    parser.add_argument("--route", default="pier_to_car")
    parser.add_argument(
        "--from-ms",
        type=int,
        required=True,
        help="t_ms do log onde comecar a correcao (substitui o restante)",
    )
    parser.add_argument("--countdown", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    route_path = resolve_route_path(args.route)

    if not route_path.exists():
        stash_log(f"[tune] Rota nao encontrada: {route_path}")
        close_stash_log()
        sys.exit(1)

    route = load_route(route_path)
    if route.get("version") != ROUTE_VERSION_EVENTS:
        stash_log("[tune] Suporta apenas rotas v2 (key_events)")
        close_stash_log()
        sys.exit(1)

    stash_log(__doc__.strip())
    stash_log(f"[tune] Rota: {route_path}")
    stash_log(f"[tune] Correcao a partir de {args.from_ms}ms")
    stash_log("[tune] Posicione igual ao replay ate esse instante")
    stash_log("[tune] F10 salvar correcao | ESC cancelar")

    play_until(route, args.from_ms, countdown_sec=args.countdown)

    stash_log("[tune] >>> CORRECAO: ande daqui ate o destino. F10 salvar.")
    recorder = PatchRecorder()
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

    if not recorder.save_requested or not recorder.events:
        stash_log("[tune] Nada salvo")
        close_stash_log()
        return

    merged_events = merge_event_routes(
        route["events"],
        recorder.events,
        from_ms=args.from_ms,
    )
    total_ms = args.from_ms
    if recorder.events:
        total_ms = args.from_ms + int(recorder.events[-1]["t_ms"])
    if route.get("metadata", {}).get("total_duration_ms"):
        total_ms = max(total_ms, int(route["metadata"]["total_duration_ms"]))

    updated = new_event_route(
        route["name"],
        merged_events,
        resolution=config["resolution"],
        description=route.get("description", ""),
        notes=f"corrigido a partir de {args.from_ms}ms",
        total_duration_ms=total_ms,
    )
    save_route(updated, route_path)
    stash_log(f"[tune] Salvo: {route_path}")
    stash_log(f"[tune] {route_summary(updated)}")
    close_stash_log()


if __name__ == "__main__":
    main()
