# DevPilot — Design System

**Last updated:** 2026-09-28
**Applies to:** the Next.js frontend (Phase 2) and any dashboards/docs pages.

> Visual language: a calm, precise **developer tool** — think Linear/Vercel/GitHub. Dark-first, high legibility, generous whitespace, restrained color used to signal state (plan/validation/approval). Built on Tailwind CSS + shadcn/ui, so tokens below map to CSS variables and Tailwind theme extensions.

---

## 1. Color palette

Defined as HSL CSS variables (shadcn/ui convention). Ship **dark as the default**, light as opt-in.

### Neutrals (slate-based)
| Token | Light | Dark | Use |
|---|---|---|---|
| `--background` | `0 0% 100%` | `222 18% 8%` | Page background |
| `--surface` / `--card` | `210 20% 98%` | `222 16% 11%` | Cards, panels |
| `--muted` | `210 16% 93%` | `222 14% 16%` | Subtle fills, hovers |
| `--border` | `214 20% 88%` | `222 12% 20%` | Borders, dividers |
| `--foreground` | `222 30% 12%` | `210 20% 96%` | Primary text |
| `--muted-foreground` | `222 10% 42%` | `215 14% 62%` | Secondary text |

### Brand & accent
| Token | Value (light / dark) | Use |
|---|---|---|
| `--primary` | `221 83% 53%` / `217 91% 60%` | Primary actions, links (indigo/blue) |
| `--primary-foreground` | `0 0% 100%` | Text on primary |
| `--accent` | `262 83% 58%` / `263 90% 66%` | Highlights, agent/AI touches (violet) |

### Semantic / state (maps to the run state machine)
| Token | Value | Meaning |
|---|---|---|
| `--success` | `142 71% 45%` | Tests passed, approved, completed |
| `--warning` | `38 92% 50%` | Awaiting approval, review needed |
| `--destructive` | `0 72% 51%` | Failed, rejected, delete |
| `--info` | `199 89% 48%` | Planning / running / neutral status |

**Rules:** color signals meaning, never decoration. Every text/background pair must meet **WCAG AA (≥4.5:1)** for body, ≥3:1 for large text. Don't rely on color alone — pair status colors with an icon and a label.

## 2. Typography

| Role | Font | Notes |
|---|---|---|
| UI / body | **Inter** (var), system-ui fallback | Primary interface font |
| Headings | Inter (tighter tracking) | `letter-spacing: -0.02em` on h1–h3 |
| Code / diffs / logs | **JetBrains Mono** (or `ui-monospace`) | Diffs, run logs, tokens |

### Type scale (rem)
| Step | Size / line-height | Use |
|---|---|---|
| xs | 0.75 / 1rem | captions, labels |
| sm | 0.875 / 1.25rem | secondary text |
| base | 1 / 1.5rem | body |
| lg | 1.125 / 1.75rem | lead text |
| xl | 1.25 / 1.75rem | card titles |
| 2xl | 1.5 / 2rem | section headings |
| 3xl | 1.875 / 2.25rem | page titles |
| 4xl | 2.25 / 2.5rem | hero |

Weights: 400 body, 500 medium (labels/buttons), 600 semibold (headings). Avoid 700+ except sparingly.

## 3. Spacing, radius, elevation
- **Spacing scale:** 4px base (Tailwind default) — use `2/3/4/6/8/12/16`.
- **Radius:** `--radius: 0.625rem` (10px); inputs/buttons `md`, cards `lg`, pills `full`.
- **Shadows:** subtle only. `sm` for cards, `md` for popovers/menus. In dark mode prefer borders over shadows.
- **Container:** max-width `1200px`, 16px side gutter on mobile, comfortable line length (~72ch) for text.

## 4. Components (shadcn/ui baseline)
- **Buttons:** primary (filled), secondary (muted), ghost, destructive. One primary action per view.
- **Status badges:** map to semantic tokens + icon (e.g. `AWAITING_APPROVAL` → warning + clock).
- **Diff viewer:** monospace, green/red gutters using success/destructive at low opacity, never pure saturated fills.
- **Run timeline:** vertical stepper reflecting the state machine (Planning → Validating → Awaiting approval → …).
- **Forms:** label above input, inline validation, `422` field errors surfaced next to the field.
- **Empty / loading / error states:** every data view must define all three.

## 5. Motion & accessibility
- Motion: 150–200ms ease-out for hovers/entrances; respect `prefers-reduced-motion`.
- Full keyboard navigability; visible focus rings (`--ring` = primary at reduced alpha).
- Icons: one set (Lucide, ships with shadcn/ui).
- Test both themes; never hardcode hex in components — use the tokens above.

## 6. Implementation notes
- Define tokens in `globals.css` under `:root` and `.dark`; extend `tailwind.config.ts` to read them.
- Keep a single source of truth for tokens; components reference semantic tokens, not raw colors.
