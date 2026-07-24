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


# -- users, roles and own-password ------------------------------------------
def _receptionist_role(app):
    roles = app.state.container.users.list_roles()
    return next(r for r in roles if r.name == "receptionist")


def _create_user(client, app, username="nasrin"):
    """Create a user and return the one-time temporary password."""
    import re

    r = client.post("/users/new", data={
        "username": username, "full_name": "نسرین قادری", "is_active": "1",
        "role_ids": [str(_receptionist_role(app).id)]})
    assert r.status_code == 200, r.text[:400]
    return re.search(r'id="tempPass">([^<]+)<', r.text).group(1).strip()


def test_users_page_lists_accounts_and_roles(client):
    page = client.get("/users").text
    assert "کاربران و نقش‌ها" in page
    assert "admin" in page
    assert "شما" in page          # the signed-in account is marked


def test_generated_temp_password_is_digits_only(client, app):
    """Digits are identical on the US and Persian layouts, so the credential is
    always typeable — the mixed alphabet used to emit P/U, which become ASCII
    on the Persian layout and cannot be recovered."""
    temp = _create_user(client, app)
    assert temp.isdigit()
    assert len(temp) >= 8


def test_new_user_must_change_the_temp_password_before_working(app, client):
    temp = _create_user(client, app)
    fresh = TestClient(app)
    assert fresh.post("/login", data={"username": "nasrin", "password": temp},
                      follow_redirects=False).status_code == 303

    bounced = fresh.get("/", follow_redirects=False)
    assert bounced.status_code == 303
    assert bounced.headers["location"] == "/account/password"

    assert fresh.post("/account/password",
                      data={"current_password": temp, "new_password": "Kabul2026",
                            "confirm_password": "Kabul2026"},
                      follow_redirects=False).status_code == 303
    assert fresh.get("/", follow_redirects=False).status_code == 200


def test_a_persian_typed_new_password_is_refused_not_stored(app, client):
    """Storing it would produce a password that cannot be typed back."""
    temp = _create_user(client, app)
    fresh = TestClient(app)
    fresh.post("/login", data={"username": "nasrin", "password": temp})
    fresh.post("/account/password", data={"current_password": temp,
               "new_password": "Kabul2026", "confirm_password": "Kabul2026"})
    r = fresh.post("/account/password", data={"current_password": "Kabul2026",
                   "new_password": "َئهد2026", "confirm_password": "َئهد2026"})
    assert r.status_code == 400
    assert "کیبورد" in r.text


def test_receptionist_cannot_administer_users(app, client):
    temp = _create_user(client, app)
    fresh = TestClient(app)
    fresh.post("/login", data={"username": "nasrin", "password": temp})
    fresh.post("/account/password", data={"current_password": temp,
               "new_password": "Kabul2026", "confirm_password": "Kabul2026"})
    assert fresh.get("/users/new").status_code == 403
    assert fresh.get("/reception").status_code == 200


@pytest.mark.parametrize("path,data,needle", [
    ("/users/1/delete", {}, "حساب خودتان"),
    ("/users/1/active", {"active": "0"}, "حساب خودتان"),
])
def test_you_cannot_lock_yourself_out(client, path, data, needle):
    assert needle in client.post(path, data=data).text


def test_role_can_be_created_and_duplicates_are_refused(client):
    r = client.post("/roles/new", data={"name": "تست نقش",
                    "permissions": ["patient.view"]}, follow_redirects=False)
    assert r.status_code == 303
    assert "تست نقش" in client.get("/users").text

    dup = client.post("/roles/new", data={"name": "تست نقش", "permissions": []})
    assert dup.status_code == 400
    assert "از قبل وجود دارد" in dup.text


def test_password_reset_issues_a_fresh_credential(client, app):
    _create_user(client, app)
    r = client.post("/users/2/reset-password")
    assert r.status_code == 200
    assert "رمز بازنشانی شد" in r.text


