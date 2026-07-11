"""
Editor simples de rota — ajusta duracao sem regravar.

Uso:
  python stash-route/edit_route.py --route pier_to_car

Comandos no editor:
  numero     = seleciona segmento (ex.: 3)
  + / -      = +100ms / -100ms no segmento selecionado
  ++ / --    = +500ms / -500ms
  p          = testar rota inteira
  t          = testar a partir do segmento selecionado
  d          = apagar segmento selecionado
  s          = salvar
  q          = sair sem salvar
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STASH_ROUTE_DIR = Path(__file__).resolve().parent
for path in (ROOT, STASH_ROUTE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from config_loader import load_config
from route_utils import (
    ROUTE_VERSION,
    ROUTE_VERSION_EVENTS,
    events_to_segments,
    load_route,
    resolve_route_path,
    route_summary,
    save_route,
)
from walk_route import play_route


def route_to_segments(route: dict) -> list[dict]:
    if route.get("version") == ROUTE_VERSION_EVENTS:
        total_ms = int(route.get("metadata", {}).get("total_duration_ms", 0))
        return events_to_segments(route["events"], total_duration_ms=total_ms or None)
    return copy.deepcopy(route["segments"])


def segments_to_route(route: dict, segments: list[dict]) -> dict:
    updated = copy.deepcopy(route)
    updated["version"] = ROUTE_VERSION
    updated["format"] = "segments"
    updated["segments"] = segments
    if "events" in updated:
        del updated["events"]
    metadata = dict(updated.get("metadata", {}))
    metadata["edited_with"] = "edit_route.py"
    updated["metadata"] = metadata
    return updated


def print_segments(segments: list[dict], selected: int) -> None:
    total_ms = sum(int(segment["duration_ms"]) for segment in segments)
    print(f"\n--- {len(segments)} segmentos, {total_ms / 1000:.1f}s total ---")
    for index, segment in enumerate(segments):
        keys = "+".join(segment["keys"])
        sec = int(segment["duration_ms"]) / 1000
        marker = ">>" if index == selected else "  "
        print(f"{marker} [{index + 1}] {keys:8} {sec:6.1f}s")
    print("---")
    print("numero | +/- 100ms | ++/-- 500ms | p testar | t testar daqui | d apagar | s salvar | q sair")


def test_route(route: dict, *, from_segment: int = 0, config: dict) -> None:
    segments = route["segments"]
    if from_segment > 0:
        offset_ms = sum(int(s["duration_ms"]) for s in segments[: from_segment - 1])
        trimmed = copy.deepcopy(route)
        trimmed["segments"] = segments[from_segment - 1 :]
        stash_log(f"[edit] Testando a partir do segmento {from_segment} (+{offset_ms}ms omitidos)")
        play_route(trimmed, countdown_sec=5, time_scale=float(config.get("stash_route", {}).get("time_scale", 1.0)))
        return
    play_route(route, countdown_sec=5, time_scale=float(config.get("stash_route", {}).get("time_scale", 1.0)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Editor de segmentos da rota")
    parser.add_argument("--route", default="pier_to_car")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    route_path = resolve_route_path(args.route)

    if not route_path.exists():
        print(f"Rota nao encontrada: {route_path}")
        print("Crie com: python stash-route/build_route.py")
        sys.exit(1)

    base_route = load_route(route_path)
    segments = route_to_segments(base_route)
    if not segments:
        print("Rota vazia")
        sys.exit(1)

    working = segments_to_route(base_route, segments)
    selected = 0
    print(__doc__.strip())
    print_segments(working["segments"], selected)

    while True:
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nSaindo sem salvar")
            break

        if not cmd:
            continue
        if cmd in {"q", "quit", "sair"}:
            break
        if cmd == "s":
            save_route(working, route_path)
            print(f"Salvo: {route_path}")
            print(route_summary(working))
            break
        if cmd == "p":
            test_route(working, config=config)
            print_segments(working["segments"], selected)
            continue
        if cmd == "t":
            test_route(working, from_segment=selected + 1, config=config)
            print_segments(working["segments"], selected)
            continue
        if cmd == "d":
            if working["segments"]:
                removed = working["segments"].pop(selected)
                print(f"Apagado: {'+'.join(removed['keys'])} {removed['duration_ms']}ms")
                selected = min(selected, len(working["segments"]) - 1)
                selected = max(0, selected)
            print_segments(working["segments"], selected)
            continue
        if cmd in {"+", "++", "-", "--"}:
            if not working["segments"]:
                continue
            delta = 500 if cmd in {"++", "--"} else 100
            if cmd in {"-", "--"}:
                delta = -delta
            segment = working["segments"][selected]
            new_ms = max(50, int(segment["duration_ms"]) + delta)
            segment["duration_ms"] = new_ms
            print(f"Segmento {selected + 1}: {new_ms}ms")
            print_segments(working["segments"], selected)
            continue
        if cmd.isdigit():
            index = int(cmd) - 1
            if 0 <= index < len(working["segments"]):
                selected = index
            print_segments(working["segments"], selected)
            continue

        print("Comando invalido")
        print_segments(working["segments"], selected)


if __name__ == "__main__":
    main()
