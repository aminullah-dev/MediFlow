# MediFlow

**Offline Clinic & Hospital Management System for Afghanistan.**
Windows desktop · fully offline · Dari & Pashto (RTL) · Python 3.13 · PySide6 · SQLite.

MediFlow runs entirely on one machine with no internet, cloud, or subscription.
All data lives in a single per-user folder, making backup and restore trivial.

---

## Status — all 16 modules implemented (Phases 1–6)

The foundation **and** every functional module are built. Each module has a
service layer (validated, transactional), an RBAC-gated view, and dialogs, all
tri-lingual (Dari · Pashto · English) with runtime RTL and light/dark themes.

| # | Module | What it does | Backend |
|---|--------|--------------|---------|
| 1 | **Dashboard** | Daily at-a-glance stats | `DashboardService` |
| 2 | **Patients** (بیماران) | Searchable roster, register/edit, encrypted Tazkira, MRN | `PatientService` |
| 3 | **Appointments** (نوبت‌ها) | Day view, booking, check-in → queue token, status flow | `AppointmentService` |
| 4 | **Reception** (پذیرش) | Live queue board (waiting / in-consultation / done), call & complete | `AppointmentService` |
| 5 | **Medical Records** (سوابق طبی) | Allergies, problem list, appointment history | `MedicalRecordService` |
| 6 | **Pharmacy** (دواخانه) | Medication catalogue, dated stock batches, FEFO dispensing, expiry/low alerts | `PharmacyService` |
| 7 | **Laboratory** (لابراتوار) | Test catalogue, request → collect → result workflow | `LabService` |
| 8 | **Inventory** (انبار) | Supplies with stock-in/out movement log | `InventoryService` |
| 9 | **Billing** (صورتحساب) | Invoices with line items, payments, partial/paid status | `BillingService` |
| 10 | **Accounting** (حسابداری) | Double-entry chart of accounts, journal, balances, P&L | `AccountingService` |
| 11 | **Human Resources** (منابع بشری) | Employees, attendance, payroll | `HRService` |
| 12 | **Reports** (گزارش‌ها) | Cross-module analytics with Excel export | `ReportService` |
| 13 | **Users & Roles** (کاربران و نقش‌ها) | User admin, temp passwords, role/permission editor | `UserService` |
| 14 | **Audit Log** (سابقه ممیزی) | Change trail + sign-in history (read-only) | `AuditService` |
| 15 | **Backup** (پشتیبان‌گیری) | Online SQLite backup/restore with safety snapshot | `BackupService` |
| 16 | **Settings** (تنظیمات) | Clinic profile + preferences | `SettingsService` |

The data, security, and persistence core is proven on every commit via `pytest`
(7 passing end-to-end tests); every module was verified by driving its real
PySide6 widgets (rendered to screenshots) across all three languages and both
themes.

**UI/UX:** a medical-teal design system (WCAG-checked palette), a branded
deep-teal sidebar, and a full monochrome **SVG icon set** (no emoji) — informed
by the `ui-ux-pro-max` design-intelligence skill.

---

## Quick start (development)

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
pip install -e ".[dev]"

# Run the tests (no GUI needed)
pytest

# Create/upgrade the database schema
alembic upgrade head

# Launch the application
python -m mediflow
```

On first launch an **initial admin** is created and its one-time password is
written to the log (and shown by the first-run wizard in a later phase). The
admin is forced to change the password at first sign-in.

> **Python version:** targets **3.11+ (3.13 recommended)**. `passlib` was
> deliberately *not* used — it imports the stdlib `crypt` module removed in 3.13;
> hashing uses `hashlib.pbkdf2_hmac` instead, which is dependency-free and works
> everywhere.

---

## Architecture

Layered, dependency-inverted, SOLID. Dependencies point **downward only**;
the UI never touches the ORM directly.

```
┌──────────────────────────────────────────────────────────┐
│  Presentation (PySide6)   ui/  — views, dialogs, theme    │
│    MainWindow · LoginDialog · module views (MVVM-style)   │
└───────────────▲──────────────────────────────────────────┘
                │ calls services only
┌───────────────┴──────────────────────────────────────────┐
│  Services       services/ — business rules & transactions │
│    AuthService · PatientService · DashboardService …      │
└───────────────▲──────────────────────────────────────────┘
                │ uses repositories
┌───────────────┴──────────────────────────────────────────┐
│  Repositories   data/repositories/ — the only query layer │
│    BaseRepository[T] · UserRepository · PatientRepository │
└───────────────▲──────────────────────────────────────────┘
                │ maps
┌───────────────┴──────────────────────────────────────────┐
│  Domain / ORM   data/models/ + mixins + audit hooks       │
└───────────────▲──────────────────────────────────────────┘
                │
┌───────────────┴──────────────────────────────────────────┐
│  Core           core/ — config, logging, security, errors │
│  Persistence    data/database.py — engine, sessions, UoW  │
└──────────────────────────────────────────────────────────┘
```

**Cross-cutting concerns handled once, automatically:**

- *Attribution & audit* — a session `before_flush`/`after_flush` pair stamps
  `created_by`/`updated_by` from the current-user context var and writes an
  append-only `audit_log` row (with a JSON field diff) for every change. Business
  code writes nothing extra.
- *Soft delete* — repositories transparently hide `is_deleted` rows; data is
  retained for medico-legal and financial requirements.
- *Transactions* — `Database.unit_of_work()` gives services one atomic scope;
  repositories never commit.
- *Thread safety* — `scoped_session` gives each `QThread` worker its own session;
  WAL journaling allows concurrent reads during background writes (backups).

### Composition root
`mediflow/app.py` is the only place concrete objects are constructed and injected
(`ServiceContainer`). Everything else depends on parameters/abstractions.

---

## Data model (entity-relationship overview)

Surrogate integer PKs everywhere; explicit constraint naming for stable SQLite
migrations. `AuditMixin` = timestamps + soft delete + created/updated-by.

```
User ──< user_roles >── Role ──< role_permissions >── Permission
 │                         (RBAC graph)
 ├──< LoginHistory                    AuditLog >── (any entity, by type+id)
 │
