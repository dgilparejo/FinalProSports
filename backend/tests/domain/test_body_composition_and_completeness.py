# -*- coding: utf-8 -*-
"""Domain tests (S3): US Navy body fat (men from waist/neck/height; women need the hip -> declared None), BMI, frame size from the wrist,
age from the birth date, and the completeness indicator that separates ALGORITHM INPUTS from RECORD fields."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.domain.composition.policy.body_composition_policy import bmi, estimate, frame_size, us_navy_body_fat  # noqa: E402
from finalprosports.domain.composition.policy.profile_completeness_policy import ALGORITHM_INPUTS, RECORD_FIELDS, completeness, label  # noqa: E402
from finalprosports.domain.model import ClientProfile, Goal, Restriction, RestrictionKind  # noqa: E402
from finalprosports.domain.model.client_record import ClientRecord, DietPreferences, Identification, MedicalHistory, Physiology, Somatotype, SportsProfile  # noqa: E402


def test_us_navy_men_and_women():
    fat, note = us_navy_body_fat("M", 178, 85, 38)
    assert note is None and 14 < fat < 20, (fat, note)                       # textbook value ~17 %
    fat_w, note_w = us_navy_body_fat("F", 165, 72, 33)
    assert fat_w is None and "cadera" in note_w                              # the sheet has no hip: declared, not guessed
    fat_w2, _ = us_navy_body_fat("F", 165, 72, 33, hip_cm=96)
    assert 20 < fat_w2 < 32, fat_w2
    assert us_navy_body_fat("M", 178, 30, 38) == (None, "cintura debe ser mayor que cuello")
    assert us_navy_body_fat(None, 178, 85, 38)[0] is None


def test_bmi_and_frame_size():
    assert bmi(80, 178) == 25.2 and bmi(None, 178) is None
    idx, hint = frame_size("M", 178, 16.5)
    assert idx == 10.79 and hint is Somatotype.ECTOMORPH
    assert frame_size("M", 178, 19.0)[1] is Somatotype.ENDOMORPH and frame_size("M", 178, 17.8)[1] is Somatotype.MESOMORPH
    assert frame_size("F", 165, 14.5)[1] is Somatotype.ECTOMORPH
    e = estimate("M", 178, 80, 85, 38, 17.8)
    assert e.body_fat_method == "us_navy" and e.bmi == 25.2 and e.somatotype_hint is Somatotype.MESOMORPH


def test_age_from_birth_date():
    r = ClientRecord("X", "p", Identification(birth_date=date(1990, 8, 27)))
    assert r.age_on(date(2026, 8, 26)) == 35 and r.age_on(date(2026, 8, 27)) == 36
    assert ClientRecord("X", "p").age_on(date(2026, 8, 26)) is None


def test_completeness_separates_algorithm_inputs_from_record():
    empty = ClientProfile("X", "p", None, None, None, None)
    c = completeness(empty, None)
    assert c.algorithm_present == () and len(c.algorithm_missing) == len(ALGORITHM_INPUTS) and c.record_ratio == 0.0
    full_profile = ClientProfile("X", "p", "M", 30, 178, 4, goal=Goal.VOLUME, restrictions=(Restriction(RestrictionKind.LACTOSE),), sport="crossfit",
                                 disliked_food_ids=(12,), owned_supplement_ids=(7,))
    c2 = completeness(full_profile, None)
    assert c2.algorithm_ratio == 1.0 and c2.record_ratio == 0.0            # the engine has everything; the record is empty
    record = ClientRecord("X", "p", Identification("Nombre Ficticio", date(1996, 1, 1), None, None),
                          Physiology(date(2026, 8, 1), 80, 178, 17.5, 85, 38, None, Somatotype.MESOMORPH), MedicalHistory("ninguna", "lactosa", None, None),
                          DietPreferences("pollo", "pescado azul", None, False, False), SportsProfile(5, "crossfit", "—", "volumen", "9-18", "19-20", "creatina", None, "Garmin"))
    c3 = completeness(ClientProfile("X", "p", "M", 30, 178, 4, goal=Goal.VOLUME), record)
    assert "restrictions" in c3.algorithm_present                          # the medical block was filled: restrictions are informed
    assert "disliked_foods" in c3.algorithm_present and "supplements_owned" in c3.algorithm_present and "sport" in c3.algorithm_present
    assert set(c3.record_missing) == {"phone", "email", "injuries", "surgeries", "food_vices", "first_diet_notes"}
    assert label("wrist_cm") == "muñeca" and len(RECORD_FIELDS) == 25


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
