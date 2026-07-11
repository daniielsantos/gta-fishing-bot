from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROUTE_VERSION = 1
ROUTE_VERSION_EVENTS = 2
MOVEMENT_KEYS = frozenset({"w", "a", "s", "d"})
KEY_SWAP = {"a": "d", "d": "a", "w": "w", "s": "s"}

STASH_ROUTE_DIR = Path(__file__).resolve().parent
ROUTES_DIR = STASH_ROUTE_DIR / "routes"
LOG_PATH = STASH_ROUTE_DIR / "stash-route.log"

_log_file = None


def stash_log(message: str) -> None:
    global _log_file
    line = message.rstrip("\n")
    print(line, flush=True)
    if _log_file is None:
        _log_file = LOG_PATH.open("a", encoding="utf-8")
    _log_file.write(line + "\n")
    _log_file.flush()


def close_stash_log() -> None:
    global _log_file
    if _log_file is not None:
        _log_file.flush()
        _log_file.close()
        _log_file = None


def stamp_ms(started_at: float | None, now: float | None = None) -> tuple[int, float]:
    """Retorna (t_ms arredondado, started_at) desde o inicio da gravacao/replay."""
    tick = time.perf_counter() if now is None else now
    if started_at is None:
        return 0, tick
    return round((tick - started_at) * 1000), started_at


def wait_until(target_perf: float) -> float:
    """
    Espera ate o instante absoluto (perf_counter).
    Retorna skew em ms (positivo = executou atrasado).
    """
    while True:
        now = time.perf_counter()
        remaining = target_perf - now
        if remaining <= 0:
            return (now - target_perf) * 1000
        if remaining > 0.005:
            time.sleep(remaining - 0.002)
        else:
            time.sleep(0)


def normalize_keys(keys: list[str]) -> list[str]:
    normalized = [str(k).lower() for k in keys]
    unknown = [k for k in normalized if k not in MOVEMENT_KEYS]
    if unknown:
        raise ValueError(f"Teclas invalidas na rota: {unknown}")
    return sorted(normalized)


def normalize_key(key: str) -> str:
    normalized = str(key).lower()
    if normalized not in MOVEMENT_KEYS:
        raise ValueError(f"Tecla invalida na rota: {key}")
    return normalized


def _validate_segments(route: dict[str, Any]) -> None:
    segments = route.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("Rota precisa ter ao menos um segmento")

    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError(f"Segmento {index} invalido")
        keys = normalize_keys(segment.get("keys", []))
        if not keys:
            raise ValueError(f"Segmento {index} sem teclas")
        duration_ms = int(segment.get("duration_ms", 0))
        if duration_ms <= 0:
            raise ValueError(f"Segmento {index} com duration_ms invalido: {duration_ms}")


def _validate_events(route: dict[str, Any]) -> None:
    events = route.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Rota precisa ter ao menos um evento")

    prev_t = -1
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"Evento {index} invalido")
        normalize_key(str(event.get("key", "")))
        action = str(event.get("action", "")).lower()
        if action not in {"down", "up"}:
            raise ValueError(f"Evento {index} com action invalida: {action}")
        t_ms = int(event.get("t_ms", -1))
        if t_ms < 0:
            raise ValueError(f"Evento {index} com t_ms invalido: {t_ms}")
        if t_ms < prev_t:
            raise ValueError(f"Eventos fora de ordem no indice {index}")
        prev_t = t_ms


def validate_route(route: dict[str, Any]) -> None:
    version = route.get("version")
    if version == ROUTE_VERSION:
        _validate_segments(route)
        return
    if version == ROUTE_VERSION_EVENTS:
        _validate_events(route)
        return
    raise ValueError(f"Versao de rota nao suportada: {version}")


