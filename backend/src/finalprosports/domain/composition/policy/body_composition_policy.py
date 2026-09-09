"""Body-composition estimates (S3), pure functions. They explain why the intake sheet asks for exactly wrist, waist, neck and height.

  us_navy_body_fat   Hodgdon & Beckett (1984) circumference method used by the US Navy, body density -> Siri, CENTIMETRE form:
                       men    % fat = 495 / (1.0324 − 0.19077·log10(waist − neck) + 0.15456·log10(height)) − 450
                       women  % fat = 495 / (1.29579 − 0.35004·log10(waist + hip − neck) + 0.22100·log10(height)) − 450
                     Women need the hip; the professional's sheet does not ask for it, so the estimate is None for women without hip
                     (declared, not guessed).
  bmi                weight / height²
  frame_size         height / wrist ratio (body frame index): the wrist is what the sheet uses to type the physiognomy
                     (ectomorfo = small frame, mesomorfo = medium, endomorfo = large). Sex-specific cut-offs of the index.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from finalprosports.domain.model.client_record import Somatotype


@dataclass(frozen=True)
class BodyCompositionEstimate:
    body_fat_pct: float | None
    body_fat_method: str | None            # 'us_navy' | None
    body_fat_note: str | None              # why it could not be estimated
    bmi: float | None
    frame_index: float | None              # height / wrist
    somatotype_hint: Somatotype | None


def us_navy_body_fat(sex: str | None, height_cm: float | None, waist_cm: float | None, neck_cm: float | None, hip_cm: float | None = None) -> tuple[float | None, str | None]:
    if sex not in ("M", "F") or not height_cm or not waist_cm or not neck_cm:
        return None, "faltan sexo, altura, cintura o cuello"
    if sex == "M":
        if waist_cm <= neck_cm:
            return None, "cintura debe ser mayor que cuello"
        fat = 495.0 / (1.0324 - 0.19077 * math.log10(waist_cm - neck_cm) + 0.15456 * math.log10(height_cm)) - 450.0
    else:
        if not hip_cm:
            return None, "el método US Navy necesita la cadera en mujeres (la hoja del profesional no la pide)"
        if waist_cm + hip_cm <= neck_cm:
            return None, "cintura + cadera debe ser mayor que cuello"
        fat = 495.0 / (1.29579 - 0.35004 * math.log10(waist_cm + hip_cm - neck_cm) + 0.22100 * math.log10(height_cm)) - 450.0
    return round(max(0.0, min(fat, 70.0)), 1), None


def bmi(weight_kg: float | None, height_cm: float | None) -> float | None:
    if not weight_kg or not height_cm:
        return None
    return round(weight_kg / (height_cm / 100) ** 2, 1)


def frame_size(sex: str | None, height_cm: float | None, wrist_cm: float | None) -> tuple[float | None, Somatotype | None]:
    if not height_cm or not wrist_cm or sex not in ("M", "F"):
        return None, None
    r = round(height_cm / wrist_cm, 2)
    small, large = (10.4, 9.6) if sex == "M" else (11.0, 10.1)
    hint = Somatotype.ECTOMORPH if r > small else Somatotype.ENDOMORPH if r < large else Somatotype.MESOMORPH
    return r, hint


def estimate(sex: str | None, height_cm: float | None, weight_kg: float | None, waist_cm: float | None, neck_cm: float | None,
             wrist_cm: float | None, hip_cm: float | None = None) -> BodyCompositionEstimate:
    fat, note = us_navy_body_fat(sex, height_cm, waist_cm, neck_cm, hip_cm)
    idx, hint = frame_size(sex, height_cm, wrist_cm)
    return BodyCompositionEstimate(fat, "us_navy" if fat is not None else None, note, bmi(weight_kg, height_cm), idx, hint)
