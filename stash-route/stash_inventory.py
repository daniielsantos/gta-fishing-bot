"""
Transfere peixes do bolso para o trunk por especie.

Uso:
  python stash-route/stash_inventory.py --dry-run     # so le OCR, sem arrastar
  python stash-route/stash_inventory.py --stash       # abre I, arrasta, ESC
  python stash-route/stash_inventory.py --drag 2 perch  # testa 1 drag

Antes: rode calibrate_inventory.py com inventario aberto (I).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any

import cv2

ROOT = Path(__file__).resolve().parent.parent
STASH_ROUTE_DIR = Path(__file__).resolve().parent
for path in (ROOT, STASH_ROUTE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from config_loader import load_config
from inventory_utils import (
    DEBUG_OCR_DIR,
    crop_roi,
    detect_species_in_slot,
    ensure_tesseract,
    grab_screen,
    inventory_is_full,
    label_roi_for_slot,
    ocr_status_message,
    read_inventory_weight,
    read_inventory_weight_retry,
    read_weight_from_crop,
    read_weight_from_frame,
    read_weight_text_ocr,
    slot_center,
    trunk_index_for_species,
    validate_inventory_calibration,
    weight_ocr_last_error,
    weight_stash_limit,
)
from keyboard_input import release_keys, tap_key
from mouse_input import drag_mouse
from route_utils import close_stash_log, stash_log


def wait_startup_delay(cfg: dict, *, override_sec: float | None = None) -> None:
    if override_sec is not None:
        delay_ms = int(override_sec * 1000)
    else:
        delay_ms = int(cfg.get("startup_delay_ms", 3000))
    if delay_ms <= 0:
        return
    stash_log(f"[stash] Aguardando {delay_ms / 1000:.1f}s — foque o GTA...")
    time.sleep(delay_ms / 1000.0)


def prepare_after_movement(cfg: dict) -> None:
    """Apos anti-afk o personagem ainda 'anda' — solta WASD e espera parar."""
    keys = [str(k) for k in cfg.get("release_keys_before_stash", ["w", "a", "s", "d"])]
    if keys:
        release_keys(keys)
        stash_log(f"[stash] Soltando teclas de movimento: {', '.join(keys)}")
    wait_ms = int(cfg.get("post_movement_wait_ms", 1000))
    if wait_ms > 0:
        stash_log(f"[stash] Aguardando {wait_ms / 1000:.1f}s apos movimento...")
        time.sleep(wait_ms / 1000.0)


def open_inventory(cfg: dict) -> None:
    key = str(cfg.get("open_key", "i"))
    hold_ms = float(cfg.get("inventory_key_hold_ms", 150))
    stash_log(f"[stash] Abrindo inventario: tecla '{key}'")
    tap_key(key, hold_ms=hold_ms, use_scancode=True)
    wait_ms = int(cfg.get("ui_open_wait_ms", 600))
    time.sleep(wait_ms / 1000.0)


def _save_weight_debug_failure(frame, cfg: dict, ocr_raw: str | None) -> None:
    weight_roi = cfg.get("weight_roi")
    if not weight_roi:
        return
    DEBUG_OCR_DIR.mkdir(parents=True, exist_ok=True)
    crop = crop_roi(frame, weight_roi)
    if crop.size > 0:
        crop_path = DEBUG_OCR_DIR / "weight_fail_crop.png"
        cv2.imwrite(str(crop_path), crop)
        stash_log(f"[stash] Debug: recorte do peso salvo em {crop_path}")
    tag = re.sub(r"[^a-z0-9._-]+", "_", (ocr_raw or "none").lower())
    left = max(0, int(weight_roi["left"]) - 40)
    top = max(0, int(weight_roi["top"]) - 30)
    right = int(weight_roi["left"]) + int(weight_roi["width"]) + 120
    bottom = int(weight_roi["top"]) + int(weight_roi["height"]) + 80
    corner = frame[top:bottom, left:right]
    if corner.size > 0:
        corner_path = DEBUG_OCR_DIR / f"weight_fail_corner_{tag}.png"
        cv2.imwrite(str(corner_path), corner)
        stash_log(f"[stash] Debug: canto da tela salvo em {corner_path}")


def close_inventory(cfg: dict) -> None:
    key = str(cfg.get("close_key", "esc"))
    stash_log(f"[stash] Fechando inventario: tecla '{key}'")
    tap_key(key, hold_ms=80, use_scancode=True)
    time.sleep(0.2)


def scan_pocket_fish(frame, cfg: dict, *, debug_ocr: bool = False) -> list[dict]:
    """
    Le cada slot do Pockets independentemente (ordem varia a cada pesca).
    OCR no texto embaixo do slot -> especie -> coluna fixa no trunk.
    """
    pocket_slots = cfg.get("pocket_slots", [])
    fish_species = [str(s).lower() for s in cfg.get("fish_species", [])]
    trunk_order = [str(s).lower() for s in cfg.get("trunk_species_order", [])]
    label_offset = cfg.get("label_offset")
    results: list[dict] = []

    ocr_err = ocr_status_message()
    if ocr_err:
        stash_log(f"[stash] AVISO OCR: {ocr_err}")

    stash_log("[stash] Escaneando Pockets (ordem livre — OCR por slot)")

    for slot in pocket_slots:
        if not slot.get("x") or not slot.get("y"):
            continue
        species, ocr_text = detect_species_in_slot(
            frame,
            slot,
            fish_species,
            label_offset=label_offset,
            debug=debug_ocr,
            slot_index=int(slot.get("index", 0)),
        )
        if not species:
            roi = label_roi_for_slot(slot, label_offset)
            stash_log(
                f"[stash] pocket {slot.get('index', '?')}: "
                f"vazio ou nao-peixe (ocr={ocr_text!r}, roi={roi}) — ignorado"
            )
            continue
        trunk_idx = trunk_index_for_species(species, trunk_order)
        if trunk_idx is None:
            stash_log(f"[stash] pocket {slot.get('index')}: especie {species} sem coluna no trunk")
            continue
        trunk_slots = cfg.get("trunk_slots", [])
        if trunk_idx >= len(trunk_slots):
            stash_log(f"[stash] trunk slot {trunk_idx} nao calibrado")
            continue
        results.append(
            {
                "pocket": slot,
                "trunk": trunk_slots[trunk_idx],
                "species": species,
            }
        )
        stash_log(
            f"[stash] pocket {slot.get('index')} -> {species} "
            f"(trunk col {trunk_idx}, ocr={ocr_text!r})"
        )
    return results


def drag_fish_transfer(cfg: dict, pocket: dict, trunk: dict, species: str) -> None:
    px, py = slot_center(pocket)
    tx, ty = slot_center(trunk)
    stash_log(f"[stash] drag {species}: ({px},{py}) -> ({tx},{ty})")
    drag_mouse(
        px,
        py,
        tx,
        ty,
        hold_before_ms=float(cfg.get("drag_hold_ms", 80)),
        drag_ms=float(cfg.get("drag_duration_ms", 250)),
        hold_after_ms=float(cfg.get("drag_hold_ms", 80)),
    )


def stash_all_fish(
    cfg: dict,
    *,
    dry_run: bool = False,
    debug_ocr: bool = False,
    startup_delay_sec: float | None = None,
) -> int:
    errors = validate_inventory_calibration(cfg)
    if errors:
        for err in errors:
            stash_log(f"[stash] ERRO: {err}")
        return 0

    if not dry_run:
        wait_startup_delay(cfg, override_sec=startup_delay_sec)
        open_inventory(cfg)

    frame = grab_screen()
    weight_roi = cfg.get("weight_roi")
    if weight_roi:
        weights = read_inventory_weight(
            frame,
            weight_roi,
            weight_max_kg=float(cfg.get("weight_max_kg", 80.0)),
        )
        if weights:
            stash_log(f"[stash] Peso: {weights[0]:.1f} / {weights[1]:.1f} kg")

    transfers = scan_pocket_fish(frame, cfg, debug_ocr=debug_ocr)
    if not transfers:
        stash_log("[stash] Nenhum peixe para transferir nos Pockets")
        if not dry_run:
            close_inventory(cfg)
        return 0

    count = 0
    for item in transfers:
        if dry_run:
            count += 1
            continue
        drag_fish_transfer(cfg, item["pocket"], item["trunk"], item["species"])
        time.sleep(float(cfg.get("between_drag_ms", 150)) / 1000.0)
        count += 1

    if not dry_run:
        time.sleep(0.3)
        close_inventory(cfg)

    stash_log(f"[stash] Transferidos: {count}")
    return count


def _read_weight_with_fallback(cfg: dict, frame) -> tuple[tuple[float, float] | None, str | None]:
    weight_roi = cfg.get("weight_roi")
    weight_max_kg = float(cfg.get("weight_max_kg", 80.0))
    if not weight_roi:
        return None, None

    parsed, label = read_weight_from_frame(frame, weight_roi, weight_max_kg=weight_max_kg)
    if parsed:
        return parsed, label

    crop = crop_roi(frame, weight_roi)
    if crop.size == 0:
        return None, label

    for _ in range(3):
        parsed, label = read_weight_from_crop(crop, weight_max_kg=weight_max_kg)
        if parsed:
            return parsed, label

    return None, label


def maybe_stash_if_full(
    cfg: dict,
    *,
    startup_delay_sec: float | None = None,
    after_movement: bool = False,
    sct: Any | None = None,
) -> int:
    """Abre inventario, verifica peso; se cheio, transfere peixes. Retorna quantidade movida."""
    if not cfg.get("enabled", False):
        return 0

    errors = validate_inventory_calibration(cfg)
    if errors:
        for err in errors:
            stash_log(f"[stash] ERRO: {err}")
        return 0

    wait_startup_delay(cfg, override_sec=startup_delay_sec)

    tess_ok, tess_err = ensure_tesseract(force=True)
    if not tess_ok:
        stash_log(f"[stash] ERRO Tesseract: {tess_err}")
        return 0

    if after_movement:
        prepare_after_movement(cfg)

    open_inventory(cfg)
    extra_wait_ms = int(cfg.get("weight_read_wait_ms", 500))
    if extra_wait_ms > 0:
        time.sleep(extra_wait_ms / 1000.0)

    stash_log("[stash] Lendo peso...")
    frame, weights, ocr_raw = read_inventory_weight_retry(cfg)
    if weights is None:
        stash_log("[stash] OCR falhou — tentando recorte local...")
        frame = grab_screen()
        weights, ocr_raw = _read_weight_with_fallback(cfg, frame)

    if weights is None:
        _save_weight_debug_failure(frame, cfg, ocr_raw)
        ocr_err = weight_ocr_last_error()
        stash_log(
            f"[stash] AVISO: OCR nao leu peso (texto={ocr_raw!r}) — stash ignorado. "
            f"roi={cfg.get('weight_roi')}. ocr_err={ocr_err!r}. "
            "Veja stash-route/debug_ocr/weight_fail_*.png"
        )
        close_inventory(cfg)
        return 0

    current, maximum = weights
    limit = weight_stash_limit(cfg, maximum)
    stash_log(f"[stash] Peso: {current:.1f} / {maximum:.1f} kg (stash se >= {limit:.1f})")

    if current < limit:
        stash_log("[stash] Inventario com espaco — stash ignorado")
        close_inventory(cfg)
        return 0

    stash_log("[stash] Inventario cheio — transferindo peixes para o trunk")
    transfers = scan_pocket_fish(frame, cfg)
    if not transfers:
        stash_log("[stash] Nenhum peixe nos Pockets para transferir")
        close_inventory(cfg)
        return 0

    count = 0
    for item in transfers:
        drag_fish_transfer(cfg, item["pocket"], item["trunk"], item["species"])
        time.sleep(float(cfg.get("between_drag_ms", 150)) / 1000.0)
        count += 1

    time.sleep(0.3)
    close_inventory(cfg)
    stash_log(f"[stash] Transferidos: {count}")
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stash de peixes via inventario")
    parser.add_argument("--dry-run", action="store_true", help="So OCR, sem teclas/mouse")
    parser.add_argument("--stash", action="store_true", help="Executa stash completo")
    parser.add_argument(
        "--delay",
        type=float,
        metavar="SEC",
        help="Segundos de espera antes de teclas/mouse (padrao: startup_delay_ms no config)",
    )
    parser.add_argument("--drag", nargs=2, metavar=("POCKET_IDX", "SPECIES"))
    parser.add_argument("--check-weight", action="store_true", help="So le peso na tela")
    parser.add_argument(
        "--debug-ocr",
        action="store_true",
        help="Salva recortes OCR em stash-route/debug_ocr/",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    cfg = dict(config.get("stash_inventory", {}))

    stash_log(__doc__.strip())

    if args.check_weight or args.dry_run or args.stash or args.drag:
        pass
    else:
        stash_log("[stash] Use --dry-run, --stash, --drag ou --check-weight")
        close_stash_log()
        return

    if args.check_weight:
        frame = grab_screen()
        weight_roi = cfg.get("weight_roi", {})
        weights = read_inventory_weight(
            frame,
            weight_roi,
            weight_max_kg=float(cfg.get("weight_max_kg", 80.0)),
            debug=args.debug_ocr,
        )
        full = inventory_is_full(frame, cfg)
        ocr_raw = read_weight_text_ocr(frame, weight_roi) if args.debug_ocr and weight_roi else None
        stash_log(f"[stash] Peso: {weights} | cheio={full}")
        if ocr_raw is not None:
            stash_log(f"[stash] OCR peso bruto: {ocr_raw!r} | roi={weight_roi}")
        close_stash_log()
        return

    if args.drag:
        pocket_idx = int(args.drag[0])
        species = str(args.drag[1]).lower()
        errors = validate_inventory_calibration(cfg)
        if errors:
            for err in errors:
                stash_log(f"[stash] ERRO: {err}")
            close_stash_log()
            sys.exit(1)
        trunk_order = [str(s).lower() for s in cfg.get("trunk_species_order", [])]
        trunk_idx = trunk_index_for_species(species, trunk_order)
        if trunk_idx is None:
            stash_log(f"[stash] Especie desconhecida: {species}")
            close_stash_log()
            sys.exit(1)
        pockets = cfg.get("pocket_slots", [])
        trunks = cfg.get("trunk_slots", [])
        if pocket_idx >= len(pockets) or trunk_idx >= len(trunks):
            stash_log("[stash] Indice fora da calibracao")
            close_stash_log()
            sys.exit(1)
        wait_startup_delay(cfg, override_sec=args.delay)
        open_inventory(cfg)
        drag_fish_transfer(cfg, pockets[pocket_idx], trunks[trunk_idx], species)
        close_inventory(cfg)
        close_stash_log()
        return

    stash_all_fish(
        cfg,
        dry_run=args.dry_run,
        debug_ocr=args.debug_ocr,
        startup_delay_sec=args.delay,
    )
    close_stash_log()


if __name__ == "__main__":
    main()
