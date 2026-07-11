"""
Calibra slots do inventario (Pockets + Trunk + peso).

Uso:
  1. No jogo: carro ao lado, pressione I para abrir inventario
  2. Rode: python stash-route/calibrate_inventory.py
  3. Clique no CENTRO de cada slot na ordem indicada
  4. S = salvar config.json | Q = sair

Controles:
  CLIQUE ESQUERDO  - marca o slot atual
  N / P            - proximo / anterior slot
  TAB              - pula direto para calibrar peso (2 cliques no texto "80.0 / 80 KG")
  S                - salvar
  Q / ESC          - sair
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import mss
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
STASH_ROUTE_DIR = Path(__file__).resolve().parent
for path in (ROOT, STASH_ROUTE_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from config_loader import load_config, save_config
from inventory_utils import DEFAULT_LABEL_OFFSET, label_roi_for_slot


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def build_steps(trunk_order: list[str]) -> list[dict]:
    steps: list[dict] = []
    for index in range(6):
        steps.append({"kind": "pocket", "index": index, "label": f"Pocket {index + 1} (posicao)"})
    for index, species in enumerate(trunk_order[:6]):
        steps.append(
            {
                "kind": "trunk",
                "index": index,
                "species": species,
                "label": f"Trunk {species}",
            }
        )
    steps.append({"kind": "weight_tl", "label": "Peso (canto sup-esq)"})
    steps.append({"kind": "weight_br", "label": "Peso (canto inf-dir)"})
    return steps


def main() -> None:
    config = load_config()
    inv_cfg = dict(config.get("stash_inventory", {}))
    trunk_order = list(inv_cfg.get("trunk_species_order", ["perch", "carp", "trout", "salmon"]))
    steps = build_steps(trunk_order)

    pocket_slots = [dict(slot) for slot in inv_cfg.get("pocket_slots", [])]
    trunk_slots = [dict(slot) for slot in inv_cfg.get("trunk_slots", [])]
    weight_roi = dict(inv_cfg.get("weight_roi", {})) if inv_cfg.get("weight_roi") else None
    weight_points: list[tuple[int, int]] = []

    step_idx = 0
    last_frame: np.ndarray | None = None

    print(__doc__)

    def current_step() -> dict:
        return steps[step_idx]

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        nonlocal pocket_slots, trunk_slots, weight_roi, weight_points, step_idx
        if event != cv2.EVENT_LBUTTONDOWN or last_frame is None:
            return

        step = current_step()
        kind = step["kind"]
        print(f"[click] {step['label']} -> ({x}, {y})")

        if kind == "pocket":
            index = int(step["index"])
            while len(pocket_slots) <= index:
                pocket_slots.append({"index": len(pocket_slots), "x": 0, "y": 0})
            pocket_slots[index] = {"index": index, "x": x, "y": y}
        elif kind == "trunk":
            index = int(step["index"])
            species = str(step["species"])
            while len(trunk_slots) <= index:
                trunk_slots.append({"index": len(trunk_slots), "species": "", "x": 0, "y": 0})
            trunk_slots[index] = {"index": index, "species": species, "x": x, "y": y}
        elif kind in {"weight_tl", "weight_br"}:
            weight_points.append((x, y))
            if len(weight_points) >= 2:
                xs = [p[0] for p in weight_points]
                ys = [p[1] for p in weight_points]
                weight_roi = {
                    "left": min(xs),
                    "top": min(ys),
                    "width": max(xs) - min(xs),
                    "height": max(ys) - min(ys),
                }
                print(f"[weight] ROI = {weight_roi}")

    cv2.namedWindow("Inventory Calibration", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Inventory Calibration", on_mouse)

    with mss.MSS() as sct:
        monitor = sct.monitors[1]
        while True:
            frame = np.array(sct.grab(monitor))[:, :, :3]
            last_frame = frame
            overlay = frame.copy()

            for slot in pocket_slots:
                if slot.get("x") and slot.get("y"):
                    cv2.circle(overlay, (int(slot["x"]), int(slot["y"])), 10, (0, 255, 255), 2)
                    roi = label_roi_for_slot(slot, DEFAULT_LABEL_OFFSET)
                    cv2.rectangle(
                        overlay,
                        (roi["left"], roi["top"]),
                        (roi["left"] + roi["width"], roi["top"] + roi["height"]),
                        (0, 255, 255),
                        1,
                    )

            for slot in trunk_slots:
                if slot.get("x") and slot.get("y"):
                    cv2.circle(overlay, (int(slot["x"]), int(slot["y"])), 10, (255, 128, 0), 2)
                    label = slot.get("species", "?")
                    cv2.putText(
                        overlay,
                        label[:6],
                        (int(slot["x"]) - 20, int(slot["y"]) - 14),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 128, 0),
                        1,
                        cv2.LINE_AA,
                    )

            if weight_roi:
                cv2.rectangle(
                    overlay,
                    (int(weight_roi["left"]), int(weight_roi["top"])),
                    (
                        int(weight_roi["left"]) + int(weight_roi["width"]),
                        int(weight_roi["top"]) + int(weight_roi["height"]),
                    ),
                    (0, 255, 0),
                    2,
                )

            step = current_step()
            cv2.putText(
                overlay,
                f"Passo {step_idx + 1}/{len(steps)}: {step['label']}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                overlay,
                "Clique=marca | N/P=passo | TAB=peso | S=salvar | Q=sair",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                overlay,
                "Amarelo: circulo=arrastar | retangulo=OCR do nome do peixe",
                (20, 112),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )

            cv2.imshow("Inventory Calibration", overlay)
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("n"):
                step_idx = min(step_idx + 1, len(steps) - 1)
            if key == ord("p"):
                step_idx = max(step_idx - 1, 0)
            if key == 9:  # TAB
                step_idx = next(i for i, s in enumerate(steps) if s["kind"] == "weight_tl")
            if key == ord("s"):
                inv_cfg["pocket_slots"] = pocket_slots
                inv_cfg["trunk_slots"] = trunk_slots
                if weight_roi:
                    inv_cfg["weight_roi"] = weight_roi
                inv_cfg["label_offset"] = DEFAULT_LABEL_OFFSET
                config["stash_inventory"] = inv_cfg
                save_config(config)
                print("[save] stash_inventory salvo em config.json")
                break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
