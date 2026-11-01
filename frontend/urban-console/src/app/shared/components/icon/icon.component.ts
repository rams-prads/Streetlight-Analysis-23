import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

const REMIX_NAME_MAP: Record<string, string> = {
  // Navigation & Controls
  search: 'ri-search-2-line',
  bell: 'ri-notification-3-line',
  notification: 'ri-notification-3-line',
  user: 'ri-user-3-line',
  lock: 'ri-lock-2-line',
  shield: 'ri-shield-check-line',
  refresh: 'ri-refresh-line',
  menu: 'ri-menu-line',
  close: 'ri-close-line',
  x: 'ri-close-line',
  'chevron-right': 'ri-arrow-right-s-line',
  'chevron-left': 'ri-arrow-left-s-line',
  'arrow-left': 'ri-arrow-left-s-line',
  'arrow-right': 'ri-arrow-right-s-line',
  sync: 'ri-refresh-line',

  // 19 Municipal ERP Modules
  ptx: 'ri-government-line',
  demand: 'ri-file-list-3-line',
  wtr: 'ri-drop-line',
  grv: 'ri-feedback-line',
  fin: 'ri-bank-card-line',
  dms: 'ri-folder-shield-2-line',
  trl: 'ri-store-2-line',
  uch: 'ri-hand-coin-line',
  bpm: 'ri-home-gear-line',
  tpl: 'ri-compass-3-line',
  fnc: 'ri-fire-line',
  swm: 'ri-delete-bin-line',
  eng: 'ri-tools-line',
  slm: 'ri-lightbulb-line',
  prk: 'ri-tree-line',
  inv: 'ri-archive-line',
  hrm: 'ri-team-line',
  mpm: 'ri-building-line',
  units: 'ri-building-2-line',
  building: 'ri-building-line',
  lgl: 'ri-scales-3-line',
  gsc: 'ri-medal-line',

  // Super Admin specific
  parcels: 'ri-government-line',
  landmark: 'ri-government-line',
  collection: 'ri-apps-2-line',
  layers: 'ri-stack-line',
  efficiency: 'ri-git-branch-line',
  chart: 'ri-file-chart-line',
};

