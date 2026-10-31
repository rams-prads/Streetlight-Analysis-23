# Urban Integrated Municipal ERP — Agent & Developer Context
## Shared Context for AI Agents and Human Developers

Welcome to the Urban Integrated Municipal ERP repository. This document defines the architectural laws, tenancy models, and directory boundaries that all contributors must obey.

---

## 1. Project Domain & Hierarchy Vision

Urban is an enterprise-grade, multi-tier SaaS municipal enterprise resource planning (ERP) platform designed for Urban Local Bodies (ULBs) and State Urban Development Departments.

### Hierarchical Administrative Model:
1. **Level 0: "The Boss" (Platform Super Admin)**:
   - Global multi-tenant visibility across all States, Cities, and Departments.
   - Cross-state analytics, financial consolidation, and system administration.
2. **Level 1: Tenant (State, e.g. Telangana `TG`, Maharashtra `MH`)**:
   - Subscribes to any subset of the **19 Platform Modules**.
   - Manages State-level officers and provisions child Sub-Tenants (Cities/ULBs/Departments).
3. **Level 2: Sub-Tenant (City / ULB / Department, e.g. GWMC, GHMC, CDMA-TP)**:
   - Receives module allocations strictly from the parent State Tenant's active subscriptions.
   - Manages local city inspectors, bill collectors, citizens, and local municipal operations.

---

## 2. 19 Official Modules & Component RBAC

The platform incorporates 19 standardized municipal modules across 5 domains:
1. **Revenue & Billing**: Property Tax (`PTX`), Water & Sewerage (`WTR`), Trade Licences (`TRL`), User Charges (`UCH`), Municipal Property (`MPM`).
2. **Finance & Administration**: Finance & Accounting (`FIN`), Payroll & HR (`HRM`), Document Management (`DMS`), Inventory & Stores (`INV`).
3. **Planning & Regulation**: Building Permissions (`BPM`), Town Planning (`TPL`), Legal Cases (`LGL`), Fire NOC (`FNC`).
4. **Infrastructure & Field Operations**: Solid Waste (`SWM`), Engineering Projects (`ENG`), Street Lights (`SLM`), Parks & Horticulture (`PRK`).
5. **Citizen Engagement & Welfare**: Citizen Grievance & RTI (`GRV`), Government Schemes (`GSC`).

