"""

Bot de pesca automatica para minigame estilo barra horizontal.



Controles:

  F6  - liga/desliga o bot

  F9  - encerra o programa



Automacao:

  - Alterna teclas 1/2/3 (varas no atalho) ate o minigame iniciar

  - A cada N minigames, giro curto anti-afk (d -> s -> a -> w) antes de reiniciar



Requisitos:

  - GTA/FiveM em borderless ou janela (nao fullscreen exclusivo)

  - Resolucao 2560x1440 (ajuste config.json se diferente)

  - Rode calibrate.py antes para alinhar a ROI

  - Deixe o jogo em foco (janela ativa) ao usar F6

"""



from __future__ import annotations



import random

import sys

import time

from dataclasses import dataclass

from pathlib import Path

import cv2
import mss

import numpy as np

from pynput import keyboard



from config_loader import build_detector, load_config

from bot_logger import bot_log, close_bot_log, init_bot_log

from controller import MouseController

from debug_recorder import DebugFrameRecorder

from keyboard_input import debug_key_info, tap_key


STASH_ROUTE_DIR = Path(__file__).resolve().parent / "stash-route"
if str(STASH_ROUTE_DIR) not in sys.path:
    sys.path.insert(0, str(STASH_ROUTE_DIR))

from stash_inventory import maybe_stash_if_full
from inventory_utils import ensure_tesseract





@dataclass

class RuntimeState:

    enabled: bool = False

    running: bool = True

    last_action: str = "idle"

    last_error: float | None = None

    frames: int = 0

    catches: int = 0

    minigames_since_anti_afk: int = 0

    next_start_at: float | None = None

    anti_afk_before_next: bool = False

    rod_key_index: int = 0

    awaiting_minigame: bool = False

    await_minigame_since: float | None = None

    rod_attempts_this_cycle: int = 0

    next_rod_key_at: float | None = None





def schedule_start(state: RuntimeState, delay_sec: float, reason: str, *, anti_afk_before: bool = False) -> None:

    state.next_start_at = time.perf_counter() + delay_sec

    state.anti_afk_before_next = anti_afk_before

    state.awaiting_minigame = False

    state.next_rod_key_at = None

    state.rod_attempts_this_cycle = 0

    bot_log(f"[auto] Inicio de pesca agendado em {delay_sec:.1f}s ({reason})")





def random_restart_delay(auto_cfg: dict) -> float:

    low = float(auto_cfg.get("restart_delay_min_sec", 8))

    high = float(auto_cfg.get("restart_delay_max_sec", 12))

    if low > high:

        low, high = high, low

    return random.uniform(low, high)





def run_anti_afk(
    state: RuntimeState,
    anti_afk_keys: list[str] | None,
    anti_afk_hold_ms: float,
    anti_afk_gap_ms: float = 500.0,
    anti_afk_hold_overrides: dict[str, float] | None = None,
    anti_afk_repeat_count: int = 1,
    anti_afk_repeat_gap_ms: float = 0.0,
) -> None:

    if not state.anti_afk_before_next or not anti_afk_keys:

        state.anti_afk_before_next = False

        return

    overrides = anti_afk_hold_overrides or {}
    repeats = max(1, int(anti_afk_repeat_count))
    keys_label = " -> ".join(anti_afk_keys)

    bot_log(f"[auto] >>> ANTI-AFK: {repeats}x giro ({keys_label})")

    for spin in range(repeats):
        if spin > 0:
            if anti_afk_repeat_gap_ms > 0:
                time.sleep(anti_afk_repeat_gap_ms / 1000.0)
            bot_log(f"[auto] ANTI-AFK: volta {spin + 1}/{repeats}")

        for idx, key in enumerate(anti_afk_keys):
            if idx > 0 and anti_afk_gap_ms > 0:
                time.sleep(anti_afk_gap_ms / 1000.0)
            hold_ms = float(overrides.get(key, anti_afk_hold_ms))
            bot_log(

                f"[auto] >>> ANTI-AFK: segurando '{key}' por {hold_ms / 1000:.1f}s "

                f"({debug_key_info(key)})"

            )

            tap_key(key, hold_ms=hold_ms, use_scancode=True)

            bot_log(f"[auto] <<< ANTI-AFK: '{key}' solta")

    state.anti_afk_before_next = False





