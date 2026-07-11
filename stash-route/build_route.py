"""
Construtor FACIL de rota — um segmento por vez.

Muito mais simples que gravar a rota inteira:
  1. Va ao ponto inicial no jogo
  2. Segure as teclas do trecho (ex.: so W, ou W+D)
  3. SPACE = comeca a cronometrar esse segmento
  4. SPACE de novo = para e salva o segmento
  5. Repita para cada trecho (reta, curva, escada...)
  6. F10 = salvar pier_to_car.json

Regra: nao mude teclas no meio do segmento — um combo por vez.
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
from keyboard_input import read_movement_keys_held, sort_movement_keys
from route_utils import (
    ROUTES_DIR,
    close_stash_log,
    merge_adjacent_segments,
    new_route,
    route_summary,
    save_route,
    stash_log,
)


class SegmentBuilder:
    def __init__(self) -> None:
        self.segments: list[dict[str, object]] = []
        self.active = False
        self.active_keys: frozenset[str] = frozenset()
        self.active_since: float | None = None
        self.running = True
        self.save_requested = False

    def _toggle_segment(self) -> None:
        held = read_movement_keys_held()
        now = time.perf_counter()

        if not self.active:
            if not held:
                stash_log("[build] Segure W/A/S/D antes do SPACE")
                return
            self.active = True
            self.active_keys = held
            self.active_since = now
            label = "+".join(sort_movement_keys(held))
            stash_log(f"[build] >>> segmento {len(self.segments) + 1} INICIOU: {label}")
            return

        if self.active_since is None:
            return
        duration_ms = max(1, round((now - self.active_since) * 1000))
        segment = {
            "keys": sort_movement_keys(self.active_keys),
            "duration_ms": duration_ms,
        }
        self.segments.append(segment)
        label = "+".join(segment["keys"])
        stash_log(
            f"[build] <<< segmento {len(self.segments)} SALVO: "
            f"{label} por {duration_ms / 1000:.1f}s"
        )
        self.active = False
        self.active_keys = frozenset()
        self.active_since = None

    def undo_segment(self) -> None:
        if self.active:
            self.active = False
            self.active_keys = frozenset()
            self.active_since = None
            stash_log("[build] segmento em andamento cancelado")
            return
        if self.segments:
            removed = self.segments.pop()
            stash_log(
                f"[build] removido segmento: "
                f"{'+'.join(removed['keys'])} ({removed['duration_ms']}ms)"
            )
        else:
            stash_log("[build] nenhum segmento para remover")

    def on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if key == keyboard.Key.space:
            self._toggle_segment()
            return
        if key == keyboard.Key.f10:
            if self.active:
                self._toggle_segment()
            self.save_requested = True
            self.running = False
            return
        if key == keyboard.Key.f11:
            self.undo_segment()
            return
        if key == keyboard.Key.esc:
            self.running = False
            stash_log("[build] cancelado (ESC)")


def main() -> None:
    config = load_config()
    resolution = config["resolution"]
    route_name = "pier_to_car"
    output_path = ROUTES_DIR / f"{route_name}.json"

    stash_log(__doc__.strip())
    stash_log(f"[build] Destino: {output_path}")
    stash_log("[build] SPACE = inicio/fim do segmento | F11 = desfazer | F10 = salvar")
    stash_log("[build] Exemplo: segure W -> SPACE -> ande -> SPACE -> segure W+D -> SPACE ...")
    stash_log(
        f"[build] Resolucao: {resolution['width']}x{resolution['height']}"
    )

    builder = SegmentBuilder()
    listener = keyboard.Listener(on_press=builder.on_press)
    listener.start()

    try:
        while builder.running:
            time.sleep(0.05)
    finally:
        listener.stop()

    if not builder.save_requested:
        close_stash_log()
        return

    if not builder.segments:
        stash_log("[build] Nenhum segmento — nada salvo")
        close_stash_log()
        return

    merged = merge_adjacent_segments(builder.segments)
    route = new_route(
        route_name,
        merged,
        resolution=resolution,
        description="Montada com build_route.py (segmentos SPACE)",
    )
    save_route(route, output_path)
    stash_log(f"[build] Salvo: {output_path}")
    stash_log(f"[build] {route_summary(route)}")
    stash_log("[build] Teste: python stash-route/walk_route.py --route pier_to_car")
    stash_log("[build] Ajuste: python stash-route/edit_route.py --route pier_to_car")
    close_stash_log()


if __name__ == "__main__":
    main()
