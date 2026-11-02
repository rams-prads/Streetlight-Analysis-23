---
name: suvidha-ui-development
description: Enforces core SUVIDHA municipal ERP UI guidelines, including clean titles with hover tooltips (no raw Level 1/Level 2 text pills), mandatory main-component vs dedicated dialog folder structure, environment.ts configuration, and mobile-first responsive architecture.
---

# SUVIDHA UI & Frontend Development Skill

Use this skill whenever creating or refactoring frontend Angular components across the SUVIDHA platform.

---

## 1. Mandatory Frontend Directory & Component Structure

Every management, directory, or process module in `src/app/modules/` MUST strictly adhere to this folder architecture:

```
src/app/modules/<domain>/<feature>/
├── <feature>.component.ts             # MAIN COMPONENT: Directory view, search/filter signals, table, pagination, dialog triggers
├── <feature>.component.html           # 4-tier layout template, delegates modals to child dialog components
├── <feature>.component.scss           # Mobile-first list styles, card container, table, pagination
└── dialogs/                           # MANDATORY DIALOGS SUBDIRECTORY
    ├── <feature>-form-dialog/         # Dedicated Add / Edit Modal Dialog
    │   ├── <feature>-form-dialog.component.ts
    │   ├── <feature>-form-dialog.component.html
    │   └── <feature>-form-dialog.component.scss
    └── <feature>-<sub-entity>-dialog/ # Dedicated Secondary / Child Entity Dialog (e.g. structure, audit, allocations)
        ├── <feature>-<sub-entity>-dialog.component.ts
        ├── <feature>-<sub-entity>-dialog.component.html
        └── <feature>-<sub-entity>-dialog.component.scss
```

### Separation of Concerns:
| Component Type | Responsibilities | Must NOT Contain |
|---|---|---|
| **Main Component** (`<feature>.component.ts`) | Table/grid display, data loading (`get*`), search signals, filter dropdowns, pagination, dialog open/close state signals, delete actions. | Form inputs, validation logic, upload handlers, child sub-entity editing. |
| **Form Dialog** (`<feature>-form-dialog/`) | Add/Edit modal card, reactive form payload, input validation, state/city dropdown cascades, draft/save submit handlers. | Full directory tables, global pagination. |
| **Child Entity Dialog** (`<feature>-<sub-entity>-dialog/`) | Sub-hierarchies (e.g. Wards & Zones under ULB, Subscriptions under State, Users under Department). | Unrelated parent entity updates. |

### Dialog Binding Contract:
```html
<!-- In main component HTML -->
<app-<feature>-form-dialog
  [isOpen]="isFormDialogOpen()"
  [isEditing]="isEditing()"
  [selectedItem]="selectedItem()"
  (close)="closeFormDialog()"
  (saveSuccess)="onItemSaved($event)"
></app-<feature>-form-dialog>
```

---

## 2. Clean Page Headings & Tenancy Level Tooltips (Mandatory)
- **NO Raw Text Pills Beside Headings**: Never render visible text badges like `Level 1` or `Level 2` in page headers.
- **Hover Tooltips**: Provide tenancy level context strictly via hover tooltips on the title element:
  ```html
  <h1
    class="page-title"
    data-tooltip="Level 2 Tenancy — City / ULB Municipal Body"
    title="Level 2 Tenancy — City / ULB Municipal Body"
  >
    ULB / City Management
  </h1>
  ```
- **Tooltip SCSS Pattern**:
  ```scss
  .page-title {
    position: relative;
    cursor: default;
    display: inline-block;

    &[data-tooltip] {
      &::after {
        content: attr(data-tooltip);
        position: absolute;
        bottom: calc(100% + 8px);
        left: 0;
        background: #0f172a;
        color: #f8fafc;
        font-size: 0.75rem;
        font-weight: 500;
        line-height: 1.2;
        padding: 0.4rem 0.65rem;
        border-radius: 6px;
        white-space: nowrap;
        opacity: 0;
        visibility: hidden;
        pointer-events: none;
        transition: opacity 0.15s ease, transform 0.15s ease;
        transform: translateY(4px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        z-index: 100;
      }
      &::before {
        content: '';
        position: absolute;
        bottom: calc(100% + 2px);
        left: 18px;
        border: 6px solid transparent;
        border-top-color: #0f172a;
        opacity: 0;
        visibility: hidden;
        pointer-events: none;
        transition: opacity 0.15s ease, transform 0.15s ease;
        transform: translateY(4px);
        z-index: 100;
      }
      &:hover::after,
      &:hover::before,
      &:focus-visible::after,
      &:focus-visible::before {
        opacity: 1;
        visibility: visible;
        transform: translateY(0);
      }
    }
  }
  ```

---

## 3. Environment Variable Discipline
- Never hardcode backend URLs (e.g. `http://localhost:8000/api/v1`) or Keycloak URLs in services or components.
- Always import from `src/environments/environment.ts` (`environment.apiUrl`, `environment.keycloakUrl`).

---
## 4. Mobile-First Responsive SCSS
- Write compact mobile viewports (`375px - 767px`) first without media queries.
- Progressively enhance with `@media (min-width: 768px)` and `@media (min-width: 1024px)` using `min-width` queries only.
- Minimum $44 \times 44\text{px}$ touch targets for all interactive controls (buttons, links, pills).

---

## 5. Strict Zero-Hardcoding Mandate (Multi-Government & Multi-Tenant Deployment)

SUVIDHA is designed to deploy across diverse state governments, union territories, municipal corporations, and municipal councils across India. **NOTHING MAY BE HARDCODED.**

1. **Dynamic Jurisdictions & Tenancy**:
   - **Never hardcode static lists of states** (e.g. `['TG', 'MH', 'KA', 'TR']`), ULB/city codes, zones, or wards in components, services, or templates.
   - States MUST be dynamically loaded from `TenantManagementService.getStateTenants()`.
   - ULBs MUST be dynamically filtered by parent state via `UlbManagementService.getUlbs({ stateCode })`.
   - Zones MUST be dynamically loaded from `UlbManagementService.getZones(ulbCode)`.
   - Wards MUST be dynamically loaded from `UlbManagementService.getWards(ulbCode)` and filtered by selected `zoneId`.

2. **No Mock / Fallback Arrays on Error**:
   - NEVER provide dummy or hardcoded mock arrays inside `.subscribe({ error: () => { ... } })` blocks.
   - On API error, reset state signals to empty arrays (`[]`), log/toast the failure via `DialogService.showToast(...)`, and let user retry.

3. **Master Data & Modules**:
   - Roles, permission codes, departments, document categories, and module catalogs MUST be fetched dynamically from backend database endpoints (`/api/v1/modules`, `/api/v1/iam/roles`, `/api/v1/iam/users`, etc.).

4. **Multi-Government Localization & Theming**:
   - Portal titles, state emblems, administrative contacts, languages, and timezone settings MUST be resolved from active tenant context, never hardcoded string constants.