def press_rod_key(
    state: RuntimeState,
    start_keys: list[str],
    *,
    detector=None,
    mouse=None,
) -> str:

    key = start_keys[state.rod_key_index]

    bot_log(f"[auto] >>> START: tecla '{key}' (slot {state.rod_key_index + 1}/{len(start_keys)})")

    if detector is not None and mouse is not None:
        reset_tracking(detector, mouse)

    tap_key(key, use_scancode=True)

    state.awaiting_minigame = True

    state.await_minigame_since = time.perf_counter()

    state.rod_attempts_this_cycle += 1

    state.next_rod_key_at = None

    return key





def begin_fishing_cycle(

    state: RuntimeState,

    start_keys: list[str],

    anti_afk_keys: list[str] | None,

    anti_afk_hold_ms: float,

    anti_afk_gap_ms: float,

    anti_afk_hold_overrides: dict[str, float] | None,

    anti_afk_repeat_count: int,

    anti_afk_repeat_gap_ms: float,

    detector,

    mouse,

    stash_cfg: dict | None = None,

    sct=None,

) -> None:

    state.next_start_at = None

    state.rod_attempts_this_cycle = 0

    will_anti_afk = bool(state.anti_afk_before_next and anti_afk_keys)

    run_anti_afk(
        state,
        anti_afk_keys,
        anti_afk_hold_ms,
        anti_afk_gap_ms,
        anti_afk_hold_overrides,
        anti_afk_repeat_count,
        anti_afk_repeat_gap_ms,
    )

    if (
        will_anti_afk
        and stash_cfg
        and stash_cfg.get("enabled")
        and stash_cfg.get("check_after_anti_afk", True)
    ):
        bot_log("[stash] Checando peso apos anti-afk...")
        moved = maybe_stash_if_full(
            stash_cfg,
            startup_delay_sec=0,
            after_movement=True,
            sct=sct,
        )
        if moved:
            bot_log(f"[stash] Stash automatico: {moved} transferencia(s)")
    elif will_anti_afk and stash_cfg and not stash_cfg.get("enabled"):
        bot_log("[stash] Stash automatico desligado (stash_inventory.enabled=false)")

    press_rod_key(state, start_keys, detector=detector, mouse=mouse)





def advance_rod_key(state: RuntimeState, start_keys: list[str], *, detector=None, mouse=None) -> None:

    state.rod_key_index = (state.rod_key_index + 1) % len(start_keys)

    press_rod_key(state, start_keys, detector=detector, mouse=mouse)





def is_plausible_minigame(result, roi_width: int) -> bool:
    if not result.active:
        return False
    if (
        result.blue_left is None
        or result.blue_right is None
        or result.x_hook is None
        or result.error is None
    ):
        return False

    zone_width = result.blue_right - result.blue_left
    if zone_width < 80:
        return False
    if result.blue_left < roi_width * 0.18:
        return False
    if result.blue_right > roi_width * 0.98:
        return False
    if result.white_pixels < 10:
        return False
    if result.blue_pixels < 2000:
        return False
    return True


def reset_tracking(detector, mouse) -> None:
    detector.reset()
    mouse.stop()


def minigame_detected_now(result, minigame_active: bool, roi_width: int) -> bool:
    return is_plausible_minigame(result, roi_width) and not minigame_active