@Component({
  selector: 'app-icon',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (isRemix) {
      <i
        [class]="remixClass"
        [style.font-size.px]="size"
        [style.width.px]="size"
        [style.height.px]="size"
        class="remix-icon-glyph"
        aria-hidden="true"
      ></i>
    } @else {
      <span
        class="svg-icon-wrapper"
        [style.width.px]="size"
        [style.height.px]="size"
        [ngClass]="name"
      >
        <svg
          [attr.width]="size"
          [attr.height]="size"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="svg-icon"
        >
          <!-- 1. PTX - Property Tax -->
          @if (name === 'ptx' || name === 'demand') {
            <path d="M6 3h12l4 6-10 12L2 9l4-6z" />
            <path d="M10 7h4" />
            <path d="M10 11h4" />
            <path d="M10 7v7a2 2 0 0 0 2 2" />
          }

          <!-- 2. WTR - Water & Utility -->
          @else if (name === 'wtr') {
            <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
          }

          <!-- 3. GRV - Citizen Desk & Grievances -->
          @else if (name === 'grv') {
            <path
              d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"
            />
            <path d="M9 10h.01" />
            <path d="M15 10h.01" />
            <path d="M12 14h.01" />
          }

          <!-- 4. FIN - Finance & Accounting -->
          @else if (name === 'fin') {
            <rect x="2" y="4" width="20" height="16" rx="2" />
            <line x1="2" y1="10" x2="22" y2="10" />
            <line x1="7" y1="15" x2="7.01" y2="15" />
            <line x1="12" y1="15" x2="12.01" y2="15" />
            <line x1="17" y1="15" x2="17.01" y2="15" />
          }

          <!-- 5. DMS - Document Management -->
          @else if (name === 'dms') {
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          }

          <!-- 6. TRL - Trade Licence -->
          @else if (name === 'trl') {
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            <polyline points="9 22 9 12 15 12 15 22" />
          }

          <!-- 7. UCH - User Charges -->
          @else if (name === 'uch') {
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="3" y1="9" x2="21" y2="9" />
            <line x1="9" y1="21" x2="9" y2="9" />
          }

          <!-- 8. BPM - Building Permissions -->
          @else if (name === 'bpm') {
            <polygon points="12 2 2 7 12 12 22 7 12 2" />
            <polyline points="2 17 12 22 22 17" />
            <polyline points="2 12 12 17 22 12" />
          }

          <!-- 9. TPL - Town Planning -->
          @else if (name === 'tpl') {
            <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
            <line x1="8" y1="2" x2="8" y2="18" />
            <line x1="16" y1="6" x2="16" y2="22" />
          }

          <!-- 10. FNC - Fire NOC -->
          @else if (name === 'fnc') {
            <path d="M12 2c1 3 4 5 4 9a6 6 0 0 1-12 0c0-4 3-6 4-9 1 3 3 4 4 0z" />
          }

          <!-- 11. SWM - Solid Waste -->
          @else if (name === 'swm') {
            <rect x="1" y="3" width="15" height="13" />
            <polygon points="16 8 20 8 23 11 23 16 16 16 16 8" />
            <circle cx="5.5" cy="18.5" r="2.5" />
            <circle cx="18.5" cy="18.5" r="2.5" />
          }

          <!-- 12. ENG - Engineering Projects -->
          @else if (name === 'eng') {
            <rect x="2" y="6" width="20" height="12" rx="2" />
            <path d="M12 12h.01" />
            <path d="M17 12h.01" />
            <path d="M7 12h.01" />
          }

          <!-- 13. SLM - Street Lights -->
          @else if (name === 'slm') {
            <line x1="9" y1="18" x2="15" y2="18" />
            <line x1="10" y1="22" x2="14" y2="22" />
            <path
              d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"
            />
          }

          <!-- 14. PRK - Parks & Horticulture -->
          @else if (name === 'prk') {
            <path d="M12 10v12" />
            <path d="M12 10a5 5 0 0 1 5-5 5 5 0 0 1 5 5c0 2.5-1.5 4.5-3.5 5.5" />
            <path d="M12 10a5 5 0 0 0-5-5 5 5 0 0 0-5 5c0 2.5 1.5 4.5 3.5 5.5" />
          }

          <!-- 15. INV - Inventory & Stores -->
          @else if (name === 'inv') {
            <path
              d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"
            />
            <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          }

          <!-- 16. HRM - Payroll & HR -->
          @else if (name === 'hrm') {
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          }

          <!-- 17. MPM - Municipal Property -->
          @else if (name === 'mpm' || name === 'units' || name === 'building') {
            <rect x="4" y="2" width="16" height="20" rx="2" />
            <line x1="9" y1="6" x2="9.01" y2="6" />
            <line x1="15" y1="6" x2="15.01" y2="6" />
            <line x1="9" y1="10" x2="9.01" y2="10" />
            <line x1="15" y1="10" x2="15.01" y2="10" />
            <line x1="9" y1="14" x2="9.01" y2="14" />
            <line x1="15" y1="14" x2="15.01" y2="14" />
            <line x1="9" y1="18" x2="15" y2="18" />
          }

          <!-- 18. LGL - Legal Case Management -->
          @else if (name === 'lgl') {
            <path d="M12 3v18" />
            <path d="M4 7h16" />
            <polygon points="4 7 1 14 7 14 4 7" />
            <polygon points="20 7 17 14 23 14 20 7" />
          }

          <!-- 19. GSC - Government Schemes -->
          @else if (name === 'gsc') {
            <circle cx="12" cy="12" r="10" />
            <circle cx="12" cy="12" r="6" />
            <circle cx="12" cy="12" r="2" />
          }

          <!-- Common controls -->
          @else if (name === 'chevron-right' || name === 'arrow-right') {
            <polyline points="9 18 15 12 9 6" />
          } @else if (name === 'chevron-left' || name === 'arrow-left') {
            <polyline points="15 18 9 12 15 6" />
          } @else if (name === 'close' || name === 'x') {
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          } @else {
            <circle cx="12" cy="12" r="9" />
            <path d="M12 8v4" />
            <path d="M12 16h.01" />
          }
        </svg>
      </span>
    }
  `,
  styles: [
    `
      :host {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        line-height: 1;
        vertical-align: middle;
      }
      .remix-icon-glyph {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        line-height: 1;
        font-style: normal;
      }
      .svg-icon-wrapper {
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .svg-icon {
        width: 100%;
        height: 100%;
        stroke: currentColor;
      }
    `,
  ],
})
export class IconComponent {
  @Input() name: string = 'circle';
  @Input() size: number = 20;

  get isRemix(): boolean {
    return this.name.startsWith('ri-') || !!REMIX_NAME_MAP[this.name];
  }

  get remixClass(): string {
    if (this.name.startsWith('ri-')) {
      return this.name;
    }
    return REMIX_NAME_MAP[this.name] || 'ri-circle-line';
  }
}