def load_route(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        route = json.load(handle)
    validate_route(route)
    return route


def save_route(route: dict[str, Any], path: Path) -> None:
    validate_route(route)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(route, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def resolve_route_path(route_arg: str) -> Path:
    candidate = Path(route_arg)
    if candidate.suffix == ".json":
        return candidate if candidate.is_absolute() else STASH_ROUTE_DIR.parent / candidate

    name = route_arg.removesuffix(".json")
    return ROUTES_DIR / f"{name}.json"


def new_route(
    name: str,
    segments: list[dict[str, Any]],
    *,
    resolution: dict[str, int],
    description: str = "",
    notes: str = "",
) -> dict[str, Any]:
    route = {
        "version": ROUTE_VERSION,
        "format": "segments",
        "resolution": {
            "width": int(resolution["width"]),
            "height": int(resolution["height"]),
        },
        "name": name,
        "description": description,
        "segments": [
            {
                "keys": normalize_keys(segment["keys"]),
                "duration_ms": int(segment["duration_ms"]),
                **({"note": segment["note"]} if segment.get("note") else {}),
            }
            for segment in segments
        ],
        "metadata": {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
        },
    }
    validate_route(route)
    return route


def new_event_route(
    name: str,
    events: list[dict[str, Any]],
    *,
    resolution: dict[str, int],
    description: str = "",
    notes: str = "",
    total_duration_ms: int | None = None,
) -> dict[str, Any]:
    normalized_events = [
        {
            "t_ms": int(event["t_ms"]),
            "key": normalize_key(str(event["key"])),
            "action": str(event["action"]).lower(),
        }
        for event in events
    ]
    total_ms = total_duration_ms
    if total_ms is None and normalized_events:
        total_ms = normalized_events[-1]["t_ms"]

    route = {
        "version": ROUTE_VERSION_EVENTS,
        "format": "key_events",
        "resolution": {
            "width": int(resolution["width"]),
            "height": int(resolution["height"]),
        },
        "name": name,
        "description": description,
        "events": normalized_events,
        "metadata": {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
            "total_duration_ms": int(total_ms or 0),
        },
    }
    validate_route(route)
    return route


def events_to_segments(
    events: list[dict[str, Any]],
    *,
    total_duration_ms: int | None = None,
) -> list[dict[str, Any]]:
    held: set[str] = set()
    segments: list[dict[str, Any]] = []
    active_keys: frozenset[str] = frozenset()
    segment_start = 0

    def close_until(t_ms: int) -> None:
        nonlocal active_keys, segment_start
        if not active_keys:
            return
        duration_ms = t_ms - segment_start
        if duration_ms > 0:
            segments.append(
                {
                    "keys": sorted(active_keys),
                    "duration_ms": duration_ms,
                }
            )

    for event in events:
        t_ms = int(event["t_ms"])
        close_until(t_ms)
        key = normalize_key(str(event["key"]))
        if event["action"] == "down":
            held.add(key)
        else:
            held.discard(key)
        active_keys = frozenset(held)
        segment_start = t_ms

    end_t = total_duration_ms
    if end_t is None and events:
        end_t = int(events[-1]["t_ms"])
    if end_t is not None and active_keys:
        close_until(int(end_t))

    return merge_adjacent_segments(segments)


def reverse_route(route: dict[str, Any], *, name: str | None = None) -> dict[str, Any]:
    validate_route(route)

    if route.get("version") == ROUTE_VERSION_EVENTS:
        total_ms = int(route.get("metadata", {}).get("total_duration_ms", 0))
        if total_ms <= 0 and route.get("events"):
            total_ms = int(route["events"][-1]["t_ms"])
        segments = events_to_segments(route["events"], total_duration_ms=total_ms or None)
        segment_route = {
            **route,
            "version": ROUTE_VERSION,
            "format": "segments",
            "segments": segments,
        }
        return reverse_route(segment_route, name=name)

    _validate_segments(route)
    reversed_segments: list[dict[str, Any]] = []
    for segment in reversed(route["segments"]):
        swapped_keys = [KEY_SWAP.get(key, key) for key in segment["keys"]]
        reversed_segment: dict[str, Any] = {
            "keys": normalize_keys(swapped_keys),
            "duration_ms": int(segment["duration_ms"]),
        }
        if segment.get("note"):
            reversed_segment["note"] = segment["note"]
        reversed_segments.append(reversed_segment)

    reversed_name = name or route["name"].replace("pier_to_car", "car_to_pier")
    if reversed_name == route["name"]:
        reversed_name = f"{route['name']}_reversed"

    metadata = dict(route.get("metadata", {}))
    metadata["reversed_from"] = route["name"]
    metadata["generated_at"] = datetime.now(timezone.utc).isoformat()

    reversed_route = {
        **route,
        "version": ROUTE_VERSION,
        "format": "segments",
        "name": reversed_name,
        "description": route.get("description", ""),
        "segments": reversed_segments,
        "metadata": metadata,
    }
    if "events" in reversed_route:
        del reversed_route["events"]
    validate_route(reversed_route)
    return reversed_route


def route_summary(route: dict[str, Any]) -> str:
    if route.get("version") == ROUTE_VERSION_EVENTS:
        events = route["events"]
        total_ms = int(route.get("metadata", {}).get("total_duration_ms", 0))
        if total_ms <= 0 and events:
            total_ms = int(events[-1]["t_ms"])
        return (
            f"{route['name']}: {len(events)} eventos, "
            f"{total_ms / 1000:.1f}s total (formato key_events)"
        )

    total_ms = sum(int(segment["duration_ms"]) for segment in route["segments"])
    return (
        f"{route['name']}: {len(route['segments'])} segmentos, "
        f"{total_ms / 1000:.1f}s total"
    )


def merge_adjacent_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Junta segmentos consecutivos com as mesmas teclas (ex.: w + w -> w longo)."""
    merged: list[dict[str, Any]] = []
    for segment in segments:
        keys = normalize_keys(segment["keys"])
        duration_ms = int(segment["duration_ms"])
        if merged and merged[-1]["keys"] == keys:
            merged[-1]["duration_ms"] += duration_ms
            continue
        entry: dict[str, Any] = {"keys": keys, "duration_ms": duration_ms}
        if segment.get("note"):
            entry["note"] = segment["note"]
        merged.append(entry)
    return merged


def scale_event_times(events: list[dict[str, Any]], scale: float) -> list[dict[str, Any]]:
    """Escala intervalos entre eventos (1.05 = 5% mais lento, util com lag)."""
    if scale == 1.0 or not events:
        return events

    scaled: list[dict[str, Any]] = []
    prev_t = 0
    cursor = 0
    for event in events:
        delta = int(event["t_ms"]) - prev_t
        cursor += round(delta * scale)
        scaled.append({**event, "t_ms": cursor})
        prev_t = int(event["t_ms"])
    return scaled


def scale_segment_durations(
    segments: list[dict[str, Any]],
    scale: float,
) -> list[dict[str, Any]]:
    if scale == 1.0 or not segments:
        return segments
    return [
        {**segment, "duration_ms": max(1, round(int(segment["duration_ms"]) * scale))}
        for segment in segments
    ]


def apply_time_scale(route: dict[str, Any], scale: float) -> dict[str, Any]:
    if scale == 1.0:
        return route

    updated = dict(route)
    metadata = dict(route.get("metadata", {}))
    metadata["time_scale_applied"] = scale

    if route.get("version") == ROUTE_VERSION_EVENTS:
        events = scale_event_times(route["events"], scale)
        total_ms = int(metadata.get("total_duration_ms", 0))
        if total_ms > 0:
            total_ms = round(total_ms * scale)
        elif events:
            total_ms = int(events[-1]["t_ms"])
        updated["events"] = events
        metadata["total_duration_ms"] = total_ms
    else:
        updated["segments"] = scale_segment_durations(route["segments"], scale)

    updated["metadata"] = metadata
    return updated


def merge_event_routes(
    base_events: list[dict[str, Any]],
    patch_events: list[dict[str, Any]],
    *,
    from_ms: int,
) -> list[dict[str, Any]]:
    """Mantem eventos antes de from_ms e substitui o restante pelo patch."""
    kept = [event for event in base_events if int(event["t_ms"]) < from_ms]
    shifted_patch = [
        {**event, "t_ms": from_ms + int(event["t_ms"])}
        for event in patch_events
    ]
    merged = kept + shifted_patch
    merged.sort(key=lambda event: int(event["t_ms"]))
    return merged
