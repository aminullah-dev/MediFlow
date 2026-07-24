"""End-to-end tests for the web UI (``mediflow.web``).

These drive real HTTP through Starlette's TestClient against a throwaway data
directory, so they exercise routing, session auth, permission gates, template
rendering and the service layer together — the same path a browser takes.

``MEDIFLOW_DATA_DIR`` is pinned per-test. That is not merely tidiness: the
interpreter may be a Microsoft Store build whose ``%APPDATA%`` writes Windows
silently redirects, and pinning the path keeps a test run from ever touching a
real clinic database.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from mediflow.core.config import Config
from mediflow.core.security import hash_password
from mediflow.data.models.user import User

pytest.importorskip("fastapi", reason="web extras not installed")
from fastapi.testclient import TestClient  # noqa: E402

from mediflow.web.server import create_app  # noqa: E402

PASSWORD = "Amin2026"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIFLOW_DATA_DIR", str(tmp_path))
    application = create_app(Config.bootstrap())
    container = application.state.container
    with container.database.unit_of_work() as session:
        admin = session.query(User).filter_by(username="admin").one()
        admin.password_hash = hash_password(PASSWORD)
        admin.must_change_password = False
    yield application
    container.database.dispose()


@pytest.fixture()
def client(app):
    c = TestClient(app)
    c.post("/login", data={"username": "admin", "password": PASSWORD})
    return c


@pytest.fixture()
def anon(app):
    return TestClient(app)


def _new_patient(client, **over) -> int:
    data = {"first_name": "نادیه", "last_name": "صافی", "gender": "female",
            "approximate_age_years": "41", "blood_group": "B+"}
    data.update(over)
    r = client.post("/patients/new", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text[:400]
    return int(r.headers["location"].rsplit("/", 1)[-1])


# -- auth -------------------------------------------------------------------
def test_healthz_reports_the_resolved_data_dir(anon, tmp_path):
    body = anon.get("/healthz").json()
    assert body["status"] == "ok"
    assert str(tmp_path) in body["data_dir"]


@pytest.mark.parametrize("path", ["/", "/patients", "/appointments", "/reception"])
def test_protected_pages_redirect_when_signed_out(anon, path):
    assert anon.get(path, follow_redirects=False).status_code == 303


def test_bad_password_is_rejected_without_leaking_which_field(anon):
    r = anon.post("/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert "نام کاربری یا رمز عبور نادرست است." in r.text


def test_password_typed_on_the_persian_layout_still_signs_in(anon):
    """The layout recovery in AuthService must reach the web login too."""
    r = anon.post("/login", data={"username": "admin", "password": "َئهد2026"},
                  follow_redirects=False)
    assert r.status_code == 303


def test_sign_out_returns_to_login_and_reprotects(client):
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert client.get("/", follow_redirects=False).status_code == 303


# -- patients ---------------------------------------------------------------
def test_register_then_find_patient(client):
    _new_patient(client, first_name="زهرا", last_name="احمدی", phone="0788111222")
    listing = client.get("/patients").text
    assert "زهرا احمدی" in listing
    assert "زهرا" in client.get("/patients?q=احمدی").text
    assert "زهرا" in client.get("/patients?q=0788111222").text
    assert "پیدا نشد" in client.get("/patients?q=zzzznope").text


def test_national_id_is_hidden_in_the_list_and_revealed_on_detail(client):
    """It is encrypted at rest; only the detail view decrypts it."""
    pid = _new_patient(client, national_id="1401-1234567")
    assert "1401-1234567" not in client.get("/patients").text
    assert "1401-1234567" in client.get(f"/patients/{pid}").text


def test_validation_errors_are_dari_and_keep_what_was_typed(client):
    r = client.post("/patients/new", data={"first_name": "سمیر", "last_name": "نوری",
                                           "gender": "male"})
    assert r.status_code == 400
    assert "تاریخ تولد یا سن تقریبی را وارد کنید." in r.text
    assert "سمیر" in r.text and "نوری" in r.text


def test_patient_can_be_updated_and_deleted(client):
    pid = _new_patient(client)
    client.post(f"/patients/{pid}", data={"first_name": "نادیه", "last_name": "صافی",
                "gender": "female", "approximate_age_years": "41", "phone": "0777999888"},
                follow_redirects=False)
    assert "0777999888" in client.get(f"/patients/{pid}").text
    client.post(f"/patients/{pid}/delete", follow_redirects=False)
    assert "نادیه صافی" not in client.get("/patients").text


# -- appointments and reception ---------------------------------------------
def _book(client, pid, hour=10):
    when = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    r = client.post("/appointments/new",
                    data={"patient_id": str(pid),
                          "scheduled_start": when.strftime("%Y-%m-%dT%H:%M"),
                          "reason": "کنترل قند"},
                    follow_redirects=False)
    assert r.status_code == 303
    import re
    day = when.date().isoformat()
    body = client.get(f"/appointments?day={day}").text
    return int(re.findall(r"/appointments/(\d+)/", body)[-1]), day, body


def test_booking_shows_on_the_day_view(client):
    pid = _new_patient(client)
    _, _, body = _book(client, pid)
    assert "نادیه صافی" in body
    assert "نوبت گرفته" in body


def test_reception_flow_checkin_call_complete(client):
    pid = _new_patient(client)
    aid, day, _ = _book(client, pid)

    client.post(f"/appointments/{aid}/checkin", data={"day": day}, follow_redirects=False)
    board = client.get("/reception").text
    assert "در انتظار" in board
    assert "001" in board, "check-in must issue a queue token"

    client.post(f"/reception/{aid}/call", follow_redirects=False)
    assert "در حال معاینه" in client.get("/reception").text

    client.post(f"/reception/{aid}/complete", follow_redirects=False)
    assert "تکمیل‌شده امروز" in client.get("/reception").text


def test_appointment_can_be_cancelled(client):
    pid = _new_patient(client)
    aid, day, _ = _book(client, pid)
    client.post(f"/appointments/{aid}/cancel", data={"day": day}, follow_redirects=False)
    assert "لغو شده" in client.get(f"/appointments?day={day}").text


def test_booking_without_a_patient_is_refused_in_dari(client):
    when = datetime.now().strftime("%Y-%m-%dT%H:%M")
    r = client.post("/appointments/new", data={"patient_id": "", "scheduled_start": when})
    assert r.status_code == 400
    assert "بیمار را انتخاب کنید." in r.text


# -- medical records --------------------------------------------------------
def test_allergy_round_trip_with_canonical_severity(client):
    """Displayed in Dari, stored as mild/moderate/severe like the desktop build."""
    pid = _new_patient(client)
    client.post(f"/patients/{pid}/allergies",
                data={"substance": "پنی‌سیلین", "severity": "severe", "reaction": "کهیر"})
    page = client.get(f"/patients/{pid}/records").text
    assert "پنی‌سیلین" in page and "کهیر" in page
    assert "شدید" in page          # Dari label
    assert "sev-severe" in page    # canonical stored value


def test_condition_round_trip(client):
    pid = _new_patient(client)
    client.post(f"/patients/{pid}/conditions",
                data={"name": "دیابت نوع ۲", "icd10_code": "E11",
                      "is_chronic": "1", "diagnosed_on": "2024-03-15"})
    page = client.get(f"/patients/{pid}/records").text
    assert "دیابت نوع ۲" in page and "E11" in page and "مزمن" in page


def test_appointments_appear_in_the_patient_history(client):
    pid = _new_patient(client)
    _book(client, pid)
    assert "کنترل قند" in client.get(f"/patients/{pid}/records").text


def test_deleting_an_allergy_leaves_the_visit_history_intact(client):
    import re

    pid = _new_patient(client)
    _book(client, pid)
    client.post(f"/patients/{pid}/allergies", data={"substance": "پنی‌سیلین"})
    page = client.get(f"/patients/{pid}/records").text
    aid = int(re.search(r"/allergies/(\d+)/delete", page).group(1))

    client.post(f"/allergies/{aid}/delete", data={"patient_id": str(pid)})
    page = client.get(f"/patients/{pid}/records").text
    assert "پنی‌سیلین" not in page
    assert "کنترل قند" in page
