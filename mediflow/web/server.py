"""MediFlow web layer — FastAPI + server-rendered Jinja templates.

The whole point of this module is that it is *thin*. Every rule about patients,
prescriptions, stock, money, permissions and the audit chain already lives in
``mediflow.services`` and ``mediflow.data``, none of which ever imported Qt. So
the browser UI reuses ``build_container`` verbatim and adds only: sessions,
routes, and HTML.

Sessions hold the user id and permission set. Permissions are re-read from the
database on every request rather than trusted from the cookie, so revoking a
role takes effect immediately instead of at next sign-in.
"""
from __future__ import annotations

import os
import secrets
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from mediflow.app import build_container
from mediflow.core.config import Config
from mediflow.core.constants import AppointmentStatus, BloodGroup, Gender
from mediflow.core.exceptions import (
    AccountLockedError,
    AuthenticationError,
    MediFlowError,
    ValidationError,
)
from mediflow.core.keyboard import has_persian_layout_chars
from mediflow.core.logging_config import configure_logging, get_logger
from mediflow.data.database import current_permissions, current_user_id
from mediflow.services.dashboard_service import DashboardService
from mediflow.services.appointment_service import AppointmentBooking
from mediflow.services.patient_service import PatientRegistration

log = get_logger("web")

_HERE = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))

# (value, Dari label) pairs for the select inputs.
GENDERS = [(Gender.MALE.value, "مرد"), (Gender.FEMALE.value, "زن"),
           (Gender.OTHER.value, "سایر")]
BLOOD_GROUPS = [(b.value, "نامعلوم" if b is BloodGroup.UNKNOWN else b.value)
                for b in BloodGroup]


# The service layer raises English domain messages (it predates the web UI and
# is shared with the desktop build). Map the ones a receptionist can actually
# trigger onto Dari; anything unmapped falls through unchanged rather than
# being swallowed.
_ERROR_FA = {
    "First name is required.": "نام الزامی است.",
    "Last name is required.": "تخلص الزامی است.",
    "Invalid gender.": "جنسیت نامعتبر است.",
    "Provide a date of birth or an approximate age.":
        "تاریخ تولد یا سن تقریبی را وارد کنید.",
}


def _fa_error(exc: Exception) -> str:
    return _ERROR_FA.get(str(exc), str(exc))


# Appointment lifecycle, in Dari. Kept here rather than in the template so the
# reception board and the day view can never drift apart.
STATUS_FA = {
    AppointmentStatus.BOOKED.value: "نوبت گرفته",
    AppointmentStatus.CHECKED_IN.value: "در انتظار",
    AppointmentStatus.IN_CONSULTATION.value: "در حال معاینه",
    AppointmentStatus.COMPLETED.value: "تکمیل شده",
    AppointmentStatus.CANCELLED.value: "لغو شده",
    AppointmentStatus.NO_SHOW.value: "غایب",
    AppointmentStatus.WAITLISTED.value: "فهرست انتظار",
}


# Stored values match the desktop build exactly (allergy_dialog.py uses
# mild/moderate/severe), so records written by either UI stay comparable.
SEVERITIES = [("", "— تعیین نشده —"), ("mild", "خفیف"),
              ("moderate", "متوسط"), ("severe", "شدید")]
SEVERITY_FA = {"mild": "خفیف", "moderate": "متوسط", "severe": "شدید"}


def _parse_day(raw: str | None) -> datetime:
    """The ?day= query param, or today. Bad input falls back rather than 500s."""
    if raw:
        try:
            d = date.fromisoformat(raw)
            return datetime(d.year, d.month, d.day)
        except ValueError:
            pass
    now = datetime.now()
    return datetime(now.year, now.month, now.day)


def _parse_datetime_local(raw: str | None) -> datetime:
    """Parse an <input type="datetime-local"> value.

    ``scheduled_start`` stores user-entered *local* wall-clock time (the
    services treat "today" as the local calendar day), so this stays naive and
    is deliberately not converted to UTC.
    """
    if not raw:
        raise ValidationError("زمان نوبت را وارد کنید.", field="scheduled_start")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise ValidationError("زمان نوبت نامعتبر است.", field="scheduled_start")


