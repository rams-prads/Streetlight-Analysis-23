# Rule: Backend & Frontend Coding Structure Consistency

## 1. Backend Invariants (`backend/services/core_service/app/`)

1. **Layer Separation**:
   - `api/v1/`: Controllers and HTTP route handlers only. No raw SQL or direct DB schema alters.
   - `core/`: Authentication, security, tenant resolution, configuration, and redis clients.
   - `db/`: SQLAlchemy declarative models (`models.py`), database session (`session.py`), and seeding (`seed.py`).
   - `schemas/`: Pydantic v2 schemas (`auth.py`, `property.py`, `tenant.py`, etc.).
2. **Naming & Serialization**:
   - All response and request schemas MUST inherit from `CamelModel` (`populate_by_name=True`, `alias_generator=to_camel`).
   - Backend Python attributes use `snake_case`; external JSON payloads use `camelCase`.
3. **Multi-Tier Tenant Isolation**:
   - Every router querying municipal entities MUST declare `tenant_id: str = Depends(get_current_tenant)` and where applicable `sub_tenant_id: Optional[str] = Depends(get_current_sub_tenant)`.
   - Never perform bare queries like `select(PropertyParcel)` without `.where(PropertyParcel.tenant_id == tenant_id)`.
4. **Caching Discipline**:
   - Cache keys must be scoped with tenant context: `prefix:{tenant_id}:{sub_tenant_id}`.
5. **Mandatory Search, Limit & Skip Pagination**:
   - Every entity listing and collection endpoint MUST support `search: Optional[str] = Query(None)` across primary textual columns, as well as `skip: int = Query(0, ge=0)` and `limit: int = Query(50, ge=1, le=100)`.
   - SQL queries must filter by search criteria when provided and execute `.offset(skip).limit(limit)`. Total entity count should be computed via `select(func.count(...))` for accurate pagination ranges.

---

## 2. Frontend Invariants (`frontend/urban-console/src/app/`)

1. **Architecture & Framework**:
   - Angular 22 standalone components only. No `NgModule` modules.
   - State management MUST use Angular Signals (`signal<T>()`, `computed()`, `effect()`).
2. **Model Alignment**:
   - Every entity received from FastAPI must have a corresponding TypeScript interface in `src/app/core/models/` matching the camelCase fields of the backend `CamelModel`.
3. **Styling & Design System**:
   - Use custom SCSS with variables defined in `src/styles.scss` and `docs/TYPOGRAPHY_AND_DESIGN_SYSTEM.md`.
   - Do NOT introduce TailwindCSS or bootstrap utility bloat.
4. **Mobile-First Responsive Architecture (Mandatory Skill)**:
   - Base-first mobile breakpoint: Write styles for compact mobile viewports (375px-767px) first without media queries; progressively enhance to tablet (`@media (min-width: 768px)`) and desktop (`@media (min-width: 1024px)`) using `min-width` only.
   - Maintain minimum 44x44px ergonomic touch targets for interactive controls.
   - Navigation must collapse to slide-over drawer or compact icon rail on <1024px viewports.
   - Fluid grid layouts (`repeat(auto-fit, minmax(..., 1fr))`) preventing horizontal overflow.
5. **Header Injection**:
   - All HTTP requests initiated through Angular services MUST inject `Authorization`, `X-Tenant-ID`, and `X-Sub-Tenant-ID` headers.
6. **Standard Component 4-Tier Visual Architecture (Mandatory)**:
   - All management and directory views across SUVIDHA must implement the official 4-tier layout:
     - **Tier 1 (Page Header)**: Title + Subtitle on left; Outlined Refresh + Primary Action on right.
     - **Tier 2 (Filter & Search Bar)**: Search input with magnifying glass + Suffix select dropdowns on right.
     - **Tier 3 (Card Table Container)**: 12px rounded white card container with uppercase muted headers, entity initial avatars, code/uuid monospace pills, status indicator pills with dot, compact action buttons (`Edit`, `Delete`, `Suspend`/`Activate`), and integrated bottom pagination bar.
     - **Tier 4 (Footer Note)**: Centered `© 2026 SUVIDHA. All rights reserved.`.
7. **Geographic Authority (State, District, City Tables)**:
   - Geographic data (States, Districts, Cities/ULBs) MUST be queried exclusively from Postgres database tables (`states`, `districts`, `cities`), NEVER hardcoded in UI templates.
8. **Clean Headers & Hover Tooltips for Tenancy Levels (Mandatory)**:
   - Do NOT display raw visible text badges like 'Level 1' or 'Level 2' beside page titles.
   - Keep page headings clean. Tenancy level context MUST be shown via a hover tooltip on the heading (`data-tooltip="Level X Tenancy — ..."` and `title="..."`).
9. **Component Modularity & Dedicated Dialog Directory Structure (Mandatory)**:
   - NEVER code table listings, forms, and secondary modules into a single monolithic component.
   - Every feature must follow this directory layout:
     ```
     <feature>/
     ├── <feature>.component.ts       # Table, filter/search signals, pagination, dialog triggers
     ├── <feature>.component.html     # 4-tier layout delegating modals to child dialog components
     ├── <feature>.component.scss     # Mobile-first list styles
     └── dialogs/
         ├── <feature>-form-dialog/   # Add / Edit Modal Dialog component
         └── <feature>-<child>-dialog/# Child / secondary hierarchy dialog component
     ```
   - Parent directory components must remain lean, containing only list state, filters, pagination, and dialog toggle bindings.
10. **Environment Variable Discipline**:
   - All backend endpoints and auth server URLs MUST be consumed via `src/environments/environment.ts` (`environment.apiUrl`, `environment.keycloakUrl`), NEVER hardcoded as strings.
11. **Mandatory Table Search & Pagination Architecture**:
   - Every component table listing entities MUST implement both a live search input filter and the standardized pagination bar (`.suvidha-pagination-bar` or `.pagination-bar`):
     - Interactive search input box with search icon and real-time query filtering.
     - Rows-per-page limit selector (`[5, 10, 20, 50]`).
     - Current page signal and computed offset (`skip = (currentPage - 1) * pageSize`).
     - Page navigation controls (`prevPage()`, `nextPage()`, `goToPage(p)`).
     - Informational counter: `Showing X to Y of Z entries`.
     - Data slicing or backend `limit`/`skip` parameter passing.
12. **Strict Zero-Hardcoding Mandate (Multi-Government Law)**:
   - SUVIDHA deploys to multiple state and municipal governments. Static hardcoded arrays for states, ULBs, zones, wards, departments, or identity providers are strictly forbidden.
   - All jurisdictional, organizational, and authorization structures must be fetched dynamically from database APIs (`TenantManagementService`, `UlbManagementService`, `IamUserService`, `IamRbacService`).
   - Mock/dummy fallback arrays inside `.subscribe({ error: ... })` handlers are prohibited. Set empty arrays and surface toast errors.

