from __future__ import annotations

import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import cv2
import mss
import numpy as np

STASH_ROUTE_DIR = Path(__file__).resolve().parent
DEBUG_OCR_DIR = STASH_ROUTE_DIR / "debug_ocr"

# ROI do nome do item abaixo do centro do slot (pixels relativos ao clique)
DEFAULT_LABEL_OFFSET = {
    "left": -55,
    "top": 48,
    "width": 110,
    "height": 36,
}

# Variantes se o offset padrao nao pegar o texto
LABEL_OFFSET_VARIANTS = [
    DEFAULT_LABEL_OFFSET,
    {"left": -55, "top": 38, "width": 110, "height": 36},
    {"left": -55, "top": 58, "width": 110, "height": 40},
    {"left": -65, "top": 50, "width": 130, "height": 40},
]

_tesseract_ready: bool | None = None
_tesseract_error: str | None = None


def get_stash_inventory_cfg(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("stash_inventory", {})


def grab_screen(*, sct: Any | None = None, monitor_index: int = 1) -> np.ndarray:
    if sct is not None:
        monitor = sct.monitors[monitor_index]
        return np.array(sct.grab(monitor))[:, :, :3]
    with mss.MSS() as new_sct:
        monitor = new_sct.monitors[monitor_index]
        return np.array(new_sct.grab(monitor))[:, :, :3]


def slot_center(slot: dict[str, Any]) -> tuple[int, int]:
    return int(slot["x"]), int(slot["y"])


def label_roi_for_slot(slot: dict[str, Any], offsets: dict[str, int] | None = None) -> dict[str, int]:
    off = offsets or DEFAULT_LABEL_OFFSET
    x, y = slot_center(slot)
    return {
        "left": x + int(off["left"]),
        "top": y + int(off["top"]),
        "width": int(off["width"]),
        "height": int(off["height"]),
    }


def crop_roi(frame: np.ndarray, roi: dict[str, int]) -> np.ndarray:
    h, w = frame.shape[:2]
    left = max(0, int(roi["left"]))
    top = max(0, int(roi["top"]))
    right = min(w, left + int(roi["width"]))
    bottom = min(h, top + int(roi["height"]))
    if right <= left or bottom <= top:
        return np.empty((0, 0, 3), dtype=frame.dtype)
    return frame[top:bottom, left:right]


def normalize_species_text(text: str) -> str:
    cleaned = text.lower()
    cleaned = cleaned.replace("•", " ").replace("·", " ")
    cleaned = re.sub(r"[^a-z\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def match_species_exact(text: str, known: list[str]) -> str | None:
    normalized = normalize_species_text(text)
    if not normalized:
        return None
    ordered = sorted(known, key=len, reverse=True)
    tokens = normalized.split()
    for species in ordered:
        if species in tokens:
            return species
    for species in ordered:
        if species in normalized:
            return species
    compact = normalized.replace(" ", "")
    for species in ordered:
        if species in compact:
            return species
    return None


def match_species(text: str, known: list[str]) -> str | None:
    exact = match_species_exact(text, known)
    if exact:
        return exact
    return fuzzy_match_species(text, known)


def _species_match_score(ocr: str, species: str) -> float:
    norm = normalize_species_text(ocr)
    if not norm:
        return 0.0
    compact = norm.replace(" ", "")
    scores = [
        SequenceMatcher(None, compact, species).ratio(),
        SequenceMatcher(None, norm, species).ratio(),
    ]
    for token in norm.split():
        if len(token) >= 4:
            scores.append(SequenceMatcher(None, token, species).ratio())
            if species.startswith(token[:4]):
                scores.append(0.75)
            if token.startswith(species[:4]):
                scores.append(0.7)
    aliases = SPECIES_OCR_ALIASES.get(species, ())
    for alias in aliases:
        if alias in compact or alias in norm:
            scores.append(0.7)
    return max(scores)


def fuzzy_match_species(text: str, known: list[str], *, threshold: float = 0.68) -> str | None:
    norm = normalize_species_text(text)
    raw_tokens = norm.split()
    if len(raw_tokens) >= 2:
        for token in raw_tokens:
            if len(token) < 3:
                continue
            scored = [(species, SequenceMatcher(None, token, species).ratio()) for species in known]
            scored.sort(key=lambda item: item[1], reverse=True)
            if scored[0][1] >= 0.48 and (
                len(scored) < 2 or scored[0][1] - scored[1][1] >= 0.12
            ):
                return scored[0][0]

    compact = norm.replace(" ", "")
    if len(compact) < 5:
        return None

    scored = [(species, _species_match_score(text, species)) for species in known]
    scored.sort(key=lambda item: item[1], reverse=True)
    if not scored or scored[0][1] < threshold:
        return None
    if len(scored) >= 2 and scored[0][1] - scored[1][1] < 0.14:
        return None
    return scored[0][0]


def _ocr_species_preprocessed_variants(crop_bgr: np.ndarray) -> list[np.ndarray]:
    scaled_bgr = cv2.resize(crop_bgr, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(scaled_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 5, 60, 60)

    variants: list[np.ndarray] = [gray]

    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)

    for threshold in (110, 140, 170):
        _, bright = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
        variants.append(bright)

    light = cv2.inRange(gray, 130, 255)
    variants.append(light)

    hsv = cv2.cvtColor(scaled_bgr, cv2.COLOR_BGR2HSV)
    text_mask = cv2.inRange(hsv, (0, 0, 150), (180, 80, 255))
    variants.append(text_mask)

    return variants


SPECIES_OCR_ALIASES: dict[str, tuple[str, ...]] = {
    "megalodon": ("meg", "mega", "galod", "lodon", "megal"),
}


SPECIES_OCR_CONFIGS = [
    "--psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyz",
    "--psm 8 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyz",
    "--psm 7",
    "--psm 13",
]


def read_species_from_crop(
    crop_bgr: np.ndarray,
    known_species: list[str],
) -> tuple[str | None, str | None]:
    ok, _err = ensure_tesseract()
    if not ok or crop_bgr.size == 0:
        return None, None

    import pytesseract
    from PIL import Image

    best_text: str | None = None
    ocr_candidates: list[str] = []
    crop = np.ascontiguousarray(crop_bgr)

    for variant in _ocr_species_preprocessed_variants(crop):
        for cfg in SPECIES_OCR_CONFIGS:
            try:
                raw = pytesseract.image_to_string(Image.fromarray(variant), config=cfg)
            except Exception:
                continue
            if not raw.strip():
                continue
            cleaned = normalize_species_text(raw)
            if cleaned:
                ocr_candidates.append(cleaned)
            species = match_species_exact(raw, known_species)
            if species:
                return species, cleaned or raw.strip()

    unique_candidates = list(dict.fromkeys(ocr_candidates))
    for text in unique_candidates:
        species = fuzzy_match_species(text, known_species)
        if species:
            return species, text
        if best_text is None or len(text) > len(best_text):
            best_text = text

    return None, best_text


def ensure_tesseract(*, force: bool = False) -> tuple[bool, str | None]:
    global _tesseract_ready, _tesseract_error
    if force:
        _tesseract_ready = None
        _tesseract_error = None
    if _tesseract_ready is not None:
        return _tesseract_ready, _tesseract_error

    try:
        import pytesseract
    except ImportError:
        _tesseract_ready = False
        _tesseract_error = (
            "pytesseract nao instalado. Rode: pip install -r requirements-stash.txt"
        )
        return _tesseract_ready, _tesseract_error

    for candidate in (
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ):
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            break

    try:
        pytesseract.get_tesseract_version()
        _tesseract_ready = True
        _tesseract_error = None
    except Exception as exc:
        _tesseract_ready = False
        _tesseract_error = (
            "Tesseract OCR nao encontrado. Instale: "
            "https://github.com/UB-Mannheim/tesseract/wiki"
            f" ({exc})"
        )

    return _tesseract_ready, _tesseract_error


def _ocr_preprocessed_variants(crop_bgr: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)

    variants: list[np.ndarray] = []

    _, otsu = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)

    _, bright = cv2.threshold(scaled, 175, 255, cv2.THRESH_BINARY)
    variants.append(bright)

    inverted = cv2.bitwise_not(otsu)
    variants.append(inverted)

    bright_mask = cv2.inRange(scaled, 160, 255)
    variants.append(bright_mask)

    return variants


def read_text_ocr(
    frame_bgr: np.ndarray,
    roi: dict[str, int],
    *,
    ocr_configs: list[str] | None = None,
    normalize: Any | None = normalize_species_text,
) -> str | None:
    ok, err = ensure_tesseract()
    if not ok:
        return None

    crop = crop_roi(frame_bgr, roi)
    if crop.size == 0:
        return None

    import pytesseract

    configs = ocr_configs or [
        "--psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "--psm 8 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
        "--psm 7",
    ]

    best = ""
    for variant in _ocr_preprocessed_variants(crop):
        for cfg in configs:
            try:
                text = pytesseract.image_to_string(variant, config=cfg)
            except Exception:
                continue
            cleaned = normalize(text) if normalize else text.strip()
            if len(cleaned) > len(best):
                best = cleaned

    return best if best else None


def normalize_weight_text(text: str) -> str:
    cleaned = text.replace(",", ".")
    cleaned = re.sub(r"[^0-9./\sKGkg]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _ocr_weight_preprocessed_variants(crop_bgr: np.ndarray) -> list[np.ndarray]:
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC)
    hsv = cv2.cvtColor(
        cv2.resize(crop_bgr, None, fx=4.0, fy=4.0, interpolation=cv2.INTER_CUBIC),
        cv2.COLOR_BGR2HSV,
    )

    variants: list[np.ndarray] = [scaled]

    _, otsu = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(otsu)

    for threshold in (95, 120, 150, 175):
        _, bright = cv2.threshold(scaled, threshold, 255, cv2.THRESH_BINARY)
        variants.append(bright)

    yellow = cv2.inRange(hsv, (12, 50, 80), (45, 255, 255))
    gold = cv2.inRange(hsv, (8, 20, 50), (50, 255, 220))
    variants.append(cv2.bitwise_or(yellow, gold))
    variants.append(yellow)

    return variants


def sanitize_current_weight(current: float, weight_max_kg: float) -> float:
    if current < 0:
        return 0.0
    if current > weight_max_kg * 1.05:
        return weight_max_kg
    return current


def parse_weight_text(text: str, weight_max_kg: float) -> tuple[float, float] | None:
    """Extrai peso atual. Maximo vem do config (80 kg) — OCR erra o '/80' como '806'."""
    if not text or not text.strip():
        return None

    candidates = [
        text.replace(",", "."),
        normalize_weight_text(text),
        re.sub(r"\s+", "", text.replace(",", ".")),
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)

        # Prioriza numero ANTES da barra (peso atual)
        before_slash = re.search(r"(\d+(?:\.\d+)?)\s*/", candidate)
        if before_slash:
            current = sanitize_current_weight(float(before_slash.group(1)), weight_max_kg)
            return current, weight_max_kg

        slash_match = re.search(
            r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)",
            candidate,
        )
        if slash_match:
            current = sanitize_current_weight(float(slash_match.group(1)), weight_max_kg)
            return current, weight_max_kg

        nums = re.findall(r"\d+(?:\.\d+)?", candidate)
        if nums:
            current = sanitize_current_weight(float(nums[0]), weight_max_kg)
            return current, weight_max_kg

    return None


