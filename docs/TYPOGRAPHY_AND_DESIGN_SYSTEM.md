# Urban Integrated Municipal ERP — Typography & Design System Specification
## Hake Technologies Official Colour & Typography Guide

**Author**: Hake Technologies · @VinayBabu  
**Date Baseline**: 29 October 2026  
**Source Baseline**: TIDC Geospatial Portal Deck (October 2026), Proposals, DPRs & Hake Geospatial Portal UI  
**Target Resolution**: 1920x1080 (Primary Desktop Workstations) · 1366x768 (Field Laptops) · 375x812 (Inspector Mobile)  
**Accessibility Target**: WCAG 2.1 (4.5:1 for body text, 3:1 for large text 18 pt+ or 14 pt bold)  

---

## 1. Purpose & Brand Vision

Hake uses one deep teal-navy, one teal and one saffron accent, set in **Calibri** for Office files and **Noto Sans** for web and apps. Every value below was sampled from the **TIDC Geospatial Portal deck (October 2026)**, ensuring all slide decks, DPRs, proposals and app screens match what clients have already seen.

---

## 2. Colour Palette & Design Tokens

### 2.1 Core Brand Colours
Deep teal-navy carries the brand; teal is the secondary voice. Keep logo navy for the logo itself, not for slides or text.

| Name | Hex | RGB | Role / Usage Context |
|---|---|---|---|
| **Deep teal-navy** | `#0E3A52` | `14, 58, 82` | Dark slide backgrounds, slide titles, headings, body text on light backgrounds |
| **Hake teal** | `#1B8C77` | `27, 140, 119` | Subtitles, icon circles, secondary buttons, links |
| **Logo navy** | `#032065` | `3, 32, 101` | Logo only |
| **App sidebar** | `#071532` | `7, 21, 50` | Portal sidebar and dark app chrome |

### 2.2 Accent & Status Colours
Saffron is the single highlight colour; green and red carry status. Alert red is used for plot status, errors, and warnings.

| Name | Hex | RGB | Role / Usage Context |
|---|---|---|---|
| **Saffron** | `#D98A2B` | `217, 138, 43` | Key numbers on navy, "Proposed" pills, call-to-action buttons |
| **Check green** | `#3D8D51` | `61, 141, 81` | Delivered / done ticks, success, allotted plots |
| **Alert red** | `#B23A2E` | `178, 58, 46` | Errors, encroached or disputed plots |
| **Mist blue** | `#80A0AF` | `128, 160, 175` | Subtitles and secondary text on navy |

### 2.3 Card Tints and Neutrals
Card tints sit behind navy text on feature cards; use them in a fixed order so a grid of six cards always looks consistent.

| Name | Hex | RGB | Role / Fixed Card Order |
|---|---|---|---|
| **Sand** | `#CBBEA3` | `203, 190, 163` | Card 1 |
| **Peach** | `#F0D0AA` | `240, 208, 170` | Card 2 |
| **Mint** | `#8CE9D8` | `140, 233, 216` | Card 3 |
| **Sky** | `#9FC7E4` | `159, 199, 228` | Card 4 |
| **Grey** | `#D9D9D9` | `217, 217, 217` | Card 5 |
| **Rose** | `#E7AEA5` | `231, 174, 165` | Card 6 |
| **Page cream** | `#F7F5F1` | `247, 245, 241` | Light slide and page background |
| **Panel green** | `#E9F0E6` | `233, 240, 230` | "Delivered" panels |
| **Panel beige** | `#E5DFD2` | `229, 223, 210` | "Proposed" panels, text call-out boxes |
| **White** | `#FFFFFF` | `255, 255, 255` | Text on navy, screenshot frames |

### 2.4 Header Gradient Bar (Light Slides & Headers)
Left to right progression:
`#0E3A52` $\rightarrow$ `#82683C` $\rightarrow$ `#D98A2B` $\rightarrow$ `#808B4F` $\rightarrow$ `#278C72` $\rightarrow$ `#17635B`

```css
background: linear-gradient(90deg, #0E3A52 0%, #82683C 20%, #D98A2B 40%, #808B4F 60%, #278C72 80%, #17635B 100%);
```

---

## 3. Usage Rules & Contrast Ratios

### 3.1 Proportional Distribution Rule
Aim for roughly:
- **60%** Page cream or Deep teal-navy (Canvas & base structural layers)
- **25%** Teal and card tints (Secondary panels, cards, and chrome)
- **10%** Saffron (Highlights, action buttons, KPI callouts)
- **5%** Status colours (Green ticks, red errors)

### 3.2 WCAG 2.1 Contrast Matrix

