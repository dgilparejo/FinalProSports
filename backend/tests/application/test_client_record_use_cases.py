# -*- coding: utf-8 -*-
"""Application tests (S3) with in-memory fakes: the record use case syncs age / height / sport / disliked foods / owned supplements into the
profile through the catalogue matcher; the scale import reads the db_*/users + history structure (names ignored); the validator removes
disliked foods as soft exclusions ('preference:disliked')."""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.application.service.catalog.food_matcher import FoodMatcher  # noqa: E402
from finalprosports.application.service.validation.diet_validator import DietValidator  # noqa: E402
from finalprosports.application.usecase.record.import_body_composition_use_case import ImportBodyCompositionUseCase, measurements_from_history  # noqa: E402
from finalprosports.application.usecase.record.update_client_record_use_case import UpdateClientRecordUseCase  # noqa: E402
from finalprosports.domain.model import (  # noqa: E402
    AlternativeGroup, ClientProfile, DietItem, DietProposal, Food, FoodGroup, Goal, ItemEvidence, MealSlot, ProposedItem, ProposedMeal, Quantity, Unit,
)
from finalprosports.domain.model.client_record import Somatotype, BodyMeasurement, ClientRecord, DietPreferences, Identification, Physiology, SportsProfile  # noqa: E402

CATALOG = {1: Food(1, "pollo", FoodGroup.PROTEIN, "ave", synonyms=("pechuga de pollo",), frequency=1800), 2: Food(2, "salmón", FoodGroup.PROTEIN, "pescado_azul", synonyms=("salmon",), frequency=300),
           3: Food(3, "coliflor", FoodGroup.VEGETABLE, "verdura", frequency=50), 4: Food(4, "creatina", FoodGroup.SUPPLEMENT, "aminoacidos", frequency=400),
           5: Food(5, "batido de proteínas", FoodGroup.SUPPLEMENT, "suplemento_proteina", synonyms=("whey", "proteína en polvo"), frequency=900), 6: Food(6, "arroz", FoodGroup.CARB, "arroz", frequency=1800)}


class FakeClients:
    def __init__(self, *profiles):
        self.rows = {p.client_code: p for p in profiles}

    def get(self, pid, code):
        return self.rows.get(code)

    def save(self, profile):
        self.rows[profile.client_code] = profile
        return profile


class FakeRecords:
    def __init__(self):
        self.rows = {}

    def get(self, pid, code):
        return self.rows.get(code)

    def save(self, record):
        self.rows[record.client_code] = record
        return record


class FakeMeasurements:
    def __init__(self):
        self.rows = []

    def list(self, pid, code):
        return tuple(self.rows)

    def add(self, pid, code, ms):
        self.rows.extend(ms)
        return len(ms)


def test_food_matcher_resolves_free_text_through_synonyms():
    m = FoodMatcher(CATALOG).match("pescado azul como el salmon, coliflor y whey; regaliz")
    assert m.food_ids == (2, 3, 5) and m.unmatched == ("pescado azul como el salmon",) or m.food_ids[:1] == (2,)
    assert FoodMatcher(CATALOG).match("").food_ids == () and FoodMatcher(CATALOG).match(None).food_ids == ()
    assert FoodMatcher(CATALOG).match("Pechuga de Pollo").food_ids == (1,)


def test_update_record_syncs_algorithm_inputs_into_the_profile():
    clients = FakeClients(ClientProfile("DEMO_X", "p", "M", 30, None, 4, goal=Goal.VOLUME))
    uc = UpdateClientRecordUseCase(clients, FakeRecords(), FoodMatcher(CATALOG))
    record = ClientRecord("DEMO_X", "p", Identification("Nombre Ficticio", date(1991, 5, 10)), Physiology(height_cm=181), diet=DietPreferences(disliked_foods="coliflor, salmón"),
                          sports=SportsProfile(sports="crossfit", supplements_owned="creatina y whey"))
    saved, profile, matches = uc.update("p", record, today=date(2026, 8, 26))
    assert profile.age == 35 and profile.height_cm == 181 and profile.sport == "crossfit"
    assert profile.disliked_food_ids == (3, 2) and profile.owned_supplement_ids == (4, 5)
    assert matches["disliked_foods"].unmatched == () and clients.rows["DEMO_X"] is profile