**Granular Component RBAC**:
- Every module decomposes into 12 to 33 specific processes/components (total 405 components).
- Refer to [docs/MODULE_COMPONENTS_CATALOGUE.md](file:///Users/sagarsingharoy/Documents/urban/docs/MODULE_COMPONENTS_CATALOGUE.md) for the complete list.
- Permissions must be validated at the component action level (e.g., `PTX-P10:APPROVE`).

---

## 3. Strict Coding Conventions & Architecture Boundaries

### 3.1 Backend Architecture (FastAPI + Async SQLAlchemy)
- Root: `backend/services/core_service/app/`
- Every database query touching municipal entities MUST filter by `tenant_id` and (when in city context) `sub_tenant_id`.
- Pydantic models must inherit from `CamelModel` (`app/schemas/`) with `to_camel` alias generator so JSON keys match frontend conventions.
- Cache keys in Redis must follow strict scoped formatting:
  `stats:tenant:{tenant_id}:sub:{sub_tenant_id}:{resource}`
- Authentication must resolve active context via `get_current_tenant` and `get_current_sub_tenant` dependencies from `X-Tenant-ID` and `X-Sub-Tenant-ID` headers.
- Mandatory Search, Limit & Skip Pagination: Every listing endpoint serving table or collection data MUST support search filtering with `search: Optional[str] = Query(None)` across primary textual columns, alongside `skip: int = Query(0, ge=0)` and `limit: int = Query(50, ge=1, le=100)`. Queries must execute `.offset(skip).limit(limit)`.

### 3.2 Frontend Architecture (Angular 22 Standalone)
- Root: `frontend/urban-console/src/app/`
- Framework: **Angular 22.2 Standalone Components** (no obsolete NgModules).
- State: Use Angular **Signals** (`signal()`, `computed()`, `effect()`) for reactive state.
- Styling: Custom SCSS adhering to [docs/TYPOGRAPHY_AND_DESIGN_SYSTEM.md](file:///Users/sagarsingharoy/Documents/urban/docs/TYPOGRAPHY_AND_DESIGN_SYSTEM.md). Do NOT introduce TailwindCSS.
- API Services: Must pass `Authorization: Bearer <token>`, `X-Tenant-ID`, and `X-Sub-Tenant-ID` headers on every call.
- Environment: API & Auth server URLs MUST come from `src/environments/environment.ts`, never hardcoded string literals.
- Clean Headings: Do NOT display raw visible tenancy text pills (e.g. 'Level 1', 'Level 2') in page titles. Tenancy level context must be displayed as a tooltip on hover (`data-tooltip` & `title`).
- Modular Dialogs: Never put table listing and add/edit forms in a single component. Create separate standalone dialog components under `dialogs/` for Add/Edit and child entity management.
- Mandatory Search & Limit/Skip Pagination: Every table component listing entities MUST implement a live search filter input and the standardized pagination bar with rows-per-page limit selector (`[5, 10, 20, 50]`), current page index (`skip = (currentPage - 1) * limit`), page navigation controls, and "Showing X to Y of Z entries" counter.
- Strict Zero-Hardcoding Mandate: Platform deploys to multiple state and municipal governments. Hardcoding states, ULBs, zones, wards, departments, or identity providers in frontend or backend code is strictly forbidden. All hierarchies and master data must be database-driven and loaded dynamically from APIs. Never use mock fallback arrays in error handlers.

### 3.3 Mobile-First Architecture & Responsive Standard (Mandatory Skill)
All frontend development across SUVIDHA must strictly obey a **Mobile-First Responsive Architecture**:
1. **Base-First Mobile Breakpoint**: Default SCSS must target compact mobile viewports (`375px - 767px`) first without media queries. Progressive enhancement to tablet (`@media (min-width: 768px)`) and workstation desktop (`@media (min-width: 1024px)`, `@media (min-width: 1440px)`) must occur using `min-width` queries only. Never use `max-width` desktop-down degradation.
2. **Ergonomic Touch Targets**: All interactive controls (buttons, nav links, icon actions, pills) must maintain minimum $44 \times 44\text{px}$ touch target bounds on touch viewports.
3. **Adaptive Navigation Drawer**: Side navigation must collapse to a slide-over drawer or compact icon rail on viewports $<1024\text{px}$, and support minimized icon-only state with accessible tooltips on desktop.
4. **Fluid Flex & Grid Layouts**: Prevent horizontal overflow. All grids must declare `grid-template-columns: repeat(auto-fit, minmax(..., 1fr))` or flex with `min-width: 0; flex-wrap: wrap;`.
5. **Field Inspector Optimization**: High-contrast, sunlight-readable color palettes and dense single-column card layouts for municipal field inspectors.

---

## 4. Pre-Push Validation Enforced
A Git pre-push hook (`.git/hooks/pre-push` and `scripts/validate_structures.sh`) is active. Pushes will be rejected automatically if:
- Backend code fails Python compilation or deviates from the `app/api/v1/`, `app/core/`, `app/db/`, `app/schemas/` structure.
- Frontend code fails `ng build` or introduces broken imports / missing models.

---

## 5. Mandatory Version Bump Rule Before Every Commit
Before creating any git commit, the application version and version code MUST be updated:
1. **Target Files**:
   - `frontend/urban-console/src/app/core/constants/version.ts`
   - `frontend/urban-console/package.json`
2. **Increment Rules**:
   - `versionCode`: Increment integer by +1 on every commit (e.g., `100` -> `101`).
   - `version`: Increment semantic version string (`MAJOR.MINOR.PATCH`, e.g., `1.0.0` -> `1.1.0` for features, `1.1.1` for fixes).
   - `releaseDate`: Update to current Month and Year (e.g. `November 2026`).
3. **Automated Helper**:
   - Run `./scripts/bump_version.sh [patch|minor|major]` before staging changes.
4. **Zero Bypass**:
   - AI agents and developers must NEVER create a commit or propose commit messages without verifying that version and versionCode are bumped.