Patient ──< PatientAllergy
   │     ──< PatientCondition
   │     ──< PatientDocument
   │
   └──< Appointment >── Department        Appointment ──1 QueueToken
              │  \___ doctor → User
ClinicInfo    Service >── Department, Tax
```

Implemented tables: `users, roles, permissions, user_roles, role_permissions,
login_history, audit_log, clinic_info, departments, services, taxes, patients,
patient_allergies, patient_conditions, patient_documents, appointments,
queue_tokens, medications, stock_batches, lab_tests, lab_requests,
inventory_items, stock_movements, invoices, invoice_lines, payments, accounts,
journal_entries, journal_lines, employees, attendance, payslips`
(+ `alembic_version`). Three Alembic migrations (foundation → pharmacy/lab →
inventory/billing) are checked in and upgrade cleanly.

### Enumerations
Stored as human-readable string values (`AppointmentStatus`, `InvoiceStatus`,
`PaymentMethod`, `StockMovementType`, `AccountType`, `BloodGroup`, `Gender`,
`AuditAction`, …). UI labels come from translations, never from the stored value.

---

## Security

- **Passwords:** PBKDF2-HMAC-SHA256, 390k rounds, per-hash salt, self-describing
  format, `hmac.compare_digest` verification, transparent rehash-on-policy-change.
- **Account protection:** progressive lockout after 5 failures (15-minute lock);
  every attempt (success/failure) recorded in `login_history`.
- **Field encryption:** sensitive columns (e.g. Tazkira / national ID) encrypted
  with a Fernet key that is itself **DPAPI-protected** at rest on Windows (bound
  to the user account); legacy plaintext keys are migrated automatically.
- **RBAC (defense in depth):** fine-grained `module.action` permissions enforced
  in the **service layer** (`@require` decorators over each mutating method),
  not just by hiding UI navigation.
- **Audit:** append-only trail of who changed what, when — **tamper-evident via
  an HMAC hash chain**; each row links to the previous one, and
  *Audit Log → Verify integrity* detects any after-the-fact edit or deletion.
- **Backups:** consistent online SQLite backups, each with an **HMAC signature**;
  restore refuses any file that fails `PRAGMA integrity_check`, lacks the MediFlow
  schema, or whose signature does not verify.
- The initial admin password is written to a restricted one-time file (never to
  the log).

> Remaining hardening candidates (from the security review): encrypted backup
> files, login-timing equalization, and escaping `%`/`_` in search LIKE patterns.

---

## Internationalisation

- Dari (`fa_AF`), Pashto (`ps_AF`) **and English**, all selectable with
  **runtime switching** (no restart) and automatic **RTL** layout.
- Qt `.ts`/`.qm` workflow with 745+ translated strings. No hardcoded strings —
  every widget implements `retranslate_ui`; the main window re-translates the
  whole tree on switch.
- Missing `.qm` files degrade gracefully to source strings, so development is
  never blocked on translation.

---

## Development roadmap

- **Phase 1 — Foundation ✅ done:** core, security, DB, RBAC, audit, migrations,
  i18n/theme, app shell, dashboard.
- **Phase 2 — Patients & Reception ✅ done:** patient roster, registration/edit
  dialogs, check-in, queue token, live reception board.
- **Phase 3 — Appointments & EMR ✅ done:** day view, booking, queue/status flow;
  medical records (allergies, problem list, history).
- **Phase 4 — Pharmacy, Laboratory & Inventory ✅ done:** medication catalogue,
  dated batches, FEFO dispensing, expiry/low alerts; lab request→result workflow;
  inventory stock movements.
- **Phase 5 — Billing & Accounting ✅ done:** invoices, line items, payments,
  status flow; double-entry chart of accounts, journal, balances, P&L.
- **Phase 6 — HR, Reports, Backup, Settings ✅ done:** employees/attendance/payroll,
  cross-module reports with Excel export, online SQLite backup/restore, settings.
- **Phase 7 — Printing & packaging (next):** A4 + thermal (ReportLab / Qt Print),
  receipt/prescription/report templates, Windows installer (PyInstaller + Inno).

> Security hardening completed from the review: service-layer RBAC enforcement,
> DPAPI-protected encryption key, HMAC-signed backups with integrity checks, and
> a tamper-evident audit hash chain. See the **Security** section above.

---

## Repository layout

```
mediflow/
  core/          config, logging, security, exceptions, constants
  data/
    base.py mixins.py database.py audit.py schema.py
    models/        user, audit, clinic, patient, appointment
    repositories/  base_repository, user_repository, patient_repository
  services/      auth, patient, dashboard
  seeds/         permissions catalogue, idempotent seeder
  i18n/          translator (runtime switch, RTL) + translations/
  ui/            theme, main_window, views/, dialogs/, widgets/
  migrations/    Alembic env + versions/
  app.py __main__.py
tests/           foundation end-to-end tests
```

---

© MediFlow — proprietary commercial software.