| Text on Background | Contrast Ratio | Usage Rules |
|---|---|---|
| **Navy on cream** (`#0E3A52` on `#F7F5F1`) | **11.0:1** | Any text size |
| **White on navy** (`#FFFFFF` on `#0E3A52`) | **12.0:1** | Any text size |
| **Navy on any card tint** (`#0E3A52` on Tints 1–6) | **6.5:1 or higher** | Any text size |
| **White on teal** (`#FFFFFF` on `#1B8C77`) | **4.1:1** | Large text and buttons only |
| **Teal on cream** (`#1B8C77` on `#F7F5F1`) | **3.8:1** | Subtitles and headings only |
| **Saffron on navy** (`#D98A2B` on `#0E3A52`) | **4.4:1** | Large numbers and headings only |
| **Saffron on cream** (`#D98A2B` on `#F7F5F1`) | **2.5:1** | **Avoid** (fails contrast) |
| **White on saffron** (`#FFFFFF` on `#D98A2B`) | **2.8:1** | **Avoid**; put navy text on saffron buttons |

### 3.3 Core Design Application Laws
- **One accent per view**: Saffron highlights a key number or a pill, never body text.
- **Tints for backgrounds only**: Keep tints for card backgrounds only; never use them for text or icons.
- **Semantic status discipline**: 
  - `Green` = Done, delivered, or allotted plot
  - `Saffron` = Proposed, pending, or in-progress
  - `Red` = Error, encroached, disputed plot, or problem
- **Logo usage**: Do not place the logo on teal or saffron. Use the white pill version on navy and the plain version on cream.

---

## 4. Typography System

### 4.1 Font Family Mapping

| Where | Primary Font | Fallback Font | Notes |
|---|---|---|---|
| **Web portal & mobile app** | **Noto Sans** | `system-ui, sans-serif` | Free on Google Fonts; weights 400 (Regular) and 600 (Bold) |
| **Indian-language text** | **Noto Sans Bengali / Devanagari / Telugu** | — | Multilingual portals & chatbot; matches Noto Sans metrics |
| **Code, coordinates, IDs** | **JetBrains Mono** | `Consolas, monospace` | For plot IDs, ULPIN, PTIN, EPSG codes, lat/long |
| **Slides (PowerPoint)** | Calibri | Arial | Bold for titles and card headings, Regular for body |
| **Documents (Word, DPRs, proposals)** | Calibri | Arial | Same weights as slides |

- **Weights**: Use two weights only: **Regular (400)** and **Bold (600 on web)**.
- **Casing**: Write headings in **sentence case** (e.g., *"Phase I outcomes"*, not *"Phase I Outcomes"*).

### 4.2 Type Scale (Measured from 16:9 Deck to Web Screen Equivalents)

| Element | Slides (pt) | Web (px) | Weight | Colour |
|---|---|---|---|---|
| **Cover / section title** | 40 pt | 40px (`2.5rem`) | Bold (600) | White on navy |
| **Slide / page title (H1)** | 30 pt | 32px (`2.0rem`) | Bold (600) | Deep teal-navy (`#0E3A52`) |
| **Subtitle** | 16 pt | 18px (`1.125rem`) | Regular (400) | Hake teal (`#1B8C77`) / Mist blue on navy (`#80A0AF`) |
| **Card heading (H3)** | 16 pt | 18px (`1.125rem`) | Bold (600) | Deep teal-navy (`#0E3A52`) |
| **Body text** | 14–16 pt | 16px (`1.0rem`) | Regular (400) | Deep teal-navy (`#0E3A52`) |
| **Key statistic** | 40 pt | 40px (`2.5rem`) | Bold (600) | Saffron on navy (`#D98A2B`) |
| **Caption, page number, footnote** | 10 pt | 12px (`0.75rem`) | Regular (400) | Mist blue (`#80A0AF`) or Grey (`#D9D9D9`) |

---

## 5. Quick Reference (CSS Tokens)

```css
:root {
  /* Core Brand Tokens */
  --hake-navy: #0E3A52;
  --hake-teal: #1B8C77;
  --hake-saffron: #D98A2B;
  --hake-green: #3D8D51;
  --hake-red: #B23A2E;
  --hake-logo-navy: #032065;
  --hake-sidebar: #071532;
  --hake-mist: #80A0AF;
  --hake-cream: #F7F5F1;

  /* Card Tints & Panel Tokens */
  --tint-sand: #CBBEA3;
  --tint-peach: #F0D0AA;
  --tint-mint: #8CE9D8;
  --tint-sky: #9FC7E4;
  --tint-grey: #D9D9D9;
  --tint-rose: #E7AEA5;
  --panel-green: #E9F0E6;
  --panel-beige: #E5DFD2;

  /* Typography Families */
  --font-sans: "Noto Sans", Calibri, Arial, system-ui, sans-serif;
  --font-mono: "JetBrains Mono", Consolas, monospace;
  --font-indic-bengali: "Noto Sans Bengali", sans-serif;
  --font-indic-devanagari: "Noto Sans Devanagari", sans-serif;
  --font-indic-telugu: "Noto Sans Telugu", sans-serif;
}
```