WEIGHT_OCR_CONFIGS = [
    "--psm 7 -c tessedit_char_whitelist=0123456789./ KGkg",
    "--psm 8 -c tessedit_char_whitelist=0123456789./ KGkg",
    "--psm 7",
]


_weight_ocr_last_error: str | None = None


def weight_ocr_last_error() -> str | None:
    return _weight_ocr_last_error


def read_weight_from_crop(
    crop_bgr: np.ndarray,
    *,
    weight_max_kg: float,
) -> tuple[tuple[float, float] | None, str | None]:
    global _weight_ocr_last_error
    _weight_ocr_last_error = None

    ok, tess_err = ensure_tesseract()
    if not ok:
        _weight_ocr_last_error = tess_err
        return None, None

    if crop_bgr.size == 0:
        _weight_ocr_last_error = "recorte do peso vazio"
        return None, None

    import pytesseract
    from PIL import Image

    configs = [
        *WEIGHT_OCR_CONFIGS,
        "--psm 7",
        "--psm 8",
        "--psm 13",
    ]

    best_label: str | None = None
    crop = np.ascontiguousarray(crop_bgr)

    for variant in _ocr_weight_preprocessed_variants(crop):
        for cfg in configs:
            try:
                pil = Image.fromarray(variant)
                raw = pytesseract.image_to_string(pil, config=cfg)
            except Exception as exc:
                _weight_ocr_last_error = str(exc)
                continue
            if not raw.strip():
                continue
            parsed = parse_weight_text(raw, weight_max_kg)
            if parsed:
                label = normalize_weight_text(raw) or raw.strip()
                return parsed, label
            cleaned = normalize_weight_text(raw)
            if cleaned and (best_label is None or len(cleaned) > len(best_label)):
                best_label = cleaned

    if best_label:
        parsed = parse_weight_text(best_label, weight_max_kg)
        if parsed:
            return parsed, best_label

    if _weight_ocr_last_error is None:
        _weight_ocr_last_error = "nenhum texto reconhecido no recorte do peso"
    return None, best_label