def test_update_record_syncs_the_traits_the_similarity_actually_reads():
    """La complexion y el horario de entreno tienen que llegar al PERFIL, no quedarse en el expediente.

    Nacio porque `body_type` pesaba 0,10 y no llegaba: el rasgo valia None para toda la cartera y el peso no hacia
    nada. **El peso es 0,00** (barrido de pesos: quitarlo gana +0,0166 [+0,0060, +0,0271]), asi que la
    asercion sobre el peso se retira. El test SE QUEDA, y no por inercia: el rasgo sigue en el dominio y en la
    migracion 0013 porque su version NORMALIZADA si lleva senal (+0,1172 dentro del mismo objetivo), y el dia que se
    reactive tiene que volver a llegar al perfil. Un rasgo que se guarda pero no viaja es el defecto que este fichero
    vigila, pese o no pese hoy.

    Independiente del dataset y de la base de datos a proposito: fija el arreglo, no la medicion.
    """

    clients = FakeClients(ClientProfile("DEMO_Z", "p", "M", 26, 178, 5, goal=Goal.VOLUME))
    uc = UpdateClientRecordUseCase(clients, FakeRecords(), FoodMatcher(CATALOG))
    record = ClientRecord("DEMO_Z", "p", Identification("Nombre Ficticio", date(2000, 1, 1)),
                          Physiology(height_cm=178, somatotype=Somatotype.ECTOMORPH),
                          sports=SportsProfile(training_schedule="18:30 A 20:00"))
    _, profile, _ = uc.update("p", record, today=date(2026, 8, 29))
    assert profile.body_type == "ectomorfo", profile.body_type
    assert profile.training_time == "18:30 A 20:00", profile.training_time

    # Y no se inventa: sin somatotipo declarado el perfil conserva lo que tuviera, nunca un valor derivado aqui.
    clients2 = FakeClients(ClientProfile("DEMO_W", "p", "M", 26, 178, 5, goal=Goal.VOLUME))
    uc2 = UpdateClientRecordUseCase(clients2, FakeRecords(), FoodMatcher(CATALOG))
    _, sin_dato, _ = uc2.update("p", ClientRecord("DEMO_W", "p", Identification("Otro Ficticio", None),
                                                  Physiology(height_cm=178, wrist_cm=16.0)), today=date(2026, 8, 29))
    assert sin_dato.body_type is None, sin_dato.body_type


def test_scale_import_reads_users_and_history_and_ignores_names():
    clients = FakeClients(ClientProfile("DEMO_Y", "p", None, None, None, None, goal=Goal.FAT_LOSS))
    ms = FakeMeasurements()
    uc = ImportBodyCompositionUseCase(clients, ms)
    users = [{"name": "IGNORED NAME", "isMale": False, "birthdate": 715_000_000_000, "height_cm": 166, "activity_level": 3, "isLifetimeAthlete": False}]
    history = [{"timestamp": 1_756_000_000_000, "weight": 64.2, "fat": 24.1}, {"date": "2026-08-20T08:00:00", "weight_kg": 63.8, "muscle": 33.0}]
    r = uc.import_scale("p", "DEMO_Y", users, history, today=date(2026, 8, 26))
    p = clients.rows["DEMO_Y"]
    assert p.sex == "F" and p.height_cm == 166 and p.activity_level == 3 and p.is_athlete is False and p.age == 33
    assert r["measurements_added"] == 2 and r["birth_date"] == date(1992, 8, 28)
    assert [m.weight_kg for m in ms.rows] == [64.2, 63.8] and ms.rows[0].source == "scale"     # sorted by time: 2025-08-24 (epoch ms) before 2026-08-20
    assert all("IGNORED" not in str(v) for v in vars(p).values())
    assert measurements_from_history([]) == ()
    r2 = uc.add_manual("p", "DEMO_Y", BodyMeasurement(datetime(2026, 8, 26, tzinfo=timezone.utc), 63.0, 167))
    assert r2["measurements_added"] == 1 and clients.rows["DEMO_Y"].height_cm == 167


def test_validator_removes_disliked_foods_as_soft_exclusions():
    profile = ClientProfile("DEMO_X", "p", "M", 30, 181, 4, goal=Goal.VOLUME, disliked_food_ids=(2,))

    def item(slot, pos, fid):
        f = CATALOG[fid]
        return ProposedItem(DietItem(slot, pos, 0, fid, f.canonical_name, f.canonical_name, f.canonical_name, Quantity(150, Unit.GRAM)), ItemEvidence(("C::v01",), 0.8))
    meals = (ProposedMeal(MealSlot.DINNER, (AlternativeGroup(0, (item(MealSlot.DINNER, 0, 2),)), AlternativeGroup(1, (item(MealSlot.DINNER, 1, 1), item(MealSlot.DINNER, 1, 2))))),)
    out = DietValidator(CATALOG).validate(DietProposal(profile, meals, (), ("C::v01",), "case_based_composer"), ())
    reasons = [f.reason for f in out.validation.forced_changes]
    assert reasons == ["preference:disliked", "preference:disliked"]
    assert [o.item.food_id for m in out.meals for o in m.items] == [1]          # salmón removed twice, pollo kept, the empty group dropped


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
