from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class DetectionResult:
    active: bool
    x_hook: float | None
    x_blue: float | None
    blue_left: float | None
    blue_right: float | None
    error: float | None
    blue_pixels: int
    white_pixels: int
    zone_width: float | None = None
    x_hook_control: float | None = None
    blue_left_control: float | None = None
    blue_right_control: float | None = None
    error_control: float | None = None


class FishingDetector:
    def __init__(
        self,
        hsv_lower: list[int],
        hsv_upper: list[int],
        white_threshold: int = 200,
        min_blue_pixels: int = 80,
        min_white_pixels: int = 15,
        smoothing: float = 0.35,
        zone_smoothing: float = 0.2,
        hook_smoothing: float = 0.45,
        bar_strip_ratio: float = 0.42,
        hook_area_min: int = 25,
        hook_area_max: int = 1200,
        blue_v_min: int = 110,
        blue_max_pixels: int = 12000,
        min_zone_width_px: float = 60.0,
        expected_zone_width_px: float = 220.0,
        max_zone_jump_px: float = 180.0,
        hook_band_top_ratio: float = 0.44,
        hook_band_bottom_ratio: float = 0.74,
        hook_max_width_px: float = 48.0,
        hook_max_height_px: float = 58.0,
        hook_min_aspect: float = 0.75,
        hook_max_aspect: float = 3.5,
        hook_shape_min_height_px: float = 10.0,
        hook_shape_max_width_px: float = 22.0,
        hook_shape_min_span_ratio: float = 0.38,
        hook_noise_open_px: int = 3,
        max_hook_jump_px: float = 140.0,
        hook_search_radius_px: float = 100.0,
        hook_white_threshold: int = 210,
        hook_v_min: int = 200,
        hook_s_max: int = 70,
        hook_shirt_merge_width: float = 26.0,
        lost_grace_frames: int = 20,
        hook_search_margin_ratio: float = 0.14,
        hook_search_min_height_ratio: float = 0.09,
        max_hook_band_pixels: int = 130,
        bar_margin_left_px: float = 35.0,
        bar_margin_right_px: float = 95.0,
    ) -> None:
        self.hsv_lower = np.array(hsv_lower, dtype=np.uint8)
        self.hsv_upper = np.array(hsv_upper, dtype=np.uint8)
        self.white_threshold = white_threshold
        self.hook_white_threshold = hook_white_threshold
        self.hook_v_min = hook_v_min
        self.hook_s_max = hook_s_max
        self.hook_shirt_merge_width = hook_shirt_merge_width
        self.min_blue_pixels = min_blue_pixels
        self.min_white_pixels = min_white_pixels
        self.smoothing = smoothing
        self.zone_smoothing = zone_smoothing
        self.hook_smoothing = hook_smoothing
        self.bar_strip_ratio = bar_strip_ratio
        self.hook_area_min = hook_area_min
        self.hook_area_max = hook_area_max
        self.blue_v_min = blue_v_min
        self.blue_max_pixels = blue_max_pixels
        self.min_zone_width_px = min_zone_width_px
        self.expected_zone_width_px = expected_zone_width_px
        self.max_zone_jump_px = max_zone_jump_px
        self.hook_band_top_ratio = hook_band_top_ratio
        self.hook_band_bottom_ratio = hook_band_bottom_ratio
        self.hook_search_margin_ratio = hook_search_margin_ratio
        self.hook_search_min_height_ratio = hook_search_min_height_ratio
        self.hook_max_width_px = hook_max_width_px
        self.hook_max_height_px = hook_max_height_px
        self.hook_min_aspect = hook_min_aspect
        self.hook_max_aspect = hook_max_aspect
        self.hook_shape_min_height_px = hook_shape_min_height_px
        self.hook_shape_max_width_px = hook_shape_max_width_px
        self.hook_shape_min_span_ratio = hook_shape_min_span_ratio
        self.hook_noise_open_px = hook_noise_open_px
        self.max_hook_jump_px = max_hook_jump_px
        self.hook_search_radius_px = hook_search_radius_px
        self.lost_grace_frames = lost_grace_frames
        self.max_hook_band_pixels = max_hook_band_pixels
        self.bar_margin_left_px = bar_margin_left_px
        self.bar_margin_right_px = bar_margin_right_px

        self._x_hook: float | None = None
        self._x_blue: float | None = None
        self._blue_left: float | None = None
        self._blue_right: float | None = None
        self._reject_streak = 0
        self._lost_streak = 0
        self._blue_pixel_ema: float | None = None
        self._wrong_error_streak = 0
        self._ctrl_x_hook: float | None = None
        self._ctrl_blue_left: float | None = None
        self._ctrl_blue_right: float | None = None
        self._ctrl_error: float | None = None
        self._hook_stale_frames = 0

    def reset(self) -> None:
        self._x_hook = None
        self._x_blue = None
        self._blue_left = None
        self._blue_right = None
        self._reject_streak = 0
        self._lost_streak = 0
        self._blue_pixel_ema = None
        self._wrong_error_streak = 0
        self._ctrl_x_hook = None
        self._ctrl_blue_left = None
        self._ctrl_blue_right = None
        self._ctrl_error = None
        self._hook_stale_frames = 0

    def _smooth(self, previous: float | None, current: float | None, factor: float) -> float | None:
        if current is None:
            return previous
        if previous is None:
            return current
        return previous * (1.0 - factor) + current * factor

    def _bar_slice(self, frame_bgr: np.ndarray) -> tuple[np.ndarray, int]:
        height = frame_bgr.shape[0]
        if height <= 100:
            return frame_bgr, 0

        bar_top = int(height * (1.0 - self.bar_strip_ratio))
        return frame_bgr[bar_top:, :], bar_top

    def _bar_edge_limits(
        self,
        bar_width: int,
        prev_x: float | None = None,
    ) -> tuple[int, int]:
        left = max(0, int(self.bar_margin_left_px))
        right = max(left + 1, bar_width - max(0, int(self.bar_margin_right_px)))
        if prev_x is not None:
            slack = 18.0
            if prev_x < left + slack:
                left = 0
            if prev_x >= right - slack:
                right = bar_width
        return left, min(right, bar_width)

    def _strict_bar_edge_limits(self, bar_width: int) -> tuple[int, int]:
        left = max(0, int(self.bar_margin_left_px))
        right = max(left + 1, bar_width - max(0, int(self.bar_margin_right_px)))
        return left, min(right, bar_width)

    def _mask_bar_edges(self, mask: np.ndarray, prev_x: float | None = None) -> np.ndarray:
        if mask.size == 0 or prev_x is not None:
            return mask
        left, right = self._strict_bar_edge_limits(mask.shape[1])
        out = mask.copy()
        if left > 0:
            out[:, :left] = 0
        if right < mask.shape[1]:
            out[:, right:] = 0
        return out

    def _hook_in_edge_exclusion(self, cx: float, bar_width: int, prev_x: float | None) -> bool:
        if prev_x is not None:
            left, right = self._bar_edge_limits(bar_width, prev_x)
            if left <= cx < right:
                return False
            return abs(cx - prev_x) > self.max_hook_jump_px

        strict_left, strict_right = self._strict_bar_edge_limits(bar_width)
        return cx < strict_left or cx >= strict_right

    def _blue_mask(self, bar_bgr: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(bar_bgr, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.hsv_lower, self.hsv_upper)

        v_min = max(self.blue_v_min, int(self.hsv_lower[2]))
        bright = cv2.inRange(
            hsv,
            np.array([self.hsv_lower[0], self.hsv_lower[1], v_min], dtype=np.uint8),
            self.hsv_upper,
        )
        mask = cv2.bitwise_and(mask, bright)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    def _blue_mask_for_zone(self, bar_bgr: np.ndarray) -> np.ndarray:
        """Mascara azul com fechamento horizontal — une gaps das setas <- ->."""
        mask = self._blue_mask(bar_bgr)
        close_k = cv2.getStructuringElement(cv2.MORPH_RECT, (29, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_k)
        dilate_k = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 3))
        mask = cv2.dilate(mask, dilate_k, iterations=1)
        return mask

    def _zone_bounds_from_columns(
        self,
        blue_mask: np.ndarray,
    ) -> tuple[float | None, float | None, float | None, int]:
        height, width = blue_mask.shape[:2]
        if width <= 0 or height <= 0:
            return None, None, None, 0

        y0 = int(height * 0.32)
        y1 = max(y0 + 1, int(height * 0.92))
        strip = blue_mask[y0:y1, :]
        col_counts = np.count_nonzero(strip, axis=0).astype(np.float64)
        if col_counts.max() < 2.0:
            return None, None, None, int(col_counts.sum())

        row_span = max(1, strip.shape[0])
        threshold = max(2.0, row_span * 0.06)
        target_w = int(
            max(
                self.expected_zone_width_px * 1.05,
                self.min_zone_width_px * 2.5,
                180.0,
            )
        )
        target_w = min(target_w, width)

        runs: list[tuple[int, int, float]] = []
        in_run = False
        run_start = 0
        for x in range(width):
            if col_counts[x] >= threshold:
                if not in_run:
                    run_start = x
                    in_run = True
            elif in_run:
                run_end = x - 1
                strength = float(col_counts[run_start : run_end + 1].sum())
                runs.append((run_start, run_end, strength))
                in_run = False
        if in_run:
            run_end = width - 1
            strength = float(col_counts[run_start : run_end + 1].sum())
            runs.append((run_start, run_end, strength))

        if not runs:
            if target_w >= width:
                return None, None, None, int(col_counts.sum())
            window_sums = np.convolve(col_counts, np.ones(target_w, dtype=np.float64), mode="valid")
            if window_sums.size == 0 or window_sums.max() < threshold * 2.0:
                return None, None, None, int(col_counts.sum())
            best_x0 = int(window_sums.argmax())
            left = float(best_x0)
            right = float(best_x0 + target_w)
            center = (left + right) / 2.0
            return left, right, center, int(window_sums[best_x0])

        best: tuple[float, int, int, float] | None = None
        for run_left, run_right, strength in runs:
            run_w = run_right - run_left + 1
            if run_w < self.min_zone_width_px:
                continue
            width_penalty = abs(run_w - target_w) * 1.4
            if run_w > target_w * 1.45:
                width_penalty += (run_w - target_w * 1.45) * 2.5
            score = width_penalty - strength * 0.012
            if best is None or score < best[0]:
                best = (score, run_left, run_right, strength)

        if best is None:
            return None, None, None, int(col_counts.sum())

        _score, run_left, run_right, strength = best
        run_w = run_right - run_left + 1
        if run_w > target_w * 1.2:
            segment = col_counts[run_left : run_right + 1]
            half = target_w // 2
            center_idx = int(run_left + segment.argmax())
            left = float(max(0, center_idx - half))
            right = float(min(width, left + target_w))
            left = max(0.0, right - target_w)
        else:
            left = float(run_left)
            right = float(run_right + 1)

        center = (left + right) / 2.0
        return left, right, center, int(strength)

    def _largest_component_bounds(
        self,
        blue_mask: np.ndarray,
        hook_x: float | None,
        ignore_prev: bool = False,
    ) -> tuple[float | None, float | None, float | None, int]:
        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(blue_mask, connectivity=8)
        if count <= 1:
            return None, None, None, 0

        best_label = 1
        best_score = float("inf")
        for label in range(1, count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < self.min_blue_pixels or area > self.blue_max_pixels:
                continue

            left = float(stats[label, cv2.CC_STAT_LEFT])
            width = float(stats[label, cv2.CC_STAT_WIDTH])
            right = left + width
            if width < self.min_zone_width_px:
                continue

            center = (left + right) / 2.0
            score = abs(area - 5500.0) * 0.02
            bar_width = float(blue_mask.shape[1])
            if left < bar_width * 0.18:
                if area > 4000:
                    score += 40.0
                elif hook_x is not None and hook_x > bar_width * 0.55:
                    score -= 250.0
                else:
                    score += 900.0
            if right > bar_width * 0.98:
                score += 400.0
            if hook_x is not None:
                if left - 25 <= hook_x <= right + 25:
                    score -= 300.0
                else:
                    score += min(abs(hook_x - center) * 0.08, 120.0)
            if not ignore_prev and self._blue_left is not None and self._blue_right is not None:
                prev_center = (self._blue_left + self._blue_right) / 2.0
                prev_width = self._blue_right - self._blue_left
                overlap = max(0.0, min(right, self._blue_right) - max(left, self._blue_left))
                overlap_ratio = overlap / max(prev_width, width, 1.0)
                if overlap_ratio < 0.45:
                    score += 800.0
                else:
                    score -= overlap_ratio * 120.0
                score += abs(center - prev_center) * 0.5
                score += max(abs(left - self._blue_left), abs(right - self._blue_right)) * 0.2

            if score < best_score:
                best_score = score
                best_label = label

        area = int(stats[best_label, cv2.CC_STAT_AREA])
        left = float(stats[best_label, cv2.CC_STAT_LEFT])
        width = float(stats[best_label, cv2.CC_STAT_WIDTH])
        right = left + width
        center = (left + right) / 2.0
        return left, right, center, area

    def _zone_from_label(
        self,
        blue_mask: np.ndarray,
        label: int,
        stats: np.ndarray,
    ) -> tuple[float, float, float, int]:
        area = int(stats[label, cv2.CC_STAT_AREA])
        left = float(stats[label, cv2.CC_STAT_LEFT])
        width = float(stats[label, cv2.CC_STAT_WIDTH])
        right = left + width
        center = (left + right) / 2.0
        return left, right, center, area

    def _zone_separated_from_hook(
        self,
        hook_x: float | None,
        left: float | None,
        right: float | None,
        margin: float = 35.0,
    ) -> bool:
        if hook_x is None or left is None or right is None:
            return False
        return hook_x > right + margin or hook_x < left - margin

    def _vision_zone_bounds(
        self,
        blue_mask: np.ndarray,
    ) -> tuple[float | None, float | None, float | None, int]:
        return self._measure_zone_vision(blue_mask)

    def _nearest_zone_to_hook(
        self,
        blue_mask: np.ndarray,
        hook_x: float,
    ) -> tuple[float | None, float | None, float | None, int]:
        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(blue_mask, connectivity=8)
        if count <= 1:
            return None, None, None, 0

        best: tuple[float, float, float, float, int] | None = None
        for label in range(1, count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < self.min_blue_pixels or area > self.blue_max_pixels:
                continue
            width = float(stats[label, cv2.CC_STAT_WIDTH])
            if width < self.min_zone_width_px:
                continue

            left, right, center, area = self._zone_from_label(blue_mask, label, stats)
            score = abs(hook_x - center) * 1.2
            if left - 25 <= hook_x <= right + 25:
                score -= 220.0
            score += abs(area - 5500.0) * 0.015
            score += abs(width - self.expected_zone_width_px) * 0.08

            if best is None or score < best[0]:
                best = (score, left, right, center, area)

        if best is None:
            return None, None, None, 0
        _score, left, right, center, area = best
        return left, right, center, area

    def _measure_zone_vision(
        self,
        zone_mask: np.ndarray,
    ) -> tuple[float | None, float | None, float | None, int]:
        bounds = self._zone_bounds_from_columns(zone_mask)
        if bounds[0] is not None:
            return bounds
        return self._largest_component_bounds(zone_mask, None, ignore_prev=True)

    def _follow_zone_measurement(
        self,
        left: float,
        right: float,
        hook_x: float | None,
    ) -> tuple[float, float, float]:
        center = (left + right) / 2.0
        prev_l = self._ctrl_blue_left if self._ctrl_blue_left is not None else self._blue_left
        prev_r = self._ctrl_blue_right if self._ctrl_blue_right is not None else self._blue_right
        if prev_l is None or prev_r is None:
            return left, right, center

        hook_outside_vision = self._zone_separated_from_hook(hook_x, left, right, margin=8.0)
        hook_outside_prev = self._zone_separated_from_hook(hook_x, prev_l, prev_r, margin=8.0)
        jump = max(abs(left - prev_l), abs(right - prev_r))

        if hook_outside_vision or hook_outside_prev:
            max_step = max(self.max_zone_jump_px * 2.5, 48.0)
            if jump > max_step * 2.0:
                return left, right, center
        else:
            max_step = float(self.max_zone_jump_px)

        if jump <= max_step:
            return left, right, center

        scale = max_step / jump
        new_left = prev_l + (left - prev_l) * scale
        new_right = prev_r + (right - prev_r) * scale
        return new_left, new_right, (new_left + new_right) / 2.0

    def _blue_zone_bounds(
        self,
        blue_mask: np.ndarray,
        hook_x: float | None,
    ) -> tuple[float | None, float | None, float | None, int]:
        left, right, center, area = self._measure_zone_vision(blue_mask)
        if left is None or right is None or center is None:
            self._reject_streak += 1
            if self._reject_streak >= 4:
                self._blue_left = None
                self._blue_right = None
            return None, None, None, area

        self._reject_streak = 0
        follow_left, follow_right, follow_center = self._follow_zone_measurement(
            left, right, hook_x
        )
        return follow_left, follow_right, follow_center, area

    def _slide_zone_toward_hook(
        self,
        hook_x: float,
        left: float,
        right: float,
        bar_width: float,
    ) -> tuple[float, float, float]:
        width = right - left
        if width < self.expected_zone_width_px * 0.55:
            if self._blue_left is not None and self._blue_right is not None:
                width = self._blue_right - self._blue_left
            else:
                width = float(self.expected_zone_width_px)
        width = max(width, self.expected_zone_width_px * 1.05)
        step = float(self.max_zone_jump_px)

        if hook_x > right + 1:
            shift = min(hook_x - right + 8, step)
            left += shift
            right += shift
        elif hook_x < left - 1:
            shift = min(left - hook_x + 8, step)
            left -= shift
            right -= shift

        if right > bar_width:
            overshoot = right - bar_width
            left -= overshoot
            right = bar_width
        if left < 0:
            right -= left
            left = 0.0

        if right - left < width * 0.88:
            center = hook_x
            left = center - width * 0.5
            right = center + width * 0.5
            if right > bar_width:
                right = bar_width
                left = max(0.0, right - width)
            if left < 0:
                left = 0.0
                right = min(bar_width, width)

        center = (left + right) / 2.0
        return left, right, center

    def _hook_mask_raw(
        self,
        bar_bgr: np.ndarray,
        blue_mask: np.ndarray,
        white_threshold: int | None = None,
    ) -> np.ndarray:
        threshold = self.hook_white_threshold if white_threshold is None else white_threshold
        gray = cv2.cvtColor(bar_bgr, cv2.COLOR_BGR2GRAY)
        _, bright_gray = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

        hsv = cv2.cvtColor(bar_bgr, cv2.COLOR_BGR2HSV)
        v_floor = max(threshold, self.hook_v_min)
        bright_desat = cv2.inRange(
            hsv,
            np.array([0, 0, v_floor], dtype=np.uint8),
            np.array([180, self.hook_s_max, 255], dtype=np.uint8),
        )

        hook_mask = cv2.bitwise_or(bright_gray, cv2.bitwise_and(bright_desat, bright_gray))

        blue_bleed = cv2.bitwise_and(blue_mask, cv2.bitwise_not(bright_gray))
        hook_mask = cv2.bitwise_and(hook_mask, cv2.bitwise_not(blue_bleed))

        k = max(1, self.hook_noise_open_px)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        hook_mask = cv2.morphologyEx(hook_mask, cv2.MORPH_OPEN, kernel)

        hook_mask = cv2.morphologyEx(
            hook_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 5)),
        )
        hook_mask = cv2.dilate(
            hook_mask,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1)),
            iterations=1,
        )
        return hook_mask

    def _search_band_ratios(self) -> tuple[float, float]:
        if self.hook_search_margin_ratio <= 0:
            return self.hook_band_top_ratio, self.hook_band_bottom_ratio

        margin = self.hook_search_margin_ratio
        top = max(0.0, self.hook_band_top_ratio - margin)
        bottom = min(1.0, self.hook_band_bottom_ratio + margin)
        min_height = self.hook_search_min_height_ratio
        if bottom - top < min_height:
            mid = (self.hook_band_top_ratio + self.hook_band_bottom_ratio) * 0.5
            top = max(0.0, mid - min_height * 0.5)
            bottom = min(1.0, mid + min_height * 0.5)
        return top, bottom

    def _hook_search_mask(
        self,
        bar_bgr: np.ndarray,
        blue_mask: np.ndarray,
        prev_x: float | None = None,
    ) -> np.ndarray:
        raw = self._hook_mask_raw(bar_bgr, blue_mask)
        text_cutoff = int(bar_bgr.shape[0] * 0.38)
        raw[:text_cutoff, :] = 0
        y0 = int(bar_bgr.shape[0] * self._search_band_ratios()[0])
        y1 = int(bar_bgr.shape[0] * self._search_band_ratios()[1])
        search_mask = np.zeros_like(raw)
        search_mask[y0:y1, :] = raw[y0:y1, :]
        return self._mask_bar_edges(search_mask, prev_x)

    def _vertical_line_mask(self, band_mask: np.ndarray) -> np.ndarray:
        if band_mask.size == 0:
            return band_mask
        band_h = max(band_mask.shape[0], 1)
        v_len = max(4, min(band_h // 2, 14))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
        return cv2.morphologyEx(band_mask, cv2.MORPH_OPEN, v_kernel)

    def _hook_mask(self, bar_bgr: np.ndarray, blue_mask: np.ndarray) -> np.ndarray:
        return self._hook_search_mask(bar_bgr, blue_mask, self._x_hook)

    def _hook_core_x(self, contour: np.ndarray, band_mask: np.ndarray) -> float | None:
        x, y, w, h = cv2.boundingRect(contour)
        if w <= 0 or h <= 0:
            return None
        sub = band_mask[y : y + h, x : x + w]
        best_span = 0
        best_col = w // 2
        for col in range(w):
            rows = np.where(sub[:, col] > 0)[0]
            if rows.size < 3:
                continue
            span = int(rows[-1] - rows[0] + 1)
            if span > best_span:
                best_span = span
                best_col = col
        if best_span < max(6, int(self.hook_shape_min_height_px * 0.6)):
            return None
        return float(x + best_col)

    def _passes_hook_shape_test(
        self,
        contour: np.ndarray,
        band_mask: np.ndarray,
        band_height: int,
    ) -> bool:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if area < self.hook_area_min or area > self.hook_area_max:
            return False
        if w < 3 or h < max(6.0, self.hook_shape_min_height_px * 0.7):
            return False
        if w > self.hook_shape_max_width_px or h > self.hook_max_height_px:
            return False

        aspect = h / max(w, 1)
        if aspect < self.hook_min_aspect or aspect > self.hook_max_aspect:
            return False

        sub = band_mask[y : y + h, x : x + w]
        col_spans: list[tuple[int, int]] = []
        for col in range(w):
            rows = np.where(sub[:, col] > 0)[0]
            if rows.size >= 2:
                col_spans.append((int(rows[-1] - rows[0] + 1), col))
        if not col_spans:
            return False

        best_span, _best_col = max(col_spans)
        min_span = max(6.0, self.hook_shape_min_height_px * 0.65, band_height * self.hook_shape_min_span_ratio)
        if best_span < min_span:
            return False

        fill = area / max(w * h, 1)
        if fill > 0.82 and w > 12:
            return False

        return True

    def _shape_hook_score(
        self,
        contour: np.ndarray,
        band_mask: np.ndarray,
        band_height: int,
        cx: float,
        prev_x: float | None,
        zone_left: float | None,
        zone_right: float | None,
    ) -> float | None:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        aspect = h / max(w, 1)

        score = aspect * 35.0 + min(area, 220.0) * 0.35 + min(h, band_height) * 1.5
        score -= max(w - 10, 0) * 8.0

        sub = band_mask[y : y + h, x : x + w]
        col_spans = []
        for col in range(w):
            rows = np.where(sub[:, col] > 0)[0]
            if rows.size >= 3:
                col_spans.append(int(rows[-1] - rows[0] + 1))
        if col_spans:
            score += max(col_spans) * 1.8

        if prev_x is not None:
            score -= abs(cx - prev_x) * 1.4
        else:
            score -= abs(cx - band_mask.shape[1] * 0.5) * 0.04

        if zone_right is not None and prev_x is not None:
            edge_glitch = (zone_right - 10) <= cx <= (zone_right + 12)
            if edge_glitch and abs(cx - prev_x) > 42:
                score -= 100.0

        return score

    def _find_hook_by_shape(
        self,
        band_mask: np.ndarray,
        band_height: int,
        prev_x: float | None,
        zone_left: float | None,
        zone_right: float | None,
    ) -> float | None:
        line_mask = self._vertical_line_mask(band_mask)
        contours: list[np.ndarray] = []
        for source in (line_mask, band_mask):
            found, _ = cv2.findContours(source, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours.extend(found)

        best_score = float("-inf")
        best_x: float | None = None
        seen_boxes: set[tuple[int, int, int, int]] = set()

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            box = (x, y, w, h)
            if box in seen_boxes:
                continue
            seen_boxes.add(box)

            if prev_x is not None and abs(x + w * 0.5 - prev_x) > self.hook_search_radius_px:
                continue
            if not self._passes_hook_shape_test(contour, band_mask, band_height):
                continue

            cx = self._hook_core_x(contour, band_mask)
            if cx is None:
                continue
            if self._hook_in_edge_exclusion(cx, band_mask.shape[1], prev_x):
                continue
            if prev_x is not None and abs(cx - prev_x) > self.max_hook_jump_px:
                continue

            score = self._shape_hook_score(
                contour, band_mask, band_height, cx, prev_x, zone_left, zone_right
            )
            if score is None or score <= best_score:
                continue
            best_score = score
            best_x = cx

        return best_x

    def _score_hook_contour(
        self,
        contour: np.ndarray,
        band_height: int,
        band_width: int,
        prev_x: float | None,
        zone_left: float | None = None,
        zone_right: float | None = None,
    ) -> float | None:
        area = cv2.contourArea(contour)
        if area < self.hook_area_min or area > self.hook_area_max:
            return None

        x, y, w, h = cv2.boundingRect(contour)
        if w > self.hook_max_width_px or h > self.hook_max_height_px:
            return None
        if w > band_width * 0.14:
            return None

        aspect = h / max(w, 1)
        if band_height >= 14:
            if aspect < self.hook_min_aspect or aspect > self.hook_max_aspect:
                return None
        elif area < 4:
            return None

        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            return None

        cx = float(moments["m10"] / moments["m00"])
        cy = float(moments["m01"] / moments["m00"])

        score = area * 0.08
        score += w * 2.5
        score += abs(w - h) * 0.4
        score += abs(cy - band_height * 0.5) * 1.2

        if prev_x is not None:
            score += abs(cx - prev_x) * 2.0
        else:
            score += abs(cx - band_width * 0.5) * 0.05

        if zone_left is not None and zone_right is not None:
            zone_width = max(zone_right - zone_left, 1.0)
            if prev_x is not None and not (zone_left - 40 <= prev_x <= zone_right + 40):
                if zone_left + zone_width * 0.1 < cx < zone_right - zone_width * 0.1:
                    score += 80.0

        return score

    def _hook_x_from_vertical_peaks(
        self,
        line_mask: np.ndarray,
        zone_left: float | None,
        zone_right: float | None,
        prev_x: float | None,
    ) -> float | None:
        if line_mask.size == 0:
            return None

        col_counts = np.count_nonzero(line_mask, axis=0).astype(np.float64)
        if col_counts.max() < 3.0:
            return None

        height = line_mask.shape[0]
        candidates: list[tuple[float, float]] = []

        for x in range(1, len(col_counts) - 1):
            count = col_counts[x]
            if count < 3.0:
                continue
            if count < col_counts[x - 1] or count < col_counts[x + 1]:
                continue

            rows = np.where(line_mask[:, x] > 0)[0]
            extent = float(rows[-1] - rows[0] + 1) if rows.size else 0.0
            if extent < max(3.0, height * 0.08):
                continue

            score = count * 4.0 + extent * 2.5
            if prev_x is not None:
                score -= abs(x - prev_x) * 0.25
            candidates.append((score, float(x)))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_x = candidates[0]

        if len(candidates) > 1 and prev_x is not None:
            second_score, second_x = candidates[1]
            if second_score >= best_score * 0.82 and abs(second_x - best_x) > 70:
                if abs(second_x - prev_x) + 8 < abs(best_x - prev_x):
                    best_x = second_x

        if best_score < 8.0:
            return None
        return best_x

    def _hook_x_from_band(self, band_mask: np.ndarray) -> float | None:
        ys, xs = np.where(band_mask > 0)
        if xs.size < max(self.min_white_pixels, 12):
            return None

        if self._blue_left is None or self._blue_right is None:
            return float(np.average(xs))

        weights = np.ones(xs.shape[0], dtype=np.float64)
        for idx, x in enumerate(xs):
            if self._blue_left - 25 <= x <= self._blue_right + 55:
                weights[idx] = 3.0
            elif x < self._blue_left - 50:
                weights[idx] = 0.25
        return float(np.average(xs, weights=weights))

    def _hook_x_from_column_projection(
        self,
        strip: np.ndarray,
        zone_left: float | None,
        zone_right: float | None,
        prev_x: float | None,
    ) -> float | None:
        if strip.size == 0:
            return None

        col_counts = np.count_nonzero(strip, axis=0).astype(np.float64)
        if col_counts.max() < 1.0:
            return None

        width = strip.shape[1]
        scores = col_counts.copy()
        if width >= 5:
            kernel = np.array([0.12, 0.18, 0.28, 0.18, 0.12], dtype=np.float64)
            scores = np.convolve(scores, kernel, mode="same")

        best_score = -1.0
        best_cx: float | None = None
        max_w = min(36, max(8, width // 6))
        for w in range(3, max_w + 1):
            for x0 in range(0, width - w + 1):
                window_score = float(scores[x0 : x0 + w].sum())
                cx = x0 + (w - 1) / 2.0
                if prev_x is not None:
                    window_score -= abs(cx - prev_x) * 0.35
                if window_score > best_score:
                    best_score = window_score
                    best_cx = cx

        if best_cx is None or best_score < 5.0:
            return None
        return best_cx

    def _sanitize_hook_x(
        self,
        raw_x: float,
        zone_left: float | None,
        zone_right: float | None,
    ) -> float:
        if self._x_hook is None:
            return raw_x

        jump = abs(raw_x - self._x_hook)
        if jump <= self.max_hook_jump_px:
            return raw_x
        return self._x_hook

    def _pin_control_zone(
        self,
        left: float,
        right: float,
        hook_x: float | None,
    ) -> tuple[float, float, float]:
        center = (left + right) / 2.0
        if (
            hook_x is None
            or self._ctrl_blue_left is None
            or self._ctrl_blue_right is None
        ):
            return left, right, center

        prev_l = self._ctrl_blue_left
        prev_r = self._ctrl_blue_right
        hook_inside_prev = prev_l <= hook_x <= prev_r
        hook_inside_new = left <= hook_x <= right
        jump = max(abs(left - prev_l), abs(right - prev_r))

        if hook_inside_prev and hook_inside_new and jump < 22.0:
            return prev_l, prev_r, (prev_l + prev_r) / 2.0

        return left, right, center

    def _reacquire_hook_x(
        self,
        line_mask: np.ndarray,
        band_mask: np.ndarray,
        white_pixels: int,
    ) -> float | None:
        best_x = self._hook_x_from_vertical_peaks(line_mask, None, None, None)
        if best_x is not None:
            return best_x
        if white_pixels >= self.min_white_pixels:
            source = line_mask if cv2.countNonZero(line_mask) > 0 else band_mask
            return self._hook_x_from_column_projection(source, None, None, None)
        return None

    def _stabilize_zone_bounds(
        self,
        left: float,
        right: float,
        hook_x: float | None,
        bar_width: float,
        hook_trusted: bool = True,
    ) -> tuple[float, float, float]:
        width = right - left
        center = (left + right) / 2.0
        expected = self.expected_zone_width_px

        min_width = expected * 1.05
        if self._blue_left is not None and self._blue_right is not None:
            min_width = max(min_width, (self._blue_right - self._blue_left) * 0.92)

        if width < expected * 0.88 and self._blue_left is not None and self._blue_right is not None:
            prev_w = self._blue_right - self._blue_left
            center = (left + right) / 2.0
            if hook_trusted and hook_x is not None and left <= hook_x <= right:
                center = hook_x
            half = prev_w * 0.5
            left = center - half
            right = center + half
        elif width < expected * 0.88:
            center = hook_x if hook_trusted and hook_x is not None else center
            half = expected * 0.55
            left = center - half
            right = center + half

        if right - left < min_width:
            center = (left + right) / 2.0
            if hook_trusted and hook_x is not None and left - 15 <= hook_x <= right + 15:
                center = hook_x
            left = center - min_width * 0.5
            right = center + min_width * 0.5

        if right > bar_width:
            overshoot = right - bar_width
            left -= overshoot
            right = bar_width
        if left < 0:
            right -= left
            left = 0.0

        if right >= bar_width - 1 and right - left < min_width:
            left = max(0.0, right - min_width)

        right = min(bar_width, max(right, left + min_width * 0.55))
        left = max(0.0, min(left, bar_width - min_width * 0.55))
        center = (left + right) / 2.0
        return left, right, center

    def _hook_cx_from_contour(
        self,
        contour: np.ndarray,
        band_mask: np.ndarray,
        prev_x: float | None,
    ) -> float | None:
        x, y, w, h = cv2.boundingRect(contour)
        if w <= self.hook_shirt_merge_width:
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                return None
            return float(moments["m10"] / moments["m00"])

        slice_start = x + max(1, int(w * 0.5))
        local = band_mask[y : y + h, slice_start : x + w]
        if local.size == 0:
            return None

        ys, xs = np.where(local > 0)
        if xs.size < max(8, self.hook_area_min // 3):
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                return None
            return float(moments["m10"] / moments["m00"])

        cx = float(slice_start + xs.mean())
        if prev_x is not None and abs(cx - prev_x) > self.max_hook_jump_px:
            col_weights: list[tuple[float, float]] = []
            for col in range(local.shape[1]):
                count = int(np.count_nonzero(local[:, col]))
                if count == 0:
                    continue
                global_x = float(slice_start + col)
                weight = count - abs(global_x - prev_x) * 0.15
                col_weights.append((weight, global_x))
            if col_weights:
                return max(col_weights, key=lambda item: item[0])[1]
        return cx

    def _find_hook_x(
        self,
        bar_bgr: np.ndarray,
        blue_mask: np.ndarray,
        zone_left: float | None = None,
        zone_right: float | None = None,
    ) -> tuple[float | None, int]:
        hook_mask = self._hook_search_mask(bar_bgr, blue_mask, self._x_hook)

        search_top, search_bottom = self._search_band_ratios()
        band_y0 = int(bar_bgr.shape[0] * search_top)
        band_y1 = int(bar_bgr.shape[0] * search_bottom)
        band_mask = hook_mask[band_y0:band_y1, :]
        band_height, band_width = band_mask.shape[:2]
        line_mask = self._vertical_line_mask(band_mask)
        white_pixels = int(cv2.countNonZero(line_mask))
        if white_pixels == 0:
            white_pixels = int(cv2.countNonZero(band_mask))

        zone_left = zone_left if zone_left is not None else self._blue_left
        zone_right = zone_right if zone_right is not None else self._blue_right

        best_x = self._find_hook_by_shape(
            band_mask, band_height, self._x_hook, zone_left, zone_right
        )
        shape_found = best_x is not None

        if best_x is None and self._x_hook is None:
            best_x = self._hook_x_from_vertical_peaks(
                line_mask, zone_left, zone_right, None
            )

        if best_x is None and self._x_hook is None and white_pixels >= self.min_white_pixels:
            best_x = self._hook_x_from_column_projection(
                line_mask if cv2.countNonZero(line_mask) > 0 else band_mask,
                zone_left,
                zone_right,
                None,
            )

        if best_x is None and self._x_hook is not None:
            self._hook_stale_frames += 1
            if self._hook_stale_frames >= 8:
                best_x = self._reacquire_hook_x(line_mask, band_mask, white_pixels)
                if best_x is not None:
                    self._hook_stale_frames = 0
            if best_x is None:
                if self._hook_stale_frames >= 14:
                    return None, white_pixels
                return self._x_hook, white_pixels

        if shape_found:
            self._hook_stale_frames = 0
        elif best_x is not None and self._hook_stale_frames > 0:
            self._hook_stale_frames = max(0, self._hook_stale_frames - 1)

        if (
            best_x is not None
            and self._x_hook is not None
            and abs(best_x - self._x_hook) > self.max_hook_jump_px
        ):
            best_x = self._x_hook

        return best_x, white_pixels

    def _finalize_raw_hook(
        self,
        raw_x: float | None,
        zone_left: float | None,
        zone_right: float | None,
        bar_width: int,
    ) -> float | None:
        if raw_x is None:
            return None

        if self._x_hook is not None and abs(raw_x - self._x_hook) > self.max_hook_jump_px:
            return self._x_hook

        if zone_right is not None and zone_left is not None:
            if raw_x >= zone_right - 8:
                if self._x_hook is None or self._x_hook < zone_right - 45:
                    return self._x_hook if self._x_hook is not None else raw_x
            if raw_x <= zone_left + 8 and self._x_hook is not None:
                if self._x_hook > zone_left + 45 and abs(raw_x - self._x_hook) > 20:
                    return self._x_hook

        if self._hook_in_edge_exclusion(raw_x, bar_width, self._x_hook):
            return self._x_hook if self._x_hook is not None else raw_x

        edge_limit = float(bar_width) - float(self.bar_margin_right_px) - 8.0
        if (
            self._x_hook is not None
            and raw_x >= edge_limit
            and self._x_hook < edge_limit - 55
        ):
            return self._x_hook

        return raw_x

    def _store_control_state(
        self,
        raw_x_hook: float,
        raw_left: float,
        raw_right: float,
    ) -> None:
        raw_center = (raw_left + raw_right) / 2.0
        self._ctrl_x_hook = raw_x_hook
        self._ctrl_blue_left = raw_left
        self._ctrl_blue_right = raw_right
        self._ctrl_error = raw_x_hook - raw_center

    def peek_zone_bounds(
        self, frame_bgr: np.ndarray
    ) -> tuple[float | None, float | None]:
        bar_bgr, _ = self._bar_slice(frame_bgr)
        zone_mask = self._blue_mask_for_zone(bar_bgr)
        left, right, _center, area = self._vision_zone_bounds(zone_mask)
        if left is None or right is None or area < self.min_blue_pixels:
            return None, None
        return left, right

    def peek_hook_x(self, frame_bgr: np.ndarray) -> float | None:
        bar_bgr, _ = self._bar_slice(frame_bgr)
        blue_mask = self._blue_mask(bar_bgr)
        prelim_left, prelim_right, _, _ = self._largest_component_bounds(blue_mask, self._x_hook)
        zone_left = self._blue_left if self._blue_left is not None else prelim_left
        zone_right = self._blue_right if self._blue_right is not None else prelim_right
        hook_x, _ = self._find_hook_x(bar_bgr, blue_mask, zone_left, zone_right)
        return hook_x

    def _cached_active_result(self, blue_pixels: int, white_pixels: int) -> DetectionResult:
        assert self._x_hook is not None
        assert self._x_blue is not None
        assert self._blue_left is not None
        assert self._blue_right is not None
        zone_width = self._blue_right - self._blue_left
        ctrl_hook = self._ctrl_x_hook if self._ctrl_x_hook is not None else self._x_hook
        ctrl_left = self._ctrl_blue_left if self._ctrl_blue_left is not None else self._blue_left
        ctrl_right = self._ctrl_blue_right if self._ctrl_blue_right is not None else self._blue_right
        ctrl_error = self._ctrl_error if self._ctrl_error is not None else (ctrl_hook - self._x_blue)
        return DetectionResult(
            active=True,
            x_hook=self._x_hook,
            x_blue=self._x_blue,
            blue_left=self._blue_left,
            blue_right=self._blue_right,
            error=self._x_hook - self._x_blue,
            blue_pixels=blue_pixels,
            white_pixels=white_pixels,
            zone_width=zone_width,
            x_hook_control=ctrl_hook,
            blue_left_control=ctrl_left,
            blue_right_control=ctrl_right,
            error_control=ctrl_error,
        )

    def detect(self, frame_bgr: np.ndarray) -> DetectionResult:
        if (
            self._x_hook is not None
            and self._x_blue is not None
            and abs(self._x_hook - self._x_blue) > 45
        ):
            self._wrong_error_streak += 1
        else:
            self._wrong_error_streak = 0

        if self._wrong_error_streak > 20:
            self._x_hook = None
            self._wrong_error_streak = 0

        bar_bgr, _ = self._bar_slice(frame_bgr)
        blue_mask = self._blue_mask(bar_bgr)
        zone_mask = self._blue_mask_for_zone(bar_bgr)

        prelim_left, prelim_right, _, _ = self._vision_zone_bounds(zone_mask)
        hint_left = self._blue_left if self._blue_left is not None else prelim_left
        hint_right = self._blue_right if self._blue_right is not None else prelim_right

        raw_x_hook, white_pixels = self._find_hook_x(
            bar_bgr, blue_mask, hint_left, hint_right
        )
        if (
            raw_x_hook is None
            and self._x_hook is not None
            and white_pixels >= self.min_white_pixels
            and self._lost_streak < 8
            and self._hook_stale_frames < 5
        ):
            raw_x_hook = self._x_hook

        hook_for_zone = raw_x_hook if raw_x_hook is not None else self._x_hook
        hook_trusted = self._hook_stale_frames == 0
        raw_left, raw_right, raw_center, _zone_area = self._blue_zone_bounds(
            zone_mask, hook_for_zone
        )
        blue_pixels = int(cv2.countNonZero(zone_mask))
        bar_width = float(bar_bgr.shape[1])

        if raw_left is not None and raw_left < bar_width * 0.18:
            hook_in_new = (
                hook_for_zone is not None
                and raw_right is not None
                and raw_left - 25 <= hook_for_zone <= raw_right + 25
            )
            hook_on_opposite_side = (
                hook_for_zone is not None
                and raw_right is not None
                and hook_for_zone > raw_right + 35
            )
            if hook_on_opposite_side:
                pass
            elif not hook_in_new and self._blue_left is not None and self._blue_right is not None:
                raw_left = self._blue_left
                raw_right = self._blue_right
                raw_center = self._x_blue if self._x_blue is not None else (raw_left + raw_right) / 2.0
            elif not hook_in_new:
                raw_left = None
                raw_right = None
                raw_center = None

        if raw_x_hook is not None:
            raw_x_hook = self._sanitize_hook_x(
                raw_x_hook,
                raw_left if raw_left is not None else self._blue_left,
                raw_right if raw_right is not None else self._blue_right,
            )
            raw_x_hook = self._finalize_raw_hook(
                raw_x_hook,
                raw_left if raw_left is not None else self._blue_left,
                raw_right if raw_right is not None else self._blue_right,
                int(bar_width),
            )

        if (
            raw_x_hook is not None
            and self._x_hook is not None
            and abs(raw_x_hook - self._x_hook) < 0.01
            and self._hook_stale_frames >= 5
            and self._blue_left is not None
            and self._blue_right is not None
            and raw_left is not None
            and raw_right is not None
        ):
            zone_shift = max(
                abs(raw_left - self._blue_left),
                abs(raw_right - self._blue_right),
            )
            if zone_shift > 10.0:
                saved_hook = self._x_hook
                self._x_hook = None
                self._hook_stale_frames = 0
                raw_x_hook, white_pixels = self._find_hook_x(
                    bar_bgr,
                    blue_mask,
                    raw_left,
                    raw_right,
                )
                if raw_x_hook is None:
                    self._x_hook = saved_hook
                else:
                    raw_x_hook = self._sanitize_hook_x(
                        raw_x_hook,
                        raw_left,
                        raw_right,
                    )
                    raw_x_hook = self._finalize_raw_hook(
                        raw_x_hook,
                        raw_left,
                        raw_right,
                        int(bar_width),
                    )
                hook_trusted = self._hook_stale_frames == 0

        if raw_left is not None and raw_right is not None:
            raw_left, raw_right, raw_center = self._stabilize_zone_bounds(
                raw_left,
                raw_right,
                raw_x_hook if raw_x_hook is not None else hook_for_zone,
                bar_width,
                hook_trusted=hook_trusted,
            )
            hook_ctrl = raw_x_hook if raw_x_hook is not None else hook_for_zone
            if (
                hook_ctrl is not None
                and raw_left <= hook_ctrl <= raw_right
            ):
                raw_left, raw_right, raw_center = self._pin_control_zone(
                    raw_left,
                    raw_right,
                    hook_ctrl,
                )

        if (
            raw_x_hook is not None
            and white_pixels > 600
            and raw_left is not None
            and raw_right is not None
            and not (raw_left - 30 <= raw_x_hook <= raw_right + 30)
        ):
            raw_x_hook = None

        active = (
            raw_left is not None
            and raw_right is not None
            and raw_center is not None
            and (raw_right - raw_left) >= self.min_zone_width_px
            and white_pixels >= self.min_white_pixels
            and raw_x_hook is not None
        )

        if not active:
            self._lost_streak += 1
            if (
                self._lost_streak <= self.lost_grace_frames
                and self._x_hook is not None
                and self._blue_left is not None
                and self._blue_right is not None
                and blue_pixels >= self.min_blue_pixels
            ):
                return self._cached_active_result(blue_pixels, white_pixels)

            fallback_left = raw_left
            fallback_right = raw_right
            if (
                (fallback_left is None or fallback_right is None)
                and blue_pixels >= self.min_blue_pixels
            ):
                fallback_left, fallback_right, _, _ = self._vision_zone_bounds(zone_mask)

            self._x_hook = None
            self._x_blue = None
            self._blue_left = None
            self._blue_right = None
            self._ctrl_x_hook = None
            self._ctrl_blue_left = None
            self._ctrl_blue_right = None
            self._ctrl_error = None
            return DetectionResult(
                active=False,
                x_hook=raw_x_hook,
                x_blue=(fallback_left + fallback_right) / 2.0 if fallback_left is not None and fallback_right is not None else None,
                blue_left=fallback_left,
                blue_right=fallback_right,
                error=(
                    raw_x_hook - (fallback_left + fallback_right) / 2.0
                    if raw_x_hook is not None and fallback_left is not None and fallback_right is not None
                    else None
                ),
                blue_pixels=blue_pixels,
                white_pixels=white_pixels,
                zone_width=(fallback_right - fallback_left) if fallback_left is not None and fallback_right is not None else None,
                x_hook_control=raw_x_hook,
                blue_left_control=fallback_left,
                blue_right_control=fallback_right,
                error_control=(
                    raw_x_hook - (fallback_left + fallback_right) / 2.0
                    if raw_x_hook is not None and fallback_left is not None and fallback_right is not None
                    else None
                ),
            )

        self._lost_streak = 0
        hook_ctrl = raw_x_hook
        chase = self._zone_separated_from_hook(hook_ctrl, raw_left, raw_right, margin=8.0)
        zone_smooth = 0.25 if chase else self.zone_smoothing
        display_left = self._smooth(self._blue_left, raw_left, zone_smooth)
        display_right = self._smooth(self._blue_right, raw_right, zone_smooth)
        display_blue = self._smooth(self._x_blue, raw_center, zone_smooth)
        self._blue_left = display_left
        self._blue_right = display_right
        self._x_blue = display_blue
        self._x_hook = raw_x_hook
        assert self._x_blue is not None
        assert self._blue_left is not None
        assert self._blue_right is not None

        raw_center = (raw_left + raw_right) / 2.0
        error = self._x_hook - self._x_blue
        error_control = raw_x_hook - raw_center
        self._store_control_state(raw_x_hook, raw_left, raw_right)
        zone_width = self._blue_right - self._blue_left

        return DetectionResult(
            active=True,
            x_hook=self._x_hook,
            x_blue=self._x_blue,
            blue_left=self._blue_left,
            blue_right=self._blue_right,
            error=error,
            blue_pixels=blue_pixels,
            white_pixels=white_pixels,
            zone_width=zone_width,
            x_hook_control=raw_x_hook,
            blue_left_control=raw_left,
            blue_right_control=raw_right,
            error_control=error_control,
        )

    def debug_frame(self, frame_bgr: np.ndarray) -> np.ndarray:
        bar_bgr, bar_top = self._bar_slice(frame_bgr)
        blue_mask = self._blue_mask(bar_bgr)
        hook_mask = self._hook_mask(bar_bgr, blue_mask)

        overlay = frame_bgr.copy()
        bar_overlay = overlay[bar_top:, :]
        bar_overlay[blue_mask > 0] = (255, 128, 0)
        bar_overlay[hook_mask > 0] = (255, 255, 255)
        overlay[bar_top:, :] = cv2.addWeighted(bar_bgr, 0.55, bar_overlay, 0.45, 0)

        bar_h = bar_bgr.shape[0]
        y_tune0 = bar_top + int(bar_h * self.hook_band_top_ratio)
        y_tune1 = bar_top + int(bar_h * self.hook_band_bottom_ratio)
        search_top, search_bottom = self._search_band_ratios()
        y_search0 = bar_top + int(bar_h * search_top)
        y_search1 = bar_top + int(bar_h * search_bottom)
        cv2.line(overlay, (0, y_tune0), (overlay.shape[1] - 1, y_tune0), (0, 255, 255), 1)
        cv2.line(overlay, (0, y_tune1), (overlay.shape[1] - 1, y_tune1), (0, 255, 255), 1)
        if abs(search_top - self.hook_band_top_ratio) > 0.005 or abs(
            search_bottom - self.hook_band_bottom_ratio
        ) > 0.005:
            cv2.line(overlay, (0, y_search0), (overlay.shape[1] - 1, y_search0), (255, 180, 0), 1)
            cv2.line(overlay, (0, y_search1), (overlay.shape[1] - 1, y_search1), (255, 180, 0), 1)

        if bar_top > 0:
            cv2.line(overlay, (0, bar_top), (overlay.shape[1] - 1, bar_top), (0, 255, 255), 1)

        edge_left, edge_right = self._strict_bar_edge_limits(overlay.shape[1])
        y0 = bar_top if bar_top > 0 else 0
        y1 = overlay.shape[0] - 1
        cv2.line(overlay, (edge_left, y0), (edge_left, y1), (0, 0, 255), 1)
        cv2.line(overlay, (edge_right, y0), (edge_right, y1), (0, 0, 255), 1)

        return overlay

    def draw_zone_overlay(
        self,
        overlay: np.ndarray,
        left: float | None,
        right: float | None,
        bar_top: int = 0,
    ) -> None:
        if left is None or right is None:
            return
        y0 = bar_top if bar_top > 0 else 0
        y1 = overlay.shape[0] - 1
        center = (left + right) / 2.0
        cv2.line(overlay, (int(left), y0), (int(left), y1), (0, 200, 255), 1)
        cv2.line(overlay, (int(right), y0), (int(right), y1), (0, 200, 255), 1)
        cv2.line(overlay, (int(center), y0), (int(center), y1), (0, 200, 255), 2)

    def blue_mask_for_debug(self, frame_bgr: np.ndarray) -> np.ndarray:
        bar_bgr, _ = self._bar_slice(frame_bgr)
        return self._blue_mask_for_zone(bar_bgr)

    def hook_mask_for_debug(self, frame_bgr: np.ndarray) -> np.ndarray:
        bar_bgr, _ = self._bar_slice(frame_bgr)
        blue_mask = self._blue_mask(bar_bgr)
        return self._hook_mask(bar_bgr, blue_mask)
