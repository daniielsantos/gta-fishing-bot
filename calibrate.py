"""
Calibra a regiao da barra de pesca e as cores HSV.

Controles:
  Setas / IJKL     - move a ROI
  W / X / A / D    - tamanho da ROI
  [ / ]            - H minimo (lower H)
  9 / 0            - H maximo (upper H)
  ; / '            - S minimo
  , / .            - V minimo (brilho)
  - / =            - threshold do anzol (hook_white_threshold)
  t / g            - linha amarela de cima (faixa do anzol)
  h / b            - linha amarela de baixo (faixa do anzol)
  CLIQUE ESQUERDO  - clique na zona azul para auto-calibrar HSV
  S                - salva config.json
  Q / ESC          - sair

Objetivo: painel esquerdo = overlay | meio = zona azul | direita = anzol (branco).
          Linhas amarelas = faixa onde o anzol e procurado (ignora texto de cima).
          azul_px > 0 e status ATIVO antes de salvar.
"""

from __future__ import annotations

import time

import cv2
import mss
import numpy as np

from config_loader import build_detector, load_config, save_config


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def blue_mask_for(frame_bgr: np.ndarray, hsv_lower: list[int], hsv_upper: list[int]) -> np.ndarray:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    lower = np.array(hsv_lower, dtype=np.uint8)
    upper = np.array(hsv_upper, dtype=np.uint8)
    return cv2.inRange(hsv, lower, upper)


def pick_hsv_from_pixel(frame_bgr: np.ndarray, x: int, y: int) -> tuple[list[int], list[int]]:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = [int(c) for c in hsv[y, x]]
    lower = [clamp(h - 12, 0, 179), clamp(s - 50, 20, 255), clamp(v - 70, 40, 255)]
    upper = [clamp(h + 12, 0, 179), 255, 255]
    return lower, upper