def read_weight_from_frame(
    frame_bgr: np.ndarray,
    weight_roi: dict[str, int],
    *,
    weight_max_kg: float,
) -> tuple[tuple[float, float] | None, str | None]:
    crop = crop_roi(frame_bgr, weight_roi)
    return read_weight_from_crop(crop, weight_max_kg=weight_max_kg)


def read_weight_text_ocr(
    frame_bgr: np.ndarray,
    roi: dict[str, int],
    *,
    weight_max_kg: float = 80.0,
) -> str | None:
    _parsed, label = read_weight_from_frame(frame_bgr, roi, weight_max_kg=weight_max_kg)
    return label


def ocr_status_message() -> str | None:
    ok, err = ensure_tesseract()
    return err if not ok else None


def detect_species_in_slot(
    frame: np.ndarray,
    slot: dict[str, Any],
    known_species: list[str],
    *,
    label_offset: dict[str, int] | None = None,
    debug: bool = False,
    slot_index: int | None = None,
) -> tuple[str | None, str | None]:
    """Retorna (especie, texto_ocr)."""
    offsets_list = [label_offset] if label_offset else []
    for variant in LABEL_OFFSET_VARIANTS:
        if variant not in offsets_list:
            offsets_list.append(variant)

    best_species: str | None = None
    best_text: str | None = None

    for off in offsets_list:
        roi = label_roi_for_slot(slot, off)
        crop = crop_roi(frame, roi)
        species, text = read_species_from_crop(crop, known_species)
        if debug and slot_index is not None:
            _save_debug_crop(frame, roi, slot_index, text)
        if species:
            return species, text
        if best_text is None and text:
            best_text = text

    return best_species, best_text