def handle_rod_probe(

    state: RuntimeState,

    start_keys: list[str],

    result,

    minigame_active: bool,

    auto_cfg: dict,

    roi_width: int,

    detector,

    mouse,

) -> None:

    if not state.awaiting_minigame:

        return



    if minigame_detected_now(result, minigame_active, roi_width):

        key = start_keys[state.rod_key_index]

        bot_log(f"[auto] Minigame iniciou com tecla '{key}'")

        state.awaiting_minigame = False

        state.rod_attempts_this_cycle = 0

        return



    now = time.perf_counter()

    if state.next_rod_key_at is not None and now >= state.next_rod_key_at:

        advance_rod_key(state, start_keys, detector=detector, mouse=mouse)

        return



    timeout = float(auto_cfg.get("rod_detect_timeout_sec", 4))

    if state.await_minigame_since is None or now - state.await_minigame_since < timeout:

        return



    failed_key = start_keys[state.rod_key_index]

    bot_log(f"[auto] Tecla '{failed_key}' nao iniciou minigame em {timeout:.0f}s")



    if state.rod_attempts_this_cycle >= len(start_keys):

        retry_delay = float(auto_cfg.get("rod_all_failed_delay_sec", 5))

        bot_log(f"[auto] Nenhuma vara respondeu ({start_keys}). Nova tentativa em {retry_delay:.0f}s")

        state.awaiting_minigame = False

        state.rod_key_index = 0

        state.rod_attempts_this_cycle = 0

        reset_tracking(detector, mouse)

        schedule_start(state, retry_delay, "nenhuma vara funcionou")

        return



    retry_gap = float(auto_cfg.get("rod_retry_gap_sec", 0.8))

    state.rod_key_index = (state.rod_key_index + 1) % len(start_keys)

    state.await_minigame_since = None

    state.next_rod_key_at = now + retry_gap

    next_key = start_keys[state.rod_key_index]

    bot_log(f"[auto] Proxima vara '{next_key}' em {retry_gap:.1f}s")





