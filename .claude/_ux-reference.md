# UX Reference

## Theme Stack

| Theme | Purpose |
|-------|---------|
| `frontend/Eventim/eventim` | Base theme (parent: Magento/blank), LESS |
| `frontend/Eventim/futurecraft` | Child of eventim |
| `frontend/Eventim/futurecraft_hyva` | Hyvä + Tailwind CSS v4 — active storefront |

New frontend work targets **futurecraft_hyva**. Use Tailwind utility classes and CSS custom properties; not LESS.

---

## Brand Colors

### CSS Custom Properties (futurecraft_hyva)

```css
--color-primary:          #004179   /* deep blue — header, links, focus rings */
--color-primary-lighter:  #0C538A
--color-primary-darker:   #002C52

--color-secondary:        #FBBB01   /* yellow — buttons, accents, sale labels */
--color-secondary-lighter:#FFC30F
--color-secondary-darker: #E5AA00

--color-on-primary:       #FFFFFF   /* text on primary bg */
--color-on-secondary:     #333333   /* text on secondary/yellow bg */

--color-accent:           #FBBB01
--color-accent-hover:     #FFC30F
```

### Neutrals

| Token / Value | Use |
|---------------|-----|
| `#FFFFFF` | Surface, form bg |
| `#F5F5F5` / `#F0F0F0` | Page background, light containers |
| `#E2E2E2` / `#EBEBEB` | Borders, dividers |
| `#B8B8B8` | Form input border |
| `#7D7D7D` | Secondary text |
| `#333333` / `#313131` | Body text |
| `#121212` | Near-black |

### Status Colors

| State | Background | Text / Border |
|-------|-----------|---------------|
| Success | `#c9e3ac` | `#30BF30` |
| Error | `#FFADAD` | `#E85D5D` |
| Warning | `#FFFCF2` | yellow border |
| Info/Notice | `#CFE0E8` | blue border |

### Layout Chrome

| Area | Background | Text |
|------|-----------|------|
| Header | `#004179` | `#FFFFFF` |
| Mobile header | `#002C52` | `#FFFFFF` |
| Footer | `#1C1C1C` | `#FFFFFF` |
| Footer border | `#464646` | — |
| Social icon bg | `#395D81` | — |

---

## Typography

```css
--font-sans: 'Overpass', sans-serif;
```

| Weight | Value |
|--------|-------|
| Light | 300 |
| Regular | 400 |
| Medium | 500 |
| Semi-bold | 600 |
| Bold | 700 |

### Type Scale

| Level | Size |
|-------|------|
| Display | `51.41px` |
| H1 | `39.55px` |
| H2 | `31.25px` |
| H3 | `23.4px` |
| Body | `1rem` (16px) |
| Small | `0.875rem` |

---

## Spacing Scale (Tailwind v4)

`--spacing(n)` = n × 4px

| Token | px |
|-------|----|
| 1 | 4 |
| 2 | 8 |
| 3 | 12 |
| 4 | 16 |
| 5 | 20 |
| 6 | 24 |
| 8 | 32 |
| 9 | 36 |
| 11 | 44 |
| 12 | 48 |

---

## Breakpoints

| Name | Width |
|------|-------|
| XS (mobile) | < 768px |
| SM (tablet) | 768px – 991px |
| MD (desktop) | 992px |
| LG | 1280px |
| XL / max-width | 1430px |

---

## Buttons

### CSS Variables (set per variant)

```css
--btn-bg, --btn-stroke, --btn-color
--btn-hover-bg, --btn-hover-color
--btn-active-bg, --btn-active-color
--btn-disabled-bg, --btn-disabled-stroke, --btn-disabled-color
```

### Variants

**Primary** (`.btn-primary`)
```
bg: #FBBB01   border: 2px solid #FBBB01   text: #333333   weight: 600
hover-bg: #FFC30F
disabled: bg var(--color-gray-50), text var(--color-gray-500)
border-radius: 5px   min-width: 185px (legacy) / fluid (Hyva)
```

**Secondary** (`.btn-secondary`)
```
bg: #FFFFFF   border: 2px solid #FBBB01   text: #333333
hover-text: #FFC30F
```