def main() -> None:
    config = load_config()
    roi = dict(config["roi"])
    hsv_lower = list(config["hsv_blue"]["lower"])
    hsv_upper = list(config["hsv_blue"]["upper"])
    white_threshold = int(config.get("white_threshold", 200))
    hook_white_threshold = int(config.get("hook_white_threshold", white_threshold))
    hook_band_top = float(config["control"].get("hook_band_top_ratio", 0.44))
    hook_band_bottom = float(config["control"].get("hook_band_bottom_ratio", 0.74))
    last_frame = None

    print(__doc__)

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        nonlocal hsv_lower, hsv_upper, last_frame
        if event != cv2.EVENT_LBUTTONDOWN or last_frame is None:
            return
        panel_width = last_frame.shape[1]
        if x >= panel_width:
            return
        local_x = int(x * last_frame.shape[1] / panel_width)
        local_y = int(y * last_frame.shape[0] / max(last_frame.shape[0], 1))
        local_x = clamp(local_x, 0, last_frame.shape[1] - 1)
        local_y = clamp(local_y, 0, last_frame.shape[0] - 1)
        hsv_lower, hsv_upper = pick_hsv_from_pixel(last_frame, local_x, local_y)
        print(f"[pick] HSV lower={hsv_lower} upper={hsv_upper}")

    cv2.namedWindow("Fishing Calibration")
    cv2.setMouseCallback("Fishing Calibration", on_mouse)

    detector = build_detector(config)

    fps_ema = 0.0
    fps_last = time.perf_counter()

    with mss.MSS() as sct:
        while True:
            loop_start = time.perf_counter()
            frame = np.array(sct.grab(roi))[:, :, :3]
            last_frame = frame

            config["hsv_blue"]["lower"] = hsv_lower
            config["hsv_blue"]["upper"] = hsv_upper
            config["white_threshold"] = white_threshold
            config["hook_white_threshold"] = hook_white_threshold
            config["control"]["hook_band_top_ratio"] = hook_band_top
            config["control"]["hook_band_bottom_ratio"] = hook_band_bottom

            detector.hsv_lower = np.array(hsv_lower, dtype=np.uint8)
            detector.hsv_upper = np.array(hsv_upper, dtype=np.uint8)
            detector.white_threshold = white_threshold
            detector.hook_white_threshold = hook_white_threshold
            detector.hook_band_top_ratio = hook_band_top
            detector.hook_band_bottom_ratio = hook_band_bottom

            result = detector.detect(frame)
            debug = detector.debug_frame(frame)

            mask = detector.blue_mask_for_debug(frame)
            hook_mask = detector.hook_mask_for_debug(frame)
            blue_view = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
            hook_view = cv2.cvtColor(hook_mask, cv2.COLOR_GRAY2BGR)

            status = "ATIVO" if result.active else "inativo"
            error_text = f"{result.error:.1f}" if result.error is not None else "-"
            hook_x = result.x_hook_control or result.x_hook
            if hook_x is None:
                hook_x = detector.peek_hook_x(frame)
            if hook_x is None:
                hook_x = detector._x_hook
            hook_text = f"{hook_x:.0f}" if hook_x is not None else "-"
            zone_left = result.blue_left_control if result.blue_left_control is not None else result.blue_left
            zone_right = result.blue_right_control if result.blue_right_control is not None else result.blue_right
            if zone_left is None or zone_right is None:
                zone_left, zone_right = detector.peek_zone_bounds(frame)
            if zone_left is None and detector._blue_left is not None:
                zone_left = detector._blue_left
                zone_right = detector._blue_right
            zone_x = result.x_blue if result.x_blue is not None else detector._x_blue
            if result.blue_left_control is not None and result.blue_right_control is not None:
                zone_x = result.zone_center_control
                if zone_x is None:
                    zone_x = (result.blue_left_control + result.blue_right_control) / 2.0
            elif result.blue_left is not None and result.blue_right is not None:
                zone_x = (result.blue_left + result.blue_right) / 2.0
            if zone_x is None and zone_left is not None and zone_right is not None:
                zone_x = (zone_left + zone_right) / 2.0
            blue_text = f"{zone_x:.0f}" if zone_x is not None else "-"
            if result.error_control is not None:
                error_text = f"{result.error_control:.1f}"
            elif (
                hook_x is not None
                and zone_left is not None
                and zone_right is not None
            ):
                center = result.zone_center_control
                if center is None:
                    center = (zone_left + zone_right) / 2.0
                error_text = f"{hook_x - center:.1f}"

            cv2.rectangle(debug, (0, 0), (debug.shape[1] - 1, debug.shape[0] - 1), (0, 255, 0), 2)
            bar_top = 0
            if debug.shape[0] > 100:
                bar_top = int(debug.shape[0] * (1.0 - detector.bar_strip_ratio))
            vis_left = result.blue_left_vision
            vis_right = result.blue_right_vision
            vis_center = result.zone_center_vision
            if vis_left is None or vis_right is None:
                vis_left, vis_right = detector.peek_zone_bounds(frame)
                vis_center = None
            ctrl_center = result.zone_center_control
            if ctrl_center is None and zone_left is not None and zone_right is not None:
                ctrl_center = (zone_left + zone_right) / 2.0
            if zone_x is None and ctrl_center is not None:
                zone_x = ctrl_center
            detector.draw_vision_zone_overlay(
                debug, vis_left, vis_right, bar_top, center=vis_center
            )
            detector.draw_zone_overlay(
                debug, zone_left, zone_right, bar_top, center=ctrl_center
            )
            if hook_x is not None:
                cv2.line(debug, (int(hook_x), 0), (int(hook_x), debug.shape[0] - 1), (255, 255, 255), 2)

            lines = [
                f"{status} | azul_px={result.blue_pixels} branco_px={result.white_pixels}",
                f"anzol={hook_text} zona={blue_text} erro={error_text}",
                f"fps~{fps_ema:.0f} (calibracao limitada pelo OpenCV)",
                f"faixa amarela = altura do anzol (t/g/h/b)",
                f"vermelho = cuidado bordas | verde = visao | ciano = controle",
                "Hook Mask = faixa de busca | S= salvar",
            ]
            for idx, line in enumerate(lines):
                cv2.putText(
                    debug,
                    line,
                    (8, 16 + idx * 16),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 255, 0),
                    1,
                    cv2.LINE_AA,
                )

            cv2.putText(
                blue_view,
                "Blue Mask",
                (8, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                hook_view,
                "Hook Mask (busca)",
                (8, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
                cv2.LINE_AA,
            )

            combined = np.hstack([debug, blue_view, hook_view])

            max_width = 1500
            if combined.shape[1] > max_width:
                scale = max_width / combined.shape[1]
                combined = cv2.resize(
                    combined,
                    (int(combined.shape[1] * scale), max(int(combined.shape[0] * scale), 80)),
                    interpolation=cv2.INTER_AREA,
                )
            cv2.imshow("Fishing Calibration", combined)

            dt = max(time.perf_counter() - loop_start, 1e-6)
            fps_ema = fps_ema * 0.9 + (1.0 / dt) * 0.1

            key = cv2.waitKeyEx(1)
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                config["roi"] = roi
                config["hsv_blue"]["lower"] = hsv_lower
                config["hsv_blue"]["upper"] = hsv_upper
                config["white_threshold"] = white_threshold
                config["hook_white_threshold"] = hook_white_threshold
                config["control"]["hook_band_top_ratio"] = hook_band_top
                config["control"]["hook_band_bottom_ratio"] = hook_band_bottom
                save_config(config)
                print("Config salva em config.json")

            step = 5

            if key in (2424832, 2, ord("j")):
                roi["left"] -= step
            elif key in (2555904, 3, ord("l")):
                roi["left"] += step
            elif key in (2490368, 0, ord("i")):
                roi["top"] -= step
            elif key in (2621440, 1, ord("k")):
                roi["top"] += step

            if key == ord("["):
                hsv_lower[0] = clamp(hsv_lower[0] - 1, 0, 179)
            elif key == ord("]"):
                hsv_lower[0] = clamp(hsv_lower[0] + 1, 0, 179)
            elif key == ord("9"):
                hsv_upper[0] = clamp(hsv_upper[0] - 1, 0, 179)
            elif key == ord("0"):
                hsv_upper[0] = clamp(hsv_upper[0] + 1, 0, 179)
            elif key == ord(";"):
                hsv_lower[1] = clamp(hsv_lower[1] - 5, 0, 255)
            elif key == ord("'"):
                hsv_lower[1] = clamp(hsv_lower[1] + 5, 0, 255)
            elif key == ord(","):
                hsv_lower[2] = clamp(hsv_lower[2] - 5, 0, 255)
            elif key == ord("."):
                hsv_lower[2] = clamp(hsv_lower[2] + 5, 0, 255)
            elif key == ord("-"):
                hook_white_threshold = clamp(hook_white_threshold - 5, 150, 255)
            elif key == ord("="):
                hook_white_threshold = clamp(hook_white_threshold + 5, 150, 255)

            band_step = 0.02
            if key == ord("t"):
                hook_band_top = max(0.0, round(hook_band_top - band_step, 2))
            elif key == ord("g"):
                hook_band_top = min(hook_band_bottom - 0.08, round(hook_band_top + band_step, 2))
            elif key == ord("h"):
                hook_band_bottom = max(hook_band_top + 0.08, round(hook_band_bottom - band_step, 2))
            elif key == ord("b"):
                hook_band_bottom = min(1.0, round(hook_band_bottom + band_step, 2))

            if key == ord("a"):
                roi["width"] = max(120, roi["width"] - step)
            elif key == ord("d"):
                roi["width"] += step
            elif key == ord("w"):
                roi["height"] = max(40, roi["height"] - step)
            elif key == ord("x"):
                roi["height"] += step

            time.sleep(0.005)

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
