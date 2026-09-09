# -*- coding: utf-8 -*-
"""Application test (S9): a portfolio client is registered BY NAME; the key is a UUID the use case assigns (or a deterministic one for
demos); the identity goes to the record, the age is derived from the birth date, and the engine's profile never carries the name."""
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from finalprosports.application.usecase.client.register_client_use_case import RegisterClientUseCase, age_on  # noqa: E402
from finalprosports.domain.model import ClientProfile, Goal, Restriction, RestrictionKind  # noqa: E402
from finalprosports.domain.model.client_profile import is_corpus_code, is_portfolio_key  # noqa: E402
from finalprosports.domain.model.client_record import Identification  # noqa: E402


class FakeClients:
    def __init__(self):
        self.rows = {}

    def get(self, pid, key):
        return self.rows.get(key)

    def save(self, profile):
        self.rows[profile.client_code] = profile
        return profile


class FakeRecords:
    def __init__(self):
        self.rows = {}

    def get(self, pid, key):
        return self.rows.get(key)

    def save(self, record):
        self.rows[record.client_code] = record
        return record

    def list_identifications(self, pid):
        return {k: r.identification for k, r in self.rows.items()}


def draft(age: int | None = None) -> ClientProfile:
    return ClientProfile(client_code="whatever the adapter put here", professional_id="p", sex="F", age=age, height_cm=166, activity_level=3, goal=Goal.FAT_LOSS,
                         restrictions=(Restriction(RestrictionKind.LACTOSE),), has_intolerances=True)


def test_register_assigns_a_uuid_key_and_writes_the_identity_to_the_record_only():
    clients, records = FakeClients(), FakeRecords()
    uc = RegisterClientUseCase(clients, records)
    saved = uc.register(draft(), Identification("  Nora Ficticia Demo ", date(1992, 3, 14), "+34 000 000 001", None), today=date(2026, 8, 27))
    assert is_portfolio_key(saved.client_code) and uuid.UUID(saved.client_code).version == 4
    assert saved.age == 34 and saved.is_corpus_case is False and saved.goal is Goal.FAT_LOSS
    assert clients.rows[saved.client_code] is saved
    record = records.rows[saved.client_code]
    assert record.identification.full_name == "Nora Ficticia Demo" and record.identification.birth_date == date(1992, 3, 14)
    assert "Nora" not in repr(saved)                                                   # the engine's profile never carries the name
    assert records.list_identifications("p")[saved.client_code].full_name == "Nora Ficticia Demo"


def test_deterministic_key_for_demos_and_age_kept_when_no_birth_date():
    uc = RegisterClientUseCase(FakeClients(), FakeRecords())
    key = str(uuid.uuid5(uuid.NAMESPACE_URL, "demo"))
    saved = uc.register(draft(age=41), Identification("Enzo Ficticio Demo"), client_id=key)
    assert saved.client_code == key and saved.age == 41


def test_register_refuses_missing_name_and_non_uuid_keys():
    uc = RegisterClientUseCase(FakeClients(), FakeRecords())
    for bad in (Identification(None), Identification(" "), Identification("A")):
        try:
            uc.register(draft(), bad)
        except ValueError:
            pass
        else:
            raise AssertionError("a client without a name was registered")
    for key in ("DEMO_ALFA", "CLIENTE_126", "not-a-uuid"):
        try:
            uc.register(draft(), Identification("Nora Ficticia Demo"), client_id=key)
        except ValueError:
            pass
        else:
            raise AssertionError(f"a non-UUID key was accepted: {key}")


def test_key_predicates_separate_corpus_pseudonyms_from_portfolio_keys():
    assert is_corpus_code("CLIENTE_126") and not is_portfolio_key("CLIENTE_126")
    assert is_portfolio_key(str(uuid.uuid4())) and not is_corpus_code(str(uuid.uuid4()))
    assert not is_corpus_code("") and not is_portfolio_key("") and not is_corpus_code("CLIENTE_1266")
    assert age_on(date(2000, 2, 29), date(2026, 2, 28)) == 25 and age_on(date(2000, 2, 29), date(2026, 3, 1)) == 26 and age_on(None, date(2026, 1, 1)) is None


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)):
        try:
            fn(); print(f"PASS {name}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