---

## 8. Standard Component Layout Architecture (Official Standard for All SUVIDHA Components)

Every future functional component and management view across SUVIDHA must strictly obey this standardized 4-tier visual structure:

```
+-------------------------------------------------------------------------------------------------------+
|  Tier 1: Page Header                                                                                  |
|  [Page Title]                                                      [ ↻ Refresh ]   [ + Primary Action ]|
|  [Page Subtitle / Scope Description]                                                                  |
+-------------------------------------------------------------------------------------------------------+
|  Tier 2: Unified Filter & Search Bar                                                                  |
|  [ 🔍 Search input field (placeholder: "Search ...") ]           [ Filter Dropdown 1 ▾ ] [ Filter 2 ▾ ]|
+-------------------------------------------------------------------------------------------------------+
|  Tier 3: Modern Card Table Container (White background, border-radius: 12px, border: 1px solid #e5e7eb)|
|  +-------------------------------------------------------------------------------------------------+  |
|  | [AVATAR] ENTITY NAME | CODE | ID (UUID) | SLUG | CONTACT | LANGUAGE | STATUS | ACTIONS (Edit,Del)|  |
|  |-------------------------------------------------------------------------------------------------|  |
|  | M  Municipality      | TR   | a8d72a4d.. | /tri | email   | Bengali  | ● Active | [Edit] [Del] [Act]|  |
|  +-------------------------------------------------------------------------------------------------+  |
|  |  Tier 3b: Integrated Pagination Bar                                                               |
|  |  Showing 1 to X of Y items                         Rows per page: [ 5 ▾ ]       [ < ] [ 1 ] [ > ]  |
|  +-------------------------------------------------------------------------------------------------+  |
+-------------------------------------------------------------------------------------------------------+
|  Tier 4: Page Footer Note                                                                             |
|  © 2026 SUVIDHA. All rights reserved.                                                                 |
+-------------------------------------------------------------------------------------------------------+
```

### Key Architectural Guidelines:
1. **Tier 1 (Page Header)**:
   - Left: `h1.page-title` (font-size: `1.5rem` mobile, `1.65rem` desktop, font-weight `700`, color `#111827`) + `p.page-subtitle` (font-size: `0.875rem`, color `#6b7280`).
   - Right: Outlined `.btn-refresh` (`height: 40px`, border: `#e5e7eb`, bg: `#ffffff`, text: `#374151`) + Primary `.btn-primary` (`height: 40px`, bg: `#2563eb`, text: `#ffffff`).
2. **Tier 2 (Unified Filter Bar)**:
   - Search box on left with magnifying glass icon and clear button (`min-height: 40px`, border: `#e5e7eb`, border-radius: `8px`).
   - Suffix dropdown filters on right (`height: 40px`, border: `#e5e7eb`, border-radius: `8px`, chevron indicator).
3. **Tier 3 (Modern Card Table Container)**:
   - Container card: `background: #ffffff`, `border: 1px solid #e5e7eb`, `border-radius: 12px`, `box-shadow: 0 1px 3px rgba(0,0,0,0.03)`.
   - Headers: Uppercase, font-size: `0.72rem`, font-weight: `600`, letter-spacing: `0.05em`, color: `#6b7280`.
   - Entity cell: Square rounded avatar (`38px x 38px`, background: `#fae8ff`, text: `#c026d3`) + primary title + secondary muted subtitle.
   - Code & ID pills: Monospace pills with copy action on UUID.
   - Status pill: Fully rounded pill with colored status dot (`#dcfce7` active, `#fef9c3` draft, `#fee2e2` suspended).
   - Row actions: Compact action buttons side by side (`Edit` outlined grey, `Delete` outlined red, `Suspend` / `Activate` contextual).
4. **Tier 3b (Pagination Bar)**:
   - Showing record range info on left.
   - Rows per page dropdown picker and numeric page navigation on right.
5. **Tier 4 (Footer Note)**:
   - Clean centered copyright notice: `© 2026 SUVIDHA. All rights reserved.`