def _clean(form, key: str) -> str | None:
    """Empty form fields arrive as '' — the services expect None instead."""
    value = (form.get(key) or "").strip()
    return value or None


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValidationError("تاریخ تولد نامعتبر است.", field="date_of_birth")


def _parse_int(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValidationError("سن نامعتبر است.", field="approximate_age_years")


def _registration_from(form) -> PatientRegistration:
    """Map posted form fields onto the service's input dataclass."""
    return PatientRegistration(
        first_name=(form.get("first_name") or "").strip(),
        last_name=(form.get("last_name") or "").strip(),
        gender=(form.get("gender") or Gender.MALE.value),
        father_name=_clean(form, "father_name"),
        date_of_birth=_parse_date(_clean(form, "date_of_birth")),
        approximate_age_years=_parse_int(_clean(form, "approximate_age_years")),
        blood_group=(form.get("blood_group") or BloodGroup.UNKNOWN.value),
        phone=_clean(form, "phone"),
        national_id=_clean(form, "national_id"),
        province=_clean(form, "province"),
        district=_clean(form, "district"),
        address=_clean(form, "address"),
        notes=_clean(form, "notes"),
    )


def _echo(form, patient_id: int | None = None) -> SimpleNamespace:
    """Re-render the form with what the user typed after a validation error.

    Shaped like PatientDTO so the template needs no special-casing.
    """
    return SimpleNamespace(
        id=patient_id, mrn=form.get("mrn") or "",
        first_name=form.get("first_name") or "", last_name=form.get("last_name") or "",
        father_name=form.get("father_name") or "", gender=form.get("gender") or "",
        date_of_birth=form.get("date_of_birth") or "",
        approximate_age_years=form.get("approximate_age_years") or "",
        blood_group=form.get("blood_group") or "", phone=form.get("phone") or "",
        national_id=form.get("national_id") or "", province=form.get("province") or "",
        district=form.get("district") or "", address=form.get("address") or "",
        notes=form.get("notes") or "",
    )


def _session_secret(config: Config) -> str:
    """A stable per-installation cookie key, kept beside the other secrets.

    Regenerating this on every boot would silently sign every user out on each
    restart, which on a clinic machine looks exactly like "the login broke".
    """
    path = config.paths.base / ".session_key"
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    key = secrets.token_urlsafe(48)
    path.write_text(key, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - best effort on Windows
        pass
    return key


def create_app(config: Config | None = None) -> FastAPI:
    config = config or Config.bootstrap()
    configure_logging(config.paths.logs, debug=config.debug)
    # Loudly state which data folder won. The MSIX redirection bug cost days
    # precisely because nothing ever printed the resolved path.
    log.warning("MediFlow web starting — data directory: %s", config.paths.base)

    container = build_container(config)
    # Not part of ServiceContainer — the desktop views construct it per-view
    # too (see ui/views/dashboard_view.py); mirror that rather than widen the
    # shared container just for the web build.
    dashboard_service = DashboardService(container.database)
    app = FastAPI(title="MediFlow", docs_url=None, redoc_url=None)
    app.state.container = container
    app.state.config = config
    app.add_middleware(SessionMiddleware, secret_key=_session_secret(config),
                       session_cookie="mediflow_session", https_only=False)
    app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

    def _current_user(request: Request):
        """Re-hydrate the signed-in user from the database, not from the cookie.

        Also binds the request-scoped identity so the service layer's
        ``@require`` decorators and the audit trail see the right actor. Every
        protected route must go through here before touching a service.
        """
        user_id = request.session.get("user_id")
        if not user_id:
            return None
        user = container.auth.load_session_user(user_id)
        if user is None:
            return None
        current_user_id.set(user.id)
        current_permissions.set(frozenset(user.permissions))
        return user

    def _deny(request: Request, user,
              message: str = "شما اجازه‌ی دسترسی به این بخش را ندارید."):
        return TEMPLATES.TemplateResponse(
            request, "denied.html", {"user": user, "message": message}, status_code=403)

    # -- auth ---------------------------------------------------------------
    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse("/", status_code=303)
        return TEMPLATES.TemplateResponse(request, "login.html", {
            "error": None,
            "username": request.session.get("last_username", ""),
        })

    @app.post("/login", response_class=HTMLResponse)
    def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
        username = (username or "").strip()
        error = None
        if not username or not password:
            error = "نام کاربری و رمز عبور را وارد کنید."
        else:
            try:
                user = container.auth.authenticate(username, password)
            except AccountLockedError as exc:
                minutes = max(1, round((exc.retry_after_seconds or 60) / 60))
                error = f"حساب قفل شده است. {minutes} دقیقه دیگر دوباره تلاش کنید."
            except AuthenticationError as exc:
                error = "نام کاربری یا رمز عبور نادرست است."
                if exc.attempts_remaining is not None and 0 < exc.attempts_remaining <= 3:
                    error += f" {exc.attempts_remaining} تلاش تا قفل‌شدن باقی مانده است."
            except MediFlowError:
                error = "نام کاربری یا رمز عبور نادرست است."
            else:
                request.session["user_id"] = user.id
                request.session["last_username"] = user.username
                log.info("Web sign-in for '%s'.", user.username)
                return RedirectResponse("/", status_code=303)

        return TEMPLATES.TemplateResponse(request, "login.html", {
            "error": error,
            "username": username,
            # Mirrors the desktop fix: tell the operator the moment Persian
            # characters reach the field, since the masked input hides it.
            "layout_warning": has_persian_layout_chars(password) or has_persian_layout_chars(username),
        }, status_code=401)

    @app.post("/logout")
    def logout(request: Request):
        """Return to the sign-in screen — never terminate the server.

        The desktop build wired 'sign out' to closing the main window, which
        quit the whole application; on a shared reception machine that reads as
        a crash. Here it simply clears the session.
        """
        request.session.pop("user_id", None)
        container.auth.logout()
        return RedirectResponse("/login", status_code=303)

    # -- pages --------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        # Bind identity so service-layer writes are attributed and RBAC applies.
        current_user_id.set(user.id)
        current_permissions.set(frozenset(user.permissions))
        try:
            stats = dashboard_service.snapshot()
        except Exception:
            log.exception("Dashboard snapshot failed")
            stats = None
        return TEMPLATES.TemplateResponse(request, "dashboard.html", {
            "user": user,
            "stats": stats,
            "data_dir": str(config.paths.base),
        })

    # -- patients -----------------------------------------------------------
    @app.get("/patients", response_class=HTMLResponse)
    def patients_list(request: Request, q: str = ""):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("patient.view"):
            return _deny(request, user)
        term = (q or "").strip()
        rows = container.patients.search(term) if term else container.patients.list_recent()
        return TEMPLATES.TemplateResponse(request, "patients_list.html", {
            "user": user, "patients": rows, "q": term,
            "total": container.patients.count(),
        })

    @app.get("/patients/new", response_class=HTMLResponse)
    def patient_new_form(request: Request):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("patient.create"):
            return _deny(request, user)
        return TEMPLATES.TemplateResponse(request, "patient_form.html", {
            "user": user, "patient": None, "error": None,
            "genders": GENDERS, "blood_groups": BLOOD_GROUPS,
        })

    @app.post("/patients/new", response_class=HTMLResponse)
    async def patient_create(request: Request):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("patient.create"):
            return _deny(request, user)
        form = await request.form()
        try:
            new_id = container.patients.register(_registration_from(form))
        except MediFlowError as exc:
            return TEMPLATES.TemplateResponse(request, "patient_form.html", {
                "user": user, "patient": _echo(form), "error": _fa_error(exc),
                "genders": GENDERS, "blood_groups": BLOOD_GROUPS,
            }, status_code=400)
        return RedirectResponse(f"/patients/{new_id}", status_code=303)

    @app.get("/patients/{patient_id}", response_class=HTMLResponse)
    def patient_detail(request: Request, patient_id: int):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("patient.view"):
            return _deny(request, user)
        try:
            patient = container.patients.get(patient_id)
        except MediFlowError:
            return _deny(request, user, "بیمار مورد نظر یافت نشد.")
        return TEMPLATES.TemplateResponse(request, "patient_form.html", {
            "user": user, "patient": patient, "error": None,
            "genders": GENDERS, "blood_groups": BLOOD_GROUPS,
        })

    @app.post("/patients/{patient_id}", response_class=HTMLResponse)
    async def patient_update(request: Request, patient_id: int):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("patient.update"):
            return _deny(request, user)
        form = await request.form()
        try:
            container.patients.update(patient_id, _registration_from(form))
        except MediFlowError as exc:
            patient = _echo(form, patient_id=patient_id)
            return TEMPLATES.TemplateResponse(request, "patient_form.html", {
                "user": user, "patient": patient, "error": _fa_error(exc),
                "genders": GENDERS, "blood_groups": BLOOD_GROUPS,
            }, status_code=400)
        return RedirectResponse(f"/patients/{patient_id}?saved=1", status_code=303)

    @app.post("/patients/{patient_id}/delete")
    def patient_delete(request: Request, patient_id: int):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("patient.delete"):
            return _deny(request, user)
        try:
            container.patients.delete(patient_id)
        except MediFlowError:
            pass
        return RedirectResponse("/patients", status_code=303)

    # -- medical records ----------------------------------------------------
    @app.get("/patients/{patient_id}/records", response_class=HTMLResponse)
    def patient_records(request: Request, patient_id: int):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("emr.view"):
            return _deny(request, user)
        try:
            patient = container.patients.get(patient_id)
        except MediFlowError:
            return _deny(request, user, "بیمار مورد نظر یافت نشد.")
        emr = container.medical_records
        return TEMPLATES.TemplateResponse(request, "patient_records.html", {
            "user": user,
            "patient": patient,
            "allergies": emr.list_allergies(patient_id),
            "conditions": emr.list_conditions(patient_id),
            "documents": emr.list_documents(patient_id),
            "history": container.appointments.list_for_patient(patient_id),
            "severities": SEVERITIES,
            "severity_fa": SEVERITY_FA,
            "status_fa": STATUS_FA,
            "error": None,
        })

    @app.post("/patients/{patient_id}/allergies")
    async def allergy_add(request: Request, patient_id: int):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("emr.write"):
            return _deny(request, user)
        form = await request.form()
        try:
            container.medical_records.add_allergy(
                patient_id,
                form.get("substance") or "",
                severity=_clean(form, "severity"),
                reaction=_clean(form, "reaction"),
            )
        except MediFlowError:
            log.exception("Adding allergy failed for patient %s", patient_id)
        return RedirectResponse(f"/patients/{patient_id}/records", status_code=303)

    @app.post("/allergies/{allergy_id}/delete")
    def allergy_delete(request: Request, allergy_id: int, patient_id: int = Form(...)):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("emr.write"):
            return _deny(request, user)
        container.medical_records.delete_allergy(allergy_id)
        return RedirectResponse(f"/patients/{patient_id}/records", status_code=303)

    @app.post("/patients/{patient_id}/conditions")
    async def condition_add(request: Request, patient_id: int):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("emr.write"):
            return _deny(request, user)
        form = await request.form()
        try:
            container.medical_records.add_condition(
                patient_id,
                form.get("name") or "",
                icd10_code=_clean(form, "icd10_code"),
                is_chronic=bool(form.get("is_chronic")),
                diagnosed_on=_parse_date(_clean(form, "diagnosed_on")),
                notes=_clean(form, "notes"),
            )
        except MediFlowError:
            log.exception("Adding condition failed for patient %s", patient_id)
        return RedirectResponse(f"/patients/{patient_id}/records", status_code=303)

    @app.post("/conditions/{condition_id}/delete")
    def condition_delete(request: Request, condition_id: int, patient_id: int = Form(...)):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("emr.write"):
            return _deny(request, user)
        container.medical_records.delete_condition(condition_id)
        return RedirectResponse(f"/patients/{patient_id}/records", status_code=303)

    # -- appointments -------------------------------------------------------
    @app.get("/appointments", response_class=HTMLResponse)
    def appointments_day(request: Request, day: str = ""):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("appointment.view"):
            return _deny(request, user)
        chosen = _parse_day(day)
        return TEMPLATES.TemplateResponse(request, "appointments.html", {
            "user": user,
            "appointments": container.appointments.list_for_day(chosen),
            "day": chosen.date().isoformat(),
            "status_fa": STATUS_FA,
        })

    @app.get("/appointments/new", response_class=HTMLResponse)
    def appointment_new_form(request: Request, patient_id: int | None = None):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("appointment.create"):
            return _deny(request, user)
        return TEMPLATES.TemplateResponse(request, "appointment_form.html", {
            "user": user, "error": None, "form": None,
            "patients": container.patients.list_recent(limit=500),
            "doctors": container.appointments.list_doctors(),
            "departments": container.appointments.list_departments(),
            "preselect_patient": patient_id,
        })

    @app.post("/appointments/new", response_class=HTMLResponse)
    async def appointment_create(request: Request):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("appointment.create"):
            return _deny(request, user)
        form = await request.form()
        try:
            if not form.get("patient_id"):
                raise ValidationError("بیمار را انتخاب کنید.", field="patient_id")
            booking = AppointmentBooking(
                patient_id=int(form["patient_id"]),
                scheduled_start=_parse_datetime_local(form.get("scheduled_start")),
                doctor_id=int(form["doctor_id"]) if form.get("doctor_id") else None,
                department_id=int(form["department_id"]) if form.get("department_id") else None,
                reason=_clean(form, "reason"),
                is_walk_in=bool(form.get("is_walk_in")),
                notes=_clean(form, "notes"),
            )
            container.appointments.book(booking)
        except MediFlowError as exc:
            return TEMPLATES.TemplateResponse(request, "appointment_form.html", {
                "user": user, "error": _fa_error(exc), "form": form,
                "patients": container.patients.list_recent(limit=500),
                "doctors": container.appointments.list_doctors(),
                "departments": container.appointments.list_departments(),
                "preselect_patient": None,
            }, status_code=400)
        day = booking.scheduled_start.date().isoformat()
        return RedirectResponse(f"/appointments?day={day}", status_code=303)

    @app.post("/appointments/{appointment_id}/checkin")
    def appointment_checkin(request: Request, appointment_id: int, day: str = Form("")):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("reception.checkin"):
            return _deny(request, user)
        try:
            container.appointments.check_in(appointment_id)
        except MediFlowError:
            log.exception("Check-in failed for appointment %s", appointment_id)
        return RedirectResponse(f"/appointments?day={day}" if day else "/appointments",
                                status_code=303)

    @app.post("/appointments/{appointment_id}/cancel")
    def appointment_cancel(request: Request, appointment_id: int, day: str = Form("")):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not user.can("appointment.cancel"):
            return _deny(request, user)
        try:
            container.appointments.cancel(appointment_id)
        except MediFlowError:
            log.exception("Cancel failed for appointment %s", appointment_id)
        return RedirectResponse(f"/appointments?day={day}" if day else "/appointments",
                                status_code=303)

    # -- reception queue ----------------------------------------------------
    @app.get("/reception", response_class=HTMLResponse)
    def reception_board(request: Request):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not (user.can("reception.checkin") or user.can("reception.queue")):
            return _deny(request, user)
        today = _parse_day(None)
        todays = container.appointments.list_for_day(today)
        waiting = [a for a in todays if a.status == AppointmentStatus.CHECKED_IN.value]
        serving = [a for a in todays if a.status == AppointmentStatus.IN_CONSULTATION.value]
        done = [a for a in todays if a.status == AppointmentStatus.COMPLETED.value]
        return TEMPLATES.TemplateResponse(request, "reception.html", {
            "user": user, "waiting": waiting, "serving": serving, "done": done,
            "status_fa": STATUS_FA,
        })

    @app.post("/reception/{appointment_id}/call")
    def reception_call(request: Request, appointment_id: int):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not (user.can("reception.queue") or user.can("appointment.update")):
            return _deny(request, user)
        try:
            container.appointments.call(appointment_id)
        except MediFlowError:
            log.exception("Call failed for appointment %s", appointment_id)
        return RedirectResponse("/reception", status_code=303)

    @app.post("/reception/{appointment_id}/complete")
    def reception_complete(request: Request, appointment_id: int):
        user = _current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        if not (user.can("reception.queue") or user.can("appointment.update")):
            return _deny(request, user)
        try:
            container.appointments.complete(appointment_id)
        except MediFlowError:
            log.exception("Complete failed for appointment %s", appointment_id)
        return RedirectResponse("/reception", status_code=303)

    @app.get("/healthz")
    def healthz():
        """Liveness probe that also reveals which database is actually in use."""
        return {"status": "ok", "data_dir": str(config.paths.base),
                "database": config.database_url}

    return app


def run(host: str = "127.0.0.1", port: int = 8000) -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="info")