**Sizes**
```
default: padding-block --spacing(2), padding-inline --spacing(4)
lg (.btn-size-lg): px-10 py-4 text-lg
sm (.btn-size-sm): px-2 py-2 text-sm
```

**Shadow**
```
default: rgba(0,0,0,0.1) 0 0.25rem 1rem 0
hover:   rgba(0,0,0,0.2) 0 0.375rem 1.5rem 0
```

---

## Links

```
color: #333333
hover-color: #333333
underline: 3px bottom bar in #FBBB01, animates on hover
transition: 0.3s ease-in-out
```

---

## Form Elements

```css
--form-radius:       var(--radius-lg)
--form-stroke:       var(--color-slate-400)   /* #B8B8B8 */
--form-active-color: var(--color-primary)
```

| Property | Value |
|----------|-------|
| Border | `2px solid var(--form-stroke)` |
| Background | `#FFFFFF` |
| Border-radius | `var(--radius-lg)` |
| Placeholder | `#ACACAC` |
| Focus outline | `2px solid var(--color-primary)`, offset `2px` |
| Transition | `150ms cubic-bezier(0.25, 0, 0.4, 1)` |

**Checkbox/radio size:** `--spacing(4.5)` (18px), border `2px`

**Toggle switch:** width `--spacing(9)`, height `--spacing(5)`, fully rounded, transition `150ms`

---

## Components

### Cards
```
rounded-lg  bg-white  p-6  shadow-sm
header: mb-4 border-b pb-4
footer: mt-4 border-t pt-4
```

### Messages / Alerts
```
rounded-lg  p-4  text-sm  border
success: border-green-200 bg-green-50 text-green-800
error:   border-red-200   bg-red-50   text-red-800
warning: border-yellow-200 bg-yellow-50 text-yellow-800
info:    border-blue-200   bg-blue-50   text-blue-800
```

### Quantity Input
```
buttons: w-10 h-10  border border-gray-300  bg-gray-50  hover:bg-gray-100
input:   w-12  text-center
```

### Checkout Progress Bar
```
h-1  rounded-full  gap-2
inactive: bg-gray-200
active/complete: bg-primary (#004179)
label: text-sm
```

### Slider / Carousel
```
snap-gap: --spacing(4)
padding-block: --spacing(6)
marker: --spacing(4) × --spacing(4), border 1px, border-radius 1rem
active-marker-width: --spacing(7)
transition: 300ms
```

---

## Focus & Interaction

```
outline: 2px solid var(--color-primary)
outline-offset: 2px  (shrinks to 0 on :active, transition 150ms)
cursor: pointer on all interactive elements
cursor: not-allowed on disabled
touch-action: manipulation
```

---

## Layout

| Property | Value |
|----------|-------|
| Main margin-block | `--spacing(8)` (32px) |
| Column gap H | `--spacing(4)` (16px) |
| Column gap V | `--spacing(8)` (32px) |
| Sidebar (MD) | 240px |
| Sidebar (LG/XL) | 320px |
| Header height mobile | `h-16` (4rem) |
| Header height desktop | `lg:h-[90px]` |

---

## Class Naming Conventions

| Prefix | Domain |
|--------|--------|
| `.btn-` | Buttons (`btn-primary`, `btn-secondary`, `btn-size-lg`) |
| `.form-` | Form elements (`form-input`, `form-swatch`) |
| `.field-` | Field wrappers (`field-error`, `field-required`) |
| `.message-` | Alerts (`message-success`, `message-error`) |
| `.snap-` | Carousels (`snap-track`, `snap-marker`, `snap-pager`) |
| `.opc-` | Checkout (`opc-progress-bar`, `opc-wrapper`) |
| `.card-` | Cards (`card-header`, `card-body`, `card-footer`) |
| `.page-` | Layouts (`page-wrapper`, `page-main`) |

**State conventions:** `._active` / `.is-active` / `[aria-current="page"]`; `:disabled` / `[aria-disabled="true"]`; `:focus-visible` for keyboard focus.