def _save_debug_crop(
    frame: np.ndarray,
    roi: dict[str, int],
    slot_index: int | str,
    text: str | None,
) -> None:
    DEBUG_OCR_DIR.mkdir(parents=True, exist_ok=True)
    crop = crop_roi(frame, roi)
    if crop.size == 0:
        return
    if isinstance(slot_index, str):
        label = re.sub(r"[^a-z0-9._-]+", "_", (text or "none").lower())
        prefix = slot_index
    else:
        label = normalize_species_text(text or "none")
        prefix = f"pocket_{slot_index}"
    path = DEBUG_OCR_DIR / f"{prefix}_{label}.png"
    cv2.imwrite(str(path), crop)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    _, otsu = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    cv2.imwrite(str(DEBUG_OCR_DIR / f"{prefix}_{label}_otsu.png"), otsu)


def read_inventory_weight(
    frame: np.ndarray,
    weight_roi: dict[str, int],
    *,
    weight_max_kg: float,
    debug: bool = False,
) -> tuple[float, float] | None:
    parsed, label = read_weight_from_frame(frame, weight_roi, weight_max_kg=weight_max_kg)
    if debug:
        _save_debug_crop(frame, weight_roi, "weight", label)
    return parsed


def read_inventory_weight_retry(
    cfg: dict[str, Any],
    *,
    max_attempts: int | None = None,
    interval_ms: int | None = None,
    debug: bool = False,
    sct: Any | None = None,
) -> tuple[np.ndarray, tuple[float, float] | None, str | None]:
    """Captura tela varias vezes ate o OCR ler o peso (UI pode demorar a abrir)."""
    weight_roi = cfg.get("weight_roi")
    frame = grab_screen(sct=sct)
    if not weight_roi:
        return frame, None, None

    attempts = max(1, int(max_attempts or cfg.get("weight_read_attempts", 8)))
    gap_ms = max(0, int(interval_ms or cfg.get("weight_read_interval_ms", 150)))
    weight_max_kg = float(cfg.get("weight_max_kg", 80.0))
    last_label: str | None = None

    for attempt in range(attempts):
        frame = grab_screen(sct=sct)
        parsed, last_label = read_weight_from_frame(frame, weight_roi, weight_max_kg=weight_max_kg)
        if debug:
            _save_debug_crop(frame, weight_roi, "weight", last_label)
        if parsed:
            return frame, parsed, last_label
        if attempt < attempts - 1 and gap_ms > 0:
            time.sleep(gap_ms / 1000.0)

    return frame, None, last_label


def weight_stash_limit(cfg: dict[str, Any], maximum: float) -> float:
    ratio = float(cfg.get("weight_trigger_ratio", 0.98))
    if maximum > 0:
        return maximum * ratio
    return float(cfg.get("weight_max_kg", 80.0)) * ratio


def inventory_is_full(
    frame: np.ndarray,
    cfg: dict[str, Any],
) -> bool:
    weight_roi = cfg.get("weight_roi")
    if not weight_roi:
        return False
    weights = read_inventory_weight(
        frame,
        weight_roi,
        weight_max_kg=float(cfg.get("weight_max_kg", 80.0)),
    )
    if weights is None:
        return False
    current, maximum = weights
    return current >= weight_stash_limit(cfg, maximum)


def trunk_index_for_species(species: str, trunk_order: list[str]) -> int | None:
    try:
        return trunk_order.index(species)
    except ValueError:
        return None


def validate_inventory_calibration(cfg: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pockets = cfg.get("pocket_slots", [])
    trunk = cfg.get("trunk_slots", [])
    if len(pockets) < 1:
        errors.append("pocket_slots vazio — rode calibrate_inventory.py")
    if len(trunk) < 1:
        errors.append("trunk_slots vazio — rode calibrate_inventory.py")
    if not cfg.get("weight_roi"):
        errors.append("weight_roi ausente — rode calibrate_inventory.py")
    return errors
