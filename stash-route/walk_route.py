"""
Replay de rota gravada (WASD + tempo).

Suporta:
  - v2 key_events: replay evento a evento (melhor para W segurado + A/D)
  - v1 segments: replay por segmentos com combo sincronizado em batch

Uso:
  python stash-route/walk_route.py --route pier_to_car
  python stash-route/walk_route.py --route pier_to_car --countdown 5
  python stash-route/walk_route.py --route pier_to_car --reverse
  python stash-route/walk_route.py --route pier_to_car --reverse --save-reverse

Antes de iniciar, deixe o jogo em foco na posicao inicial da rota.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STASH_ROUTE_DIR = Path(__file__).resolve().parent
for path in (ROOT, STASH_ROUTE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from config_loader import load_config
from keyboard_input import (
    press_key,
    release_key,
    release_keys_batch,
    sort_movement_keys,
)
from route_utils import (
    ROUTE_VERSION_EVENTS,
    apply_time_scale,
    close_stash_log,
    load_route,
    resolve_route_path,
    reverse_route,
    route_summary,
    save_route,
    stash_log,
    wait_until,
)


class ComboPlayer:
    """
    Replay evento a evento:
    - down: pressiona SO a tecla nova (nao re-envia as que ja estao seguradas)
    - up: solta SO a tecla que subiu
    """

    def __init__(self, *, use_scancode: bool = True) -> None:
        self.held: set[str] = set()
        self.use_scancode = use_scancode

    def apply_down(self, key: str) -> tuple[list[str], list[str]]:
        if key in self.held:
            return [], []
        already = sort_movement_keys(self.held)
        self.held.add(key)
        press_key(key, use_scancode=self.use_scancode)
        return [key], already

    def apply_up(self, key: str) -> tuple[list[str], list[str]]:
        if key not in self.held:
            return [], []
        self.held.discard(key)
        release_key(key, use_scancode=self.use_scancode)
        return [], [key]

    def apply_combo(self, target_keys: list[str]) -> tuple[list[str], list[str]]:
        before = set(self.held)
        target = set(target_keys)
        to_release = sort_movement_keys(before - target)
        to_press = sort_movement_keys(target - before)

        if to_release:
            release_keys_batch(to_release, use_scancode=self.use_scancode)
        for key in to_press:
            press_key(key, use_scancode=self.use_scancode)

        self.held = target
        return to_press, to_release

    def release_all(self) -> list[str]:
        released = sort_movement_keys(self.held)
        if released:
            release_keys_batch(released, use_scancode=self.use_scancode)
        self.held.clear()
        return released


def countdown(seconds: int) -> None:
    if seconds <= 0:
        return
    stash_log(f"[walk] Iniciando em {seconds}s — deixe o jogo em foco")
    for remaining in range(seconds, 0, -1):
        stash_log(f"[walk]   {remaining}...")
        time.sleep(1)


def play_event_route(
    route: dict,
    *,
    countdown_sec: int = 5,
    time_scale: float = 1.0,
) -> None:
    if time_scale != 1.0:
        route = apply_time_scale(route, time_scale)
        stash_log(f"[walk] time-scale={time_scale:.3f} aplicado")
    events = route["events"]
    stash_log(f"[walk] {route_summary(route)}")
    stash_log("[walk] Modo: key_events + relogio absoluto (sem drift acumulado)")
    countdown(countdown_sec)

    player = ComboPlayer(use_scancode=True)
    route_start = time.perf_counter()
    max_skew_ms = 0

    try:
        for index, event in enumerate(events, start=1):
            target_at = route_start + int(event["t_ms"]) / 1000.0
            skew_ms = wait_until(target_at)

            key = str(event["key"])
            action = str(event["action"])
            if action == "down":
                _, already = player.apply_down(key)
                already_label = "+".join(already) if already else "(nenhuma)"
                detail = f"nova +{key} | ja segurando: {already_label}"
            else:
                player.apply_up(key)
                detail = f"soltou -{key}"

            actual_ms = round((time.perf_counter() - route_start) * 1000)
            max_skew_ms = max(max_skew_ms, abs(skew_ms))
            skew_note = f" skew={skew_ms:+.0f}ms" if abs(skew_ms) >= 3 else ""
            held_label = "+".join(sort_movement_keys(player.held)) or "(nenhuma)"
            stash_log(
                f"[walk] evento {index}/{len(events)}: {action} {key} "
                f"@ {event['t_ms']}ms (real {actual_ms}ms){skew_note} | "
                f"{detail} | combo: {held_label}"
            )

        total_ms = int(route.get("metadata", {}).get("total_duration_ms", 0))
        if total_ms <= 0 and events:
            total_ms = int(events[-1]["t_ms"])
        if total_ms > int(events[-1]["t_ms"]) and player.held:
            target_at = route_start + total_ms / 1000.0
            held_label = "+".join(sort_movement_keys(player.held))
            stash_log(f"[walk] mantendo {held_label} ate {total_ms}ms")
            wait_until(target_at)
    finally:
        released = player.release_all()
        if released:
            stash_log(f"[walk] Teclas soltas ao final: {''.join(released)}")

    stash_log(f"[walk] Rota finalizada | maior skew de timing: {max_skew_ms:.0f}ms")


def play_segment_route(
    route: dict,
    *,
    gap_ms: int = 0,
    countdown_sec: int = 5,
    time_scale: float = 1.0,
) -> None:
    if time_scale != 1.0:
        route = apply_time_scale(route, time_scale)
        stash_log(f"[walk] time-scale={time_scale:.3f} aplicado")
    stash_log(f"[walk] {route_summary(route)}")
    stash_log("[walk] Modo: segmentos + combo batch")
    countdown(countdown_sec)

    player = ComboPlayer(use_scancode=True)
    total_segments = len(route["segments"])
    route_start = time.perf_counter()
    timeline_ms = 0

    try:
        for index, segment in enumerate(route["segments"], start=1):
            keys = segment["keys"]
            duration_ms = int(segment["duration_ms"])
            keys_label = "+".join(keys)
            note = segment.get("note")
            note_suffix = f" ({note})" if note else ""

            wait_until(route_start + timeline_ms / 1000.0)
            stash_log(
                f"[walk] segmento {index}/{total_segments}: "
                f"{keys_label} por {duration_ms}ms{note_suffix}"
            )
            to_press, to_release = player.apply_combo(keys)
            timeline_ms += duration_ms
            wait_until(route_start + timeline_ms / 1000.0)
            elapsed_ms = duration_ms

            changes = []
            if to_press:
                changes.append(f"+{''.join(to_press)}")
            if to_release:
                changes.append(f"-{''.join(to_release)}")
            change_label = " ".join(changes) if changes else "mantem"
            held_label = "+".join(sort_movement_keys(player.held)) or "(nenhuma)"
            stash_log(
                f"[walk]   {elapsed_ms}ms | {change_label} | segurando: {held_label}"
            )

            timeline_ms += gap_ms
    finally:
        released = player.release_all()
        if released:
            stash_log(f"[walk] Teclas soltas ao final: {''.join(released)}")

    stash_log("[walk] Rota finalizada")


def play_route(
    route: dict,
    *,
    gap_ms: int = 0,
    countdown_sec: int = 5,
    time_scale: float = 1.0,
) -> None:
    if route.get("version") == ROUTE_VERSION_EVENTS:
        play_event_route(route, countdown_sec=countdown_sec, time_scale=time_scale)
        return
    play_segment_route(
        route,
        gap_ms=gap_ms,
        countdown_sec=countdown_sec,
        time_scale=time_scale,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay de rota WASD gravada")
    parser.add_argument(
        "--route",
        default="pier_to_car",
        help="Nome (ex.: pier_to_car) ou caminho para .json",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Inverte a rota (A<->D, ordem dos segmentos)",
    )
    parser.add_argument(
        "--save-reverse",
        action="store_true",
        help="Salva a rota invertida em routes/car_to_pier.json",
    )
    parser.add_argument(
        "--countdown",
        type=int,
        default=5,
        help="Segundos de espera antes do replay (padrao: 5)",
    )
    parser.add_argument(
        "--gap-ms",
        type=int,
        default=None,
        help="Pausa extra entre segmentos v1 (padrao: 0)",
    )
    parser.add_argument(
        "--time-scale",
        type=float,
        default=None,
        help="Multiplica duracoes (ex.: 1.03 = 3%% mais lento, ajuda com lag)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    stash_cfg = config.get("stash_route", {})

    gap_ms = args.gap_ms
    if gap_ms is None:
        gap_ms = int(stash_cfg.get("segment_gap_ms", 0))

    time_scale = args.time_scale
    if time_scale is None:
        time_scale = float(stash_cfg.get("time_scale", 1.0))

    route_path = resolve_route_path(args.route)
    if not route_path.exists():
        stash_log(f"[walk] Rota nao encontrada: {route_path}")
        stash_log("[walk] Grave primeiro com: python stash-route/record_route.py")
        close_stash_log()
        sys.exit(1)

    route = load_route(route_path)
    expected = config["resolution"]
    recorded = route.get("resolution", {})
    if (
        recorded.get("width") != expected["width"]
        or recorded.get("height") != expected["height"]
    ):
        stash_log(
            "[walk] AVISO: resolucao da rota "
            f"({recorded.get('width')}x{recorded.get('height')}) "
            f"diferente do config ({expected['width']}x{expected['height']})"
        )

    if args.reverse:
        route = reverse_route(route)
        stash_log(f"[walk] Modo invertido: {route['name']}")
        if args.save_reverse:
            reverse_path = STASH_ROUTE_DIR / "routes" / "car_to_pier.json"
            save_route(route, reverse_path)
            stash_log(f"[walk] Rota invertida salva: {reverse_path}")

    try:
        play_route(
            route,
            gap_ms=gap_ms,
            countdown_sec=args.countdown,
            time_scale=time_scale,
        )
    finally:
        close_stash_log()


if __name__ == "__main__":
    main()
