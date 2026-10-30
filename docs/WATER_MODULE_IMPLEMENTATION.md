# Module 2 — Water & Utility Billing: implementation notes and SRS traceability

Source: *SRS – Module 2 Water Utility Billing* (v0.1, 21-10-2026). This document records what was built for
Release 1, where it lives, how each SRS requirement is met, and what is a stand-in or still open.

The module runs **on its own** (SRS 1.2, 2.1). It reads the platform's tenant, ward and zone code lists, and
exchanges no data with Property Tax or any other module.

---

## 1. Where the code is

| Layer | Files |
|---|---|
| Data model (`wtr_*` tables) | `backend/services/core_service/app/db/water_models.py` |
| Billing rules (pure, unit-testable) | `backend/services/core_service/app/core/water_calc.py` |
| API (`/api/v1/water/...`) | `backend/services/core_service/app/api/v1/water/` (`connections`, `applications`, `meters`, `billing`, `payments`, `arrears`, `approvals`, `complaints`, `reports`, `admin`, shared `common`) |
| Schemas (camelCase JSON) | `backend/services/core_service/app/schemas/water.py` |
| Start-up data | `backend/services/core_service/app/db/water_seed.py` |
| End-to-end test | `backend/services/core_service/tests/water/test_water_e2e.py` |
| Frontend service, models, Telugu/English | `frontend/urban-console/src/app/core/services/water.service.ts`, `water-i18n.service.ts`, `core/models/water.model.ts` |
| Frontend screens (lazy loaded at `/modules/wtr/:section`) | `frontend/urban-console/src/app/modules/water/` |

Edits to shared files are limited to hook-up lines:
- `app/main.py`: include the water router and run the water seed in its own session.
- `app.routes.ts`: the lazy route.
- `app.ts`/`app.html`: open the Water screens when WTR is picked in the launcher, and hide the PTX-specific banner on them.
- `package.json`: `leaflet` (map) and `qrcode` (bill/receipt QR).
- `.gitignore`: local database and photo storage.
- `start.bat`: local run without Docker.

## 2. Running it locally

`start.bat` at the repo root. With Docker it runs `docker compose up`. Without Docker it creates
`backend/services/core_service/.venv` on first run, starts the API on port 8000 against a local SQLite file
(`local-dev.db`), and starts the frontend on port 4200. In development the seed loads demo data built by the
module's own engine: ~24 connections in wards 14/22/35/48/56, four months of readings, bills, payments,
penalties, disconnection notices, complaints, an illegal-connection case and an application.

Demo water users (password `Water@123`, seeded in development only):
`water.officer@`, `meter.reader@` (limited to Ward 14), `water.fieldstaff@`, `cashier@`, `commissioner@`,
`csc.operator@` — all `@gwmc.gov.in`.

Tests: `cd backend/services/core_service` then `python -m pytest tests/water -q` (needs `requirements-dev.txt`).

## 3. Design decisions

- **Ledger, not balances.** Every money movement is a signed row in `wtr_ledger` (bucket PENALTY / FEE /
  ARREAR / CURRENT / ADVANCE / DEPOSIT, with an account head). Dues are always derived from it. No financial row
  is edited or deleted; corrections, cancellations and cheque returns post opposite rows (SRS 2.5, WB-26, WB-33).
- **Versioned configuration.** Every rate, fee, threshold, SLA, workflow and account head is a `wtr_settings`
  row with an effective date. Tariffs are versioned in `wtr_tariffs`. Nothing can be back-dated, so a past
  bill can always be recalculated (SRS 2.5, 3.4, WB-NF-50).
- **Exactly-once.** Unique (connection, cycle) bills; idempotency keys on receipts; `client_ref` on readings;
  gateway order id on online payments; de-duplicated reminders (WB-NF-32, WB-NF-63).
- **Business dates in IST.** Timestamps are stored in UTC. Receipt dates, day-end closing and the billing cycle
  of a reading use the local date (`WATER_TZ_OFFSET_MINUTES`, default 330).

## 4. SRS traceability

Status: **Done** = built and covered by the end-to-end test or checked in the browser. **Stand-in** = works
locally behind the interface the real service will use (WB-IR-10). **Open** = needs GWMC input or later work.

### 3.2.1 Consumer and connection registration
| ID | How it is met | Status |
|---|---|---|
| WB-01 | Permanent consumer number from a never-reset counter (`GWMC-W-0000001`); ward, zone, supply area, map point | Done |
| WB-02 | Address, door no., old assessment no., UPIN on every connection; not validated against Property Tax | Done |
| WB-03 | Consumer details, configurable category list, pipe size, metered flag, connection date, status; several connections per property allowed | Done |
| WB-04 | Duplicate warning at filing and at activation: same address, or within `connection.duplicateRadiusM` (15 m) | Done |
| WB-05 | Configurable workflow with SLA per step and escalation; estimate from the fee table (connection charge by pipe size, road cutting per metre, deposit by category) | Done |
| WB-06 | Owner, category and pipe-size change; temporary and permanent disconnection; restore after temporary disconnection; regularisation through the illegal-connection case | Done |
| WB-07 | Search by consumer no., old no., name, mobile, address, UPIN; click a connection on the map to open it | Done |
| WB-08 | `wtr_connection_history`: field, old, new, who, when, why | Done |

