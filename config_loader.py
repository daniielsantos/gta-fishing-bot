from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from detector import FishingDetector


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_config(config: dict[str, Any], path: Path | None = None) -> None:
    config_path = path or CONFIG_PATH
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")


def build_detector(config: dict[str, Any]) -> FishingDetector:
    control_cfg = config["control"]
    return FishingDetector(
        hsv_lower=config["hsv_blue"]["lower"],
        hsv_upper=config["hsv_blue"]["upper"],
        white_threshold=int(config.get("white_threshold", 200)),
        hook_white_threshold=int(config.get("hook_white_threshold", config.get("white_threshold", 210))),
        min_blue_pixels=int(control_cfg["min_blue_pixels"]),
        min_white_pixels=int(control_cfg["min_white_pixels"]),
        smoothing=float(control_cfg.get("smoothing", 0.45)),
        zone_smoothing=float(control_cfg.get("zone_smoothing", 0.2)),
        hook_smoothing=float(control_cfg.get("hook_smoothing", 0.45)),
        bar_strip_ratio=float(control_cfg.get("bar_strip_ratio", 0.42)),
        hook_area_min=int(control_cfg.get("hook_area_min", 25)),
        hook_area_max=int(control_cfg.get("hook_area_max", 1200)),
        blue_v_min=int(control_cfg.get("blue_v_min", 110)),
        blue_max_pixels=int(control_cfg.get("blue_max_pixels", 12000)),
        min_zone_width_px=float(control_cfg.get("min_zone_width_px", 60)),
        expected_zone_width_px=float(control_cfg.get("expected_zone_width_px", 220)),
        max_zone_jump_px=float(control_cfg.get("max_zone_jump_px", 180)),
        hook_band_top_ratio=float(control_cfg.get("hook_band_top_ratio", 0.44)),
        hook_band_bottom_ratio=float(control_cfg.get("hook_band_bottom_ratio", 0.74)),
        hook_max_width_px=float(control_cfg.get("hook_max_width_px", 48)),
        hook_max_height_px=float(control_cfg.get("hook_max_height_px", 58)),
        hook_min_aspect=float(control_cfg.get("hook_min_aspect", 0.75)),
        hook_max_aspect=float(control_cfg.get("hook_max_aspect", 3.5)),
        hook_shape_min_height_px=float(control_cfg.get("hook_shape_min_height_px", 10)),
        hook_shape_max_width_px=float(control_cfg.get("hook_shape_max_width_px", 22)),
        hook_shape_min_span_ratio=float(control_cfg.get("hook_shape_min_span_ratio", 0.38)),
        hook_noise_open_px=int(control_cfg.get("hook_noise_open_px", 3)),
        max_hook_jump_px=float(control_cfg.get("max_hook_jump_px", 140)),
        hook_search_radius_px=float(control_cfg.get("hook_search_radius_px", 100)),
        hook_v_min=int(control_cfg.get("hook_v_min", 200)),
        hook_s_max=int(control_cfg.get("hook_s_max", 70)),
        hook_shirt_merge_width=float(control_cfg.get("hook_shirt_merge_width", 26)),
        lost_grace_frames=int(control_cfg.get("lost_grace_frames", 25)),
        hook_search_margin_ratio=float(control_cfg.get("hook_search_margin_ratio", 0.14)),
        hook_search_min_height_ratio=float(control_cfg.get("hook_search_min_height_ratio", 0.09)),
        max_hook_band_pixels=int(control_cfg.get("max_hook_band_pixels", 130)),
        bar_margin_left_px=float(control_cfg.get("bar_margin_left_px", 35)),
        bar_margin_right_px=float(control_cfg.get("bar_margin_right_px", 95)),
    )