# -- pharmacy ---------------------------------------------------------------
def _new_medication(client, **over) -> int:
    data = {"name": "سیپروفلوکساسین", "generic_name": "Ciprofloxacin",
            "form": "تابلیت", "strength": "500 mg", "unit": "tablet",
            "reorder_level": "20", "sale_price": "15"}
    data.update(over)
    r = client.post("/pharmacy/new", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text[:400]
    return int(r.headers["location"].rsplit("/", 1)[-1])


def test_pharmacy_lists_seeded_medications(client):
    page = client.get("/pharmacy").text
    assert "دواخانه" in page
    assert "Paracetamol" in page


def test_medication_can_be_created_and_searched(client):
    _new_medication(client)
    assert "سیپروفلوکساسین" in client.get("/pharmacy").text
    assert "سیپروفلوکساسین" in client.get("/pharmacy?q=Ciproflox").text


def test_stock_is_tracked_as_dated_batches(client):
    from datetime import date, timedelta

    mid = _new_medication(client)
    soon = (date.today() + timedelta(days=20)).isoformat()
    later = (date.today() + timedelta(days=400)).isoformat()
    client.post(f"/pharmacy/{mid}/stock",
                data={"quantity": "30", "batch_number": "B-LATER", "expiry_date": later})
    client.post(f"/pharmacy/{mid}/stock",
                data={"quantity": "10", "batch_number": "B-SOON", "expiry_date": soon})

    detail = client.get(f"/pharmacy/{mid}").text
    assert "40 tablet" in detail
    assert soon in detail, "the nearest expiry drives the warning"


def test_dispensing_consumes_the_nearest_expiry_batch_first(client):
    """FEFO. Draining the newest batch first would leave stock to expire in
    the store — the whole point of tracking expiry per batch."""
    from datetime import date, timedelta

    mid = _new_medication(client)
    soon = (date.today() + timedelta(days=20)).isoformat()
    later = (date.today() + timedelta(days=400)).isoformat()
    client.post(f"/pharmacy/{mid}/stock", data={"quantity": "30", "expiry_date": later})
    client.post(f"/pharmacy/{mid}/stock", data={"quantity": "10", "expiry_date": soon})

    client.post(f"/pharmacy/{mid}/dispense", data={"quantity": "10"})
    detail = client.get(f"/pharmacy/{mid}").text
    assert "30 tablet" in detail
    assert soon not in detail, "near-expiry batch should be gone"
    assert later in detail


def test_cannot_dispense_more_than_is_in_stock(client):
    mid = _new_medication(client)
    client.post(f"/pharmacy/{mid}/stock", data={"quantity": "5"})
    r = client.post(f"/pharmacy/{mid}/dispense", data={"quantity": "999"})
    assert r.status_code == 400
    assert "فقط 5 واحد موجود است" in r.text, "numeric message must be localised too"


def test_zero_quantity_is_refused_in_dari(client):
    mid = _new_medication(client)
    r = client.post(f"/pharmacy/{mid}/dispense", data={"quantity": "0"})
    assert r.status_code == 400
    assert "بیشتر از صفر" in r.text


def test_low_stock_raises_an_alert_on_the_list(client):
    mid = _new_medication(client, reorder_level="20")
    client.post(f"/pharmacy/{mid}/stock", data={"quantity": "25"})
    client.post(f"/pharmacy/{mid}/dispense", data={"quantity": "10"})
    assert "رو به اتمام" in client.get("/pharmacy").text


# -- billing ----------------------------------------------------------------
def _invoice(client, pid, **over):
    data = {"patient_id": str(pid),
            "line_description": ["معاینه داکتر", "لابراتوار", ""],
            "line_quantity": ["1", "2", "1"],
            "line_unit_price": ["500", "250", ""],
            "discount": "100", "tax": "50"}
    data.update(over)
    r = client.post("/billing/new", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text[:400]
    return int(r.headers["location"].rsplit("/", 1)[-1])


def test_invoice_totals_are_computed_from_the_lines(client):
    """500x1 + 250x2 = 1000, minus 100 discount, plus 50 tax = 950."""
    pid = _new_patient(client)
    detail = client.get(f"/billing/{_invoice(client, pid)}").text
    assert "1000" in detail
    assert "950" in detail
    assert "پرداخت‌نشده" in detail


def test_blank_line_rows_are_ignored(client):
    """The form ships spare rows; a half-filled one must not become a charge."""
    pid = _new_patient(client)
    detail = client.get(f"/billing/{_invoice(client, pid)}").text
    assert detail.count("معاینه داکتر") == 1


def test_partial_then_full_payment_moves_the_status(client):
    pid = _new_patient(client)
    iid = _invoice(client, pid)

    client.post(f"/billing/{iid}/payment", data={"amount": "400", "method": "cash"})
    detail = client.get(f"/billing/{iid}").text
    assert "پرداخت جزئی" in detail
    assert "550" in detail, "balance = 950 - 400"
    assert "نقد" in detail

    client.post(f"/billing/{iid}/payment", data={"amount": "550", "method": "card"})
    detail = client.get(f"/billing/{iid}").text
    assert "پرداخت‌شده" in detail
    assert "ثبت پرداخت" not in detail, "payment form should disappear once settled"


def test_overpayment_is_refused_with_a_localised_amount(client):
    pid = _new_patient(client)
    iid = _invoice(client, pid)
    r = client.post(f"/billing/{iid}/payment", data={"amount": "9999", "method": "cash"})
    assert r.status_code == 400
    assert "بیشتر است" in r.text


def test_an_invoice_needs_at_least_one_line(client):
    pid = _new_patient(client)
    r = client.post("/billing/new", data={"patient_id": str(pid),
                    "line_description": [""], "line_quantity": ["1"],
                    "line_unit_price": ["0"]})
    assert r.status_code == 400
    assert "حداقل یک قلم" in r.text


def test_discount_cannot_exceed_the_subtotal(client):
    pid = _new_patient(client)
    r = client.post("/billing/new", data={"patient_id": str(pid),
                    "line_description": ["x"], "line_quantity": ["1"],
                    "line_unit_price": ["10"], "discount": "9999"})
    assert r.status_code == 400
    assert "تخفیف" in r.text


def test_a_cancelled_invoice_cannot_be_paid(client):
    pid = _new_patient(client)
    iid = _invoice(client, pid)
    client.post(f"/billing/{iid}/cancel")
    assert "لغو شده" in client.get(f"/billing/{iid}").text

    r = client.post(f"/billing/{iid}/payment", data={"amount": "10", "method": "cash"})
    assert r.status_code == 400
    assert "لغو" in r.text


# -- laboratory -------------------------------------------------------------
def _lab_test(client, app, name="ویتامین D"):
    client.post("/laboratory/tests",
                data={"name": name, "code": "VITD", "sample_type": "Blood",
                      "reference_range": "30-100", "unit": "ng/mL", "price": "350"})
    return next(t.id for t in app.state.container.lab.list_tests() if t.name == name)


def _lab_request(client, app, pid):
    import re

    tid = _lab_test(client, app)
    client.post("/laboratory/request",
                data={"patient_id": str(pid), "lab_test_id": str(tid)})
    board = client.get("/laboratory").text
    return int(re.search(r"/laboratory/(\d+)/collect", board).group(1))


def test_lab_catalogue_ships_with_seeded_tests(client):
    page = client.get("/laboratory/tests").text
    assert "Complete Blood Count" in page
    assert "70–110" in page, "reference ranges come from the seed"


def test_request_moves_through_collect_start_and_result(client, app):
    pid = _new_patient(client)
    rid = _lab_request(client, app, pid)
    assert "درخواست‌شده" in client.get("/laboratory").text

    client.post(f"/laboratory/{rid}/collect")
    assert "نمونه گرفته شد" in client.get("/laboratory").text

    client.post(f"/laboratory/{rid}/start")
    assert "در حال انجام" in client.get("/laboratory").text

    r = client.post(f"/laboratory/{rid}/result",
                    data={"result_value": "18", "result_flag": "low"},
                    follow_redirects=False)
    assert r.status_code == 303, "the /result route must not be swallowed by the {action} catch-all"

    board = client.get("/laboratory?all=1").text
    assert "تکمیل شده" in board
    assert "18" in board
    assert "پایین" in board and "flag-low" in board


def test_the_technician_sees_the_reference_range_when_entering_a_result(client, app):
    """It is what tells them whether the value is abnormal, so it belongs on
    the entry screen rather than only in the catalogue."""
    pid = _new_patient(client)
    rid = _lab_request(client, app, pid)
    client.post(f"/laboratory/{rid}/collect")
    form = client.get(f"/laboratory/{rid}/result").text
    assert "30-100" in form
    assert "ng/mL" in form


def test_completed_and_cancelled_requests_leave_the_open_worklist(client, app):
    pid = _new_patient(client)
    rid = _lab_request(client, app, pid)
    client.post(f"/laboratory/{rid}/cancel")
    assert "نادیه صافی" not in client.get("/laboratory").text
    assert "لغو شده" in client.get("/laboratory?all=1").text


def test_a_blank_result_is_refused_in_dari(client, app):
    pid = _new_patient(client)
    rid = _lab_request(client, app, pid)
    client.post(f"/laboratory/{rid}/collect")
    r = client.post(f"/laboratory/{rid}/result", data={"result_value": "   "})
    assert r.status_code == 400
    assert "مقدار نتیجه الزامی" in r.text


def test_a_request_needs_both_a_patient_and_a_test(client, app):
    tid = _lab_test(client, app)
    r = client.post("/laboratory/request", data={"patient_id": "", "lab_test_id": str(tid)})
    assert r.status_code == 400
    assert "بیمار را انتخاب کنید" in r.text