def main() -> None:

    log_path = init_bot_log()

    config = load_config()

    roi = dict(config["roi"])

    control_cfg = config["control"]

    auto_cfg = config.get("automation", {})

    stash_cfg = dict(config.get("stash_inventory", {}))



    auto_start = bool(auto_cfg.get("enabled", True))

    start_keys = [str(k) for k in auto_cfg.get("start_keys", ["1", "2", "3"])]

    if auto_cfg.get("anti_afk_enabled", True):
        raw_keys = auto_cfg.get("anti_afk_keys")
        if raw_keys:
            anti_afk_keys = [str(k) for k in raw_keys]
        else:
            anti_afk_keys = [str(auto_cfg.get("anti_afk_key", "w"))]
    else:
        anti_afk_keys = None

    anti_afk_hold_ms = float(auto_cfg.get("anti_afk_hold_ms", 150))

    anti_afk_gap_ms = float(auto_cfg.get("anti_afk_gap_ms", 0))

    raw_overrides = auto_cfg.get("anti_afk_hold_overrides", {})
    anti_afk_hold_overrides = {str(k): float(v) for k, v in raw_overrides.items()} if raw_overrides else None

    anti_afk_repeat_count = int(auto_cfg.get("anti_afk_repeat_count", 1))

    anti_afk_repeat_gap_ms = float(auto_cfg.get("anti_afk_repeat_gap_ms", 0))

    anti_afk_every_n = int(auto_cfg.get("anti_afk_every_n_minigames", 10))

    initial_delay_sec = float(auto_cfg.get("initial_delay_sec", 1))



    detector = build_detector(config)

    mouse = MouseController(
        deadband_px=float(control_cfg.get("control_deadband_px", 5)),
    )

    debug_overlay = bool(control_cfg.get("debug_overlay", False))

    debug_record_frames = bool(control_cfg.get("debug_record_frames", False))

    debug_recorder: DebugFrameRecorder | None = None

    if debug_record_frames:
        frames_dir = Path(__file__).resolve().parent / "debug_frames"
        debug_recorder = DebugFrameRecorder(
            frames_dir,
            fps=float(control_cfg.get("debug_record_fps", 5)),
            max_frames=int(control_cfg.get("debug_record_max_frames", 5000)),
            save_on_action_change=bool(control_cfg.get("debug_record_on_action_change", True)),
            only_minigame=bool(control_cfg.get("debug_record_only_minigame", True)),
        )
        bot_log(f"[debug] Gravacao de frames habilitada -> {frames_dir}")

    state = RuntimeState()



    toggle_key = keyboard.Key[config["hotkeys"]["toggle_bot"]]

    quit_key = keyboard.Key[config["hotkeys"]["quit"]]

    inactive_frames_to_end = int(control_cfg.get("inactive_frames_to_end", 45))
    track_grace_frames = int(control_cfg.get("track_grace_frames", 18))



    def on_press(key: keyboard.Key | keyboard.KeyCode) -> None:

        if key == toggle_key:

            state.enabled = not state.enabled

            status = "LIGADO" if state.enabled else "DESLIGADO"

            bot_log(f"[bot] {status}")

            if state.enabled:

                reset_tracking(detector, mouse)

                if auto_start:

                    schedule_start(state, initial_delay_sec, "bot ligado")

            else:

                state.next_start_at = None

                state.anti_afk_before_next = False

                state.minigames_since_anti_afk = 0

                state.awaiting_minigame = False

                state.next_rod_key_at = None

                reset_tracking(detector, mouse)

                if debug_recorder is not None and debug_recorder.active:
                    session, count = debug_recorder.end_session()
                    if session is not None:
                        bot_log(f"[debug] Gravacao encerrada: {count} frames em {session}")

        elif key == quit_key:

            state.running = False

            state.next_start_at = None

            mouse.stop()



    listener = keyboard.Listener(on_press=on_press)

    listener.start()



    target_dt = 1.0 / float(control_cfg["capture_fps"])

    minigame_active = False

    inactive_streak = 0
    last_logged_action = "idle"
    last_good_result = None
    track_miss_streak = 0
    fps_ema = 0.0



    bot_log(__doc__)

    bot_log(f"[bot] Varas nos atalhos: {start_keys}. Pressione F6 para ligar.")
    if stash_cfg.get("enabled"):
        bot_log(
            "[stash] Stash automatico LIGADO — checa peso apos anti-afk "
            f"(a cada {anti_afk_every_n} minigames)"
        )
        tess_ok, tess_err = ensure_tesseract(force=True)
        if tess_ok:
            bot_log("[stash] OCR de peso: OK")
        else:
            bot_log(f"[stash] AVISO: {tess_err}")
            bot_log(
                "[stash] Rode o bot com: .venv\\Scripts\\python.exe fishing_bot.py "
                "e instale: .venv\\Scripts\\pip.exe install -r requirements.txt"
            )

    bot_log(f"[bot] Log em arquivo: {log_path}")



    with mss.MSS() as sct:

        while state.running:

            loop_start = time.perf_counter()



            if (

                state.enabled

                and auto_start

                and state.next_start_at is not None

                and loop_start >= state.next_start_at

            ):

                begin_fishing_cycle(
                    state,
                    start_keys,
                    anti_afk_keys,
                    anti_afk_hold_ms,
                    anti_afk_gap_ms,
                    anti_afk_hold_overrides,
                    anti_afk_repeat_count,
                    anti_afk_repeat_gap_ms,
                    detector,
                    mouse,
                    stash_cfg,
                    sct,
                )



            frame = np.array(sct.grab(roi))[:, :, :3]

            result = detector.detect(frame)

            state.frames += 1

            roi_width = int(roi["width"])

            plausible = is_plausible_minigame(result, roi_width)

            if state.awaiting_minigame:
                minigame_active = False
                inactive_streak = 0
                state.last_error = None
                if mouse.holding:
                    mouse.stop()
                    state.last_action = "idle"

            handle_rod_probe(
                state, start_keys, result, minigame_active, auto_cfg, roi_width, detector, mouse
            )



            if plausible or result.active or result.blue_pixels > 1500:

                inactive_streak = 0

                if not minigame_active:

                    minigame_active = True

                    state.awaiting_minigame = False

                    bot_log("[bot] Minigame detectado.")

            elif minigame_active:

                inactive_streak += 1

                if inactive_streak >= inactive_frames_to_end:

                    minigame_active = False

                    inactive_streak = 0

                    state.catches += 1

                    mouse.stop()
                    state.last_error = None

                    detector.reset()

                    bot_log(f"[bot] Minigame finalizado (#{state.catches}).")

                    if state.enabled and auto_start:

                        state.minigames_since_anti_afk += 1

                        use_anti_afk = (

                            anti_afk_keys is not None

                            and state.minigames_since_anti_afk >= anti_afk_every_n

                        )

                        if use_anti_afk:

                            state.minigames_since_anti_afk = 0

                            keys_label = "->".join(anti_afk_keys)

                            bot_log(
                                f"[auto] Anti-afk: {anti_afk_repeat_count}x giro {keys_label} "
                                f"apos {anti_afk_every_n} minigames"
                            )

                        schedule_start(

                            state,

                            random_restart_delay(auto_cfg),

                            "minigame finalizado",

                            anti_afk_before=use_anti_afk,

                        )



            control_active = (
                state.enabled
                and minigame_active
                and not state.awaiting_minigame
            )

            ctrl = result if result.active else last_good_result
            if result.active:
                last_good_result = result
                track_miss_streak = 0
            elif last_good_result is not None:
                track_miss_streak += 1
                if track_miss_streak > track_grace_frames:
                    last_good_result = None

            if control_active and ctrl is not None and ctrl.active:
                state.last_action = mouse.update(ctrl)
                state.last_error = (
                    ctrl.error_control if ctrl.error_control is not None else ctrl.error
                )
            elif control_active and last_good_result is not None and last_good_result.active:
                state.last_action = mouse.update(last_good_result)
                state.last_error = (
                    last_good_result.error_control
                    if last_good_result.error_control is not None
                    else last_good_result.error
                )
            elif control_active:
                state.last_action = mouse.pause()
            elif not minigame_active and mouse.holding:
                mouse.stop()
                state.last_action = "idle"
                state.last_error = None
                last_good_result = None
                track_miss_streak = 0
            elif not minigame_active or state.awaiting_minigame:
                state.last_error = None
                last_good_result = None
                track_miss_streak = 0



            if control_active and state.last_action != last_logged_action:
                ctrl = ctrl if ctrl is not None else result
                err = "-" if state.last_error is None else f"{state.last_error:.1f}"
                hook = "-" if ctrl.x_hook_control is None else f"{ctrl.x_hook_control:.1f}"
                if hook == "-" and ctrl.x_hook is not None:
                    hook = f"{ctrl.x_hook:.1f}"
                left = "-" if ctrl.blue_left_control is None else f"{ctrl.blue_left_control:.1f}"
                if left == "-" and ctrl.blue_left is not None:
                    left = f"{ctrl.blue_left:.1f}"
                right = "-" if ctrl.blue_right_control is None else f"{ctrl.blue_right_control:.1f}"
                if right == "-" and ctrl.blue_right is not None:
                    right = f"{ctrl.blue_right:.1f}"
                width = "-" if ctrl.zone_width is None else f"{ctrl.zone_width:.1f}"

                bot_log(

                    f"[acao] {state.last_action} | erro={err} | "

                    f"anzol={hook} zona=[{left},{right}] w={width} | holding={mouse.holding}"

                )

                last_logged_action = state.last_action



            if not state.enabled:

                last_logged_action = "idle"



            if state.frames % 120 == 0 or (state.enabled and not result.active and state.frames % 30 == 0):

                err = "-" if state.last_error is None else f"{state.last_error:.1f}"

                rod = start_keys[state.rod_key_index] if start_keys else "-"

                bot_log(

                    f"[status] enabled={state.enabled} active={plausible} "

                    f"awaiting={state.awaiting_minigame} rod={rod} "

                    f"action={state.last_action} error={err} holding={mouse.holding} "

                    f"azul_px={result.blue_pixels} branco_px={result.white_pixels}"

                )



            if debug_overlay and state.enabled:
                overlay = detector.debug_frame(frame)
                status = "ATIVO" if result.active else "inativo"
                err_txt = (
                    f"{result.error_control:.1f}"
                    if result.error_control is not None
                    else (f"{result.error:.1f}" if result.error is not None else "-")
                )
                hook_txt = (
                    f"{result.x_hook_control:.0f}"
                    if result.x_hook_control is not None
                    else (f"{result.x_hook:.0f}" if result.x_hook is not None else "-")
                )
                zone_txt = (
                    f"{result.zone_center_control:.0f}"
                    if result.zone_center_control is not None
                    else (
                        f"{(result.blue_left_control + result.blue_right_control) / 2:.0f}"
                        if result.blue_left_control is not None
                        and result.blue_right_control is not None
                        else (f"{result.x_blue:.0f}" if result.x_blue is not None else "-")
                    )
                )
                lines = [
                    f"{status} | acao={state.last_action} holding={mouse.holding}",
                    f"anzol={hook_txt} zona={zone_txt} erro={err_txt}",
                    f"fps~{fps_ema:.0f} | plausivel={plausible} minigame={minigame_active}",
                ]
                for idx, line in enumerate(lines):
                    cv2.putText(
                        overlay,
                        line,
                        (8, 16 + idx * 16),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        (0, 255, 0),
                        1,
                        cv2.LINE_AA,
                    )
                if result.blue_left_control is not None and result.blue_right_control is not None:
                    zone_left = result.blue_left_control
                    zone_right = result.blue_right_control
                elif result.blue_left is not None and result.blue_right is not None:
                    zone_left = result.blue_left
                    zone_right = result.blue_right
                else:
                    zone_left, zone_right = detector.peek_zone_bounds(frame)
                bar_top = 0
                if overlay.shape[0] > 100:
                    bar_top = int(overlay.shape[0] * (1.0 - float(control_cfg.get("bar_strip_ratio", 1.0))))
                vis_left = result.blue_left_vision
                vis_right = result.blue_right_vision
                vis_center = result.zone_center_vision
                if vis_left is None or vis_right is None:
                    vis_left, vis_right = detector.peek_zone_bounds(frame)
                    vis_center = None
                ctrl_center = result.zone_center_control
                detector.draw_vision_zone_overlay(
                    overlay, vis_left, vis_right, bar_top, center=vis_center
                )
                detector.draw_zone_overlay(
                    overlay, zone_left, zone_right, bar_top, center=ctrl_center
                )
                hook_draw = result.x_hook_control or result.x_hook
                if hook_draw is None:
                    hook_draw = detector.peek_hook_x(frame)
                if hook_draw is not None:
                    cv2.line(
                        overlay,
                        (int(hook_draw), 0),
                        (int(hook_draw), overlay.shape[0] - 1),
                        (255, 255, 255),
                        2,
                    )
                cv2.imshow("Bot Debug (mesma visao da calibracao)", overlay)
                cv2.waitKey(1)

                if debug_recorder is not None:
                    record_minigame = minigame_active or control_active or plausible
                    if debug_recorder.should_record(state.enabled, record_minigame):
                        if not debug_recorder.active:
                            session = debug_recorder.start_session()
                            bot_log(f"[debug] Nova sessao de frames: {session}")
                        hook_num = result.x_hook_control or result.x_hook
                        zone_num = result.zone_center_control
                        if zone_num is None and (
                            result.blue_left_control is not None
                            and result.blue_right_control is not None
                        ):
                            zone_num = (result.blue_left_control + result.blue_right_control) / 2.0
                        elif zone_num is None:
                            zone_num = result.x_blue
                        debug_recorder.maybe_save(
                            overlay,
                            action=state.last_action,
                            error=state.last_error,
                            hook_x=hook_num,
                            zone_x=zone_num,
                            active=result.active,
                        )
                    elif debug_recorder.active:
                        session, count = debug_recorder.end_session()
                        if session is not None:
                            bot_log(f"[debug] Sessao pausada: {count} frames em {session}")

            dt = max(time.perf_counter() - loop_start, 1e-6)
            fps_ema = fps_ema * 0.9 + (1.0 / dt) * 0.1

            elapsed = time.perf_counter() - loop_start

            sleep_time = target_dt - elapsed

            if sleep_time > 0:

                time.sleep(sleep_time)



    listener.stop()

    mouse.stop()
    if debug_recorder is not None and debug_recorder.active:
        session, count = debug_recorder.end_session()
        if session is not None:
            bot_log(f"[debug] Gravacao finalizada: {count} frames em {session}")
    if debug_overlay:
        cv2.destroyAllWindows()

    bot_log("[bot] Encerrado.")

    close_bot_log()





if __name__ == "__main__":

    main()