### 3.2.2 Meters, readings, non-metered billing
| ID | How it is met | Status |
|---|---|---|
| WB-10 | Meter register: serial, make, size, seal, initial reading, date fixed, status | Done |
| WB-11 | Replacement records the old meter's final reading; consumption since its last billed reading carries into the new meter's first reading | Done |
| WB-12 | Reading routes, reader assignment, ordered connections, progress per route and per reader | Done |
| WB-13 | Field app screen: offline route sheet, IndexedDB queue, meter photo, GPS, time; sync when online | Done (web, not a native Android app — see §5) |
| WB-14 | Configurable no-reading reasons; "meter faulty" marks the meter faulty | Done |
| WB-15 | Lower-than-last, high or low readings held for officer review; flagged bills are held | Done |
| WB-16 | Average of the last N actual bills (`billing.averageMethod`, N = 3) | Done |
| WB-17 | Flat rate by category and pipe size, per month × cycle length | Done |
| WB-18 | Consumer self-reading with photo through the citizen portal; same checks | Done |
| WB-19 | One reading intake for field, office, bulk file and AMR sources | Done |

### 3.2.3 Tariffs and billing
| ID | How it is met | Status |
|---|---|---|
| WB-20 | Tariff per category: telescopic slabs, minimum, fixed charge, cess, effective date | Done (rates are placeholders — Appendix A #2) |
| WB-21 | Proposal → Commissioner approval (maker ≠ checker); old versions kept | Done |
| WB-22 | Free allowance per category tariff | Done |
| WB-23 | Bill run by cycle, route by route; configurable cycle length | Done |
| WB-24 | Bill shows consumer/connection, readings, consumption, slab lines, arrears, penalty, due date, UPI QR | Done (UPI payee is a placeholder) |
| WB-25 | Bill link sent by WhatsApp/SMS, shown in the portal, printable | Stand-in sender; Bluetooth spot printing needs the native app |
| WB-26 | Correction = approved adjustment entry; the bill row never changes | Done |

### 3.2.4 Demand, collection, receipts
| ID | How it is met | Status |
|---|---|---|
| WB-30 | Counter, field and CSC: cash, cheque, DD, UPI QR. Portal/app/BBPS: online flow | Counter: Done. Online: Stand-in gateway |
| WB-31 | Receipt issued immediately with unique number and verification QR; SMS copy | Done (SMS stand-in) |
| WB-32 | Part payments; configurable order (penalty → fees → arrears → current); excess held as advance | Done |
| WB-33 | Cancellation only through approved reversal | Done |
| WB-34 | Daily reconciliation of statement vs online receipts; mismatch list | Done (statement from stand-in gateway or CSV upload) |
| WB-35 | Status check completes orders whose confirmation was lost; never twice | Done (against the stand-in) |
| WB-36 | Cheque return reverses the receipt, adds the notified charge, informs the payer | Done |
| WB-37 | Day-end closing by collector, cash verified by a different cashier | Done |
| WB-38 | Refund of excess payment or of the deposit after permanent disconnection, via approval (pay or adjust) | Done |

### 3.2.5 Arrears, penalty, disconnection, reconnection
| ID | How it is met | Status |
|---|---|---|
| WB-40 | Penalty once per overdue bill on its unpaid part, at the notified rate | Done (rate placeholder — Appendix A #4) |
| WB-41 | Ageing bands by bill due date, by ward; defaulters list by amount | Done |
| WB-42 | Reminders before and after the due date, de-duplicated | Done (sender stand-in) |
| WB-43 | Notice when dues pass the amount or age threshold; listed for disconnection after the notice period | Done |
| WB-44 | Field disconnection with photo, GPS and time; no bills while disconnected; arrears kept | Done |
| WB-45 | Reconnection fee raised; work order released with SLA once everything is paid; field completes it | Done |
| WB-46 | Waiver and write-off through approval with per-role amount limits | Done |

### 3.2.6 Complaints, illegal connections, consumption analysis
| ID | How it is met | Status |
|---|---|---|
| WB-50 | Leak, no supply, dirty water, meter, billing, other; photo and location; portal/app/WhatsApp/call centre sources | Done (WhatsApp/call-centre channels enter through the same API) |
| WB-51 | Auto-assignment by ward, SLA by type, escalation chain, closing photo and remark required, citizen informed at each step | Done |
| WB-52 | Field staff log leaks from the field app | Done |
| WB-53 | Report with geo-tagged photo → inspection → regularise with penalty, disconnect, or close | Done |
| WB-54 | Zero consumption for N cycles; sudden rise or drop | Done |
| WB-55 | Comparison with the same category and ward | Done |

### 3.2.7 GIS dashboard and reports
| ID | How it is met | Status |
|---|---|---|
| WB-60 | Map of connections coloured by payment status, category or connection status | Done (OpenStreetMap base as stand-in for Bhuvan) |
| WB-61 | Complaint/leak hotspots and illegal-connection cases on the map | Done |
| WB-62 | DCB register and efficiency by ward or zone for any period | Done |
| WB-63 | Billing, reading completion by route/reader, meter status, disconnections/reconnections, complaint SLA | Done |
| WB-64 | Commissioner dashboard: today, year-to-date vs target, weakest wards, complaints past SLA | Done (target is a placeholder setting) |
| WB-65 | Daily/monthly summary by account head | Done (codes and layout are placeholders — Appendix A #10) |
| WB-66 | Excel (CSV with BOM) and PDF (print / save as PDF) on every report; schedule kept in settings | Exports: Done. Scheduled email: Open (needs the email service) |

### Non-functional and integration readiness
| ID | How it is met | Status |
|---|---|---|
| WB-NF-10 | Role permissions per action; ward/zone restriction from the user's assignment | Done |
| WB-NF-11 / NF-15 | OTP login, SSO second factor, session timeout | Platform services — Open |
| WB-NF-13 | Append-only audit of every create, change, approval and payment, with user and IP | Done (login events are logged by the platform, not this module) |
| WB-NF-20 / NF-21 / NF-22 | Consent recorded on applications; Aadhaar hashed and shown masked; public verification shows no personal data | Done |
| WB-NF-23 / WB-IR-04 | Register export without mobile/identity fields | Done |
| WB-NF-32 / NF-33 / NF-63 | Idempotent payments, offline-safe readings, resumable bill runs | Done |
| WB-NF-42 | Plain-language error messages | Done |
| WB-NF-50 / NF-64 | All rates, SLAs, workflows and categories configurable | Done |
| WB-NF-65 | Photos and documents in file storage outside the database (`WATER_STORAGE_DIR`) | Done (local folder stands in for object storage) |
| WB-IR-01 / IR-09 | Versioned REST API (`/api/v1/water`), used by the module's own screens; OpenAPI at `/docs` | Done |
| WB-IR-02 | Event outbox for all listed events | Done (not yet published to a bus) |
| WB-IR-03 | UPIN field with source | Done |
| WB-IR-05 | Account head, amount, date, ward, mode and reference on every financial row | Done |
| WB-IR-06 | Property-tax dues check is a workflow step, switched off | Done |
| WB-IR-07 | Meter make/size/serial kept for later Inventory matching | Done |
| WB-IR-08 | Link switches in `integrationLinks`, all off | Done |
| WB-IR-10 | Gateway, SMS/WhatsApp and base map stand-ins behind the module's interfaces | Done |
| WB-IR-11 | Every water API call logged with caller, path, result and time | Done |

## 5. Known limits and open items

1. **Not verified on PostgreSQL.** Everything was built and tested on SQLite (end-to-end test plus browser
   checks). The models avoid database-specific features, but the module must be run once against
   PostgreSQL/PostGIS (`docker compose up`) before it is relied on.
2. **Placeholder rates.** Every tariff, fee, deposit, penalty, threshold, account head, UPI payee and collection
   target is a placeholder pending SRS Appendix A (items 2–5, 9, 10). Change them under Administration and
   Tariffs; no code change is needed.
3. **Stand-ins (WB-IR-10).** Payment gateway/UPI/BBPS, SMS/WhatsApp/email sender, and the OpenStreetMap base map.
   Aadhaar eKYC, DigiLocker, Meeseva/CDMA APIs and bank statement formats are not connected (Appendix A #13).
4. **Field app.** Built as a mobile web screen with an offline queue. The SRS calls for a native Android app
   with Bluetooth thermal printing; that is a separate build.
5. **Telugu coverage.** Navigation, titles, common labels, bills, receipts and notices are bilingual. Some
   secondary labels and column headers are still English.
6. **Scheduler.** Penalty, reminders, notices, escalations and the gateway status check run from
   `POST /api/v1/water/jobs/daily` (or the buttons on the Arrears screen); a production scheduler must call it daily.
7. **Bundle budget.** The production build passes, but the initial bundle is 514 kB against the 500 kB
   *warning* budget (the error budget is 1 MB). The Water screens are lazy loaded; the +18 kB is shared
   framework code they use.
