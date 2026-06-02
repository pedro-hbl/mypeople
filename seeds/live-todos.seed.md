# SEED — Plow "Live To‑Dos"

> A self-contained product spec (a "seed") for a single-file, dependency-free, localStorage-only live to-do board.
> **To build:** hand this file to a coding agent — *"Hydrate this seed: build the app it specifies in one static
> HTML file until every §10 verification journey passes."* The agent outputs `todos.html` and self-runs §10.
> A reference build is included alongside as **`live-todos.todos.html`**. *(Hardened: a blind, zero-context agent
> reproduced the app one-shot — 17/17 §10 journeys PASS.)*

> **What this is.** This is a *seed*: a single self‑contained specification (the recipe) for an
> entire project. It contains **no implementation code**. Hand this file to a coding agent; the
> agent "hydrates" it — building the whole app from scratch until every acceptance test below
> passes. The implementation (the HTML/CSS/JS) is just an artifact; *this spec* is the product.
>
> **Definition of done.** A coding agent has succeeded when it has produced a single static HTML
> file that, opened directly in a browser (no server, no build step), reproduces the app described
> here and passes **every** verification journey in §10. Because LLMs are non‑deterministic, this
> spec pins down the exact constants (keys, colors, fonts, strings, formats) that matter for
> convergence — treat the values in §3, §6, §7 and §11 as **fixed**, not as suggestions.

---

## 1. Purpose & context

A **to‑do list designed to be shown on a live stream.** The author runs a coding livestream and
keeps this board on screen so viewers can see what he's working on in real time — hence the
"On air" indicator, the oversized editorial typography (readable from a distance / on a video
feed), and the always‑running live clock.

It is deliberately **tiny and dependency‑free**: one HTML file, no backend, no accounts, no build
tooling. All state lives in the browser's `localStorage`, so the board survives reloads and browser
restarts on the same machine/profile, but is private to that browser.

Key character traits the rebuild must preserve:
- **Single file.** Everything (markup, styles, logic) ships in one `.html` document.
- **Zero server.** Opening the file via `file://` must fully work.
- **Persistent.** Reloading the page never loses data.
- **Dark, premium, editorial** look — big serif headlines, a "volt" lime accent, film‑grain texture.
- **Bilingual by design** (see §11): English chrome, Portuguese item/status microcopy. This mix is
  intentional — do **not** "normalize" it to one language.

---

## 2. Technical approach (prerequisites & constraints)

- **Deliverable:** one static HTML file (the canonical filename is `todos.html`).
- **Prerequisites to run:** only a modern web browser. No Node, no package manager, no server, no
  network *required* for logic. (Fonts load from a CDN when online — see §6 — but the app must remain
  fully functional offline, falling back to system fonts.)
- **No frameworks / no libraries / no bundler.** Plain HTML + CSS + vanilla JavaScript, all inline
  in the single file. No React/Vue/jQuery, no CSS framework.
- **Persistence:** browser `localStorage` only (schema in §3). No IndexedDB, cookies, or network.
- **No external state** beyond fonts; everything else is inlined (including the logo and the grain
  texture, which are inline SVG / data‑URI — see §6).

---

## 3. Data model (the schema — fixed)

All state is a **single JSON value** stored in `localStorage` under the **exact key**:

```
plow.stream.todos.v1
```

The stored value is a **JSON array of todo objects, in display order** (index `0` renders at the
**top**). Shape:

- **Todo** (a top‑level item):
  - `id` — string, unique, stable for the item's lifetime.
  - `text` — string, the item's content.
  - `done` — boolean.
  - `created` — number, creation time as epoch **milliseconds**.
  - `subs` — array of **Sub** objects (may be empty).
- **Sub** (a sub‑task nested under a todo):
  - `id` — string, unique.
  - `text` — string.
  - `done` — boolean.
  - `created` — number, epoch milliseconds.

Illustrative example (data, not code):

```json
[
  { "id": "lp3k2a9f1", "text": "Ship the seed", "done": false, "created": 1748707200000,
    "subs": [
      { "id": "lp3k4b2", "text": "Write the spec", "done": true,  "created": 1748707260000 },
      { "id": "lp3k5c8", "text": "Add tests",      "done": false, "created": 1748707320000 }
    ] },
  { "id": "lp3k7d4", "text": "Reply in chat", "done": true, "created": 1748707000000, "subs": [] }
]
```

**ID generation.** IDs must be collision‑resistant without a server. Generate each id from a
timestamp component plus a short random component (e.g. base‑36 of the current time concatenated
with a few random base‑36 characters). The exact algorithm is free as long as ids are unique within
a session and stable once assigned.

**Ordering rules (important for convergence):**
- The array order **is** the on‑screen order.
- Adding a top‑level todo **prepends** it (new items appear at the **top** of the list).
- Adding a sub‑task **appends** it (new subs appear at the **bottom** of that todo's sub‑list).

**Migration / resilience on load.** When reading existing storage, the app must be defensive:
- If the stored value is missing or fails to parse, start from an empty array.
- If it is not an array, treat it as empty.
- For every todo lacking a `subs` array, add an empty one.
- For every sub missing `done`, default it to `false`; missing `created`, default to "now";
  missing `id`, assign a fresh one.
- Immediately **persist** this migrated shape back to storage (so older saved data is upgraded
  on first load).

**Write policy.** Persist the full array to `localStorage` after **every** mutation (add, edit,
toggle, delete, reorder — at both todo and sub level).

---

## 4. Feature list (complete)

Top‑level todos:
1. **Add todo** — via the input field (Enter) or the "Add" button. Whitespace‑only input is ignored.
2. **Complete/uncomplete** — a large checkbox toggles `done`.
3. **Edit text inline** — the item text is directly editable in place.
4. **Delete** — removes the item (no confirmation).
5. **Reorder** — move an item up/down one position with ↑/↓ controls.
6. **Add sub‑task** — from a "+ sub‑tarefa" button on the item, or by pressing **Tab** while editing
   the item's text.

Sub‑tasks (nested one level only — subs have no subs):
7. **Toggle, edit, delete, reorder** — same affordances as todos, at a smaller scale.
8. **Auto‑drop empties** — a sub left blank when focus leaves it is removed automatically.

Ambient / chrome:
9. **Live counts** — done / pending / total, **counting subs as well as todos**.
10. **Live clock** — current time (updating every second) and the date.
11. **Relative "added … ago" timestamps** — under every todo and sub, refreshed every second.
12. **Empty state** — a friendly message when there are no todos.
13. **"On air" indicator** — a pulsing live badge in the header.
14. **Persistence** — everything survives reload (per §3).

---

## 5. UI / layout spec

Overall: a single centered column, **max width ~1400px**, generous padding (roughly `48px 56px`
on desktop, reduced on narrow screens), on a near‑black background with a faint film‑grain overlay
covering the whole viewport.

**Header** (row, space‑between, wraps on narrow screens):
- **Left — brand block:**
  - A **64×64 rounded‑square logo** (≈14px radius) containing the Plow brandmark (volt‑green tile
    with a grove‑green glyph — see §6 for the asset).
  - Headline **"Live to‑dos"** in the large italic serif, where "to‑dos" is set in a softer/muted
    tone and uses a non‑breaking hyphen so it never wraps mid‑word. Font size is fluid
    (`clamp` ≈ 38–60px).
  - Below the headline, an **"On air"** pill: uppercase, bold, small, on a translucent volt
    background, led by a small **pulsing volt dot**.
- **Right — clock:**
  - Large **volt‑colored serif time** (fluid ≈ 48–76px) showing `HH:MM:SS`.
  - Beneath it, a **mono, uppercase, letter‑spaced date** in muted tone (see §7 for exact format).
  - Before the first tick, show placeholders (time `--:--`, date `—`).
- A thin bottom border separates the header from the body.

**Add bar** (below header): a large text input (flex‑grows to fill) with placeholder
`Add a to-do and hit Enter…`, next to a **volt "Add" button**. The input shows a focus ring in the
grove‑green color. The button lifts slightly and glows on hover.

**Counts row** (below add bar): three small mono pills — `X done` (green), `X pending` (amber),
`X total` (muted). Values update live (§9).

**Todo list:** a vertical stack of cards, gap ≈14px. Each **todo card**:
- A large **checkbox toggle** on the left (≈42px rounded square; empty outline when pending, filled
  green with a white check when done).
- A **body** containing:
  - The **editable item text** in the large serif (fluid ≈ 26–38px). When done, the text is
    struck through and dimmed.
  - A **meta row**: a status **badge** (§7) plus a relative **"ago"** timestamp (§7).
  - The nested **sub‑list** (see below), hidden entirely when empty.
  - A **"+ sub‑tarefa"** dashed‑outline button to add a sub.
- A right‑side **control cluster**: ↑ (up), ↓ (down), × (delete). Up is disabled on the first item,
  down on the last.
- Done cards are slightly faded. New cards animate in with a short fade/slide‑up.

**Sub‑item rows** are visually subordinate: indented under the parent with a left border rule,
smaller checkbox (≈30px), the **sub text in the sans font** (smaller, ≈18–22px), the same badge +
ago meta, and a smaller ↑/↓/× cluster. An empty sub shows placeholder text `sub-tarefa…`.

**Empty state:** when there are zero todos, the list area shows a centered italic‑serif line
(exact string in §7).

**Responsive:** at narrow widths (≈≤860px) the header stacks vertically, the clock left‑aligns,
and outer padding shrinks.

---

## 6. Design system (brand — fixed values)

**Fonts** (load from Google Fonts when online; fall back to the listed system stacks offline):
- **Serif** — `Instrument Serif` (italic used for the headline & emphasis), fallback `Georgia, serif`.
  Used for: the headline, the clock time, todo text, the empty‑state line.
- **Sans** — `DM Sans`, fallback `system-ui, -apple-system, sans-serif`. Used for: body, input,
  buttons, badges, sub text.
- **Mono** — `DM Mono`, fallback `SF Mono, Consolas, monospace`. Used for: counts pills, the date,
  the "ago" timestamps.

**Color tokens** (use these exact hex/rgba values):
- `--midnight: #01000A` (used for text on the volt button)
- `--volt: #D5EF8A` (primary lime accent — clock, add button, live dot, focus/hover accents)
- `--grove: #5e7a5e` (input focus ring, logo glyph)
- `--iris: #C4BFFF` (reserved accent)
- `--dark-bg: #111110` (page background)
- `--dark-card: #1a1a18`, surfaces `rgba(255,255,255,0.05)` / `rgba(255,255,255,0.08)`
- `--dark-border: rgba(255,255,255,0.09)`, stronger border `rgba(255,255,255,0.15)`
- `--text-dark: #F0F0E8` (primary text), `--muted-dark: rgba(240,240,232,0.45)` (muted text)
- `--success: #34c759` (done), `--danger: #ff3b30` (delete), `--warning: #febc2e` (pending)

The app effectively runs in a **dark theme**; the light tokens may exist but the rendered board is
dark.

**Film‑grain overlay (non‑negotiable, per brand).** A fixed, full‑viewport noise texture sits above
everything at very low opacity (~0.04) and ignores pointer events. Implement it as an **inline SVG
fractal‑noise (feTurbulence) data‑URI** so nothing is fetched from the network.

**Logo / brandmark.** The header logo is the Plow "P" mark: a **volt (#D5EF8A) rounded tile** with
the **grove (#5E7A5E)** stylized letterform glyph, inlined as SVG (no external image). *Judgment
call / asset note:* a logo cannot be reconstructed pixel‑accurately from prose. To converge exactly,
reuse the brandmark SVG from the existing `todos.html` verbatim (it is a static brand asset, not
program logic). If the original is unavailable, render a faithful substitute: a 64px rounded‑square
volt tile bearing a grove‑green "P"‑style mark.

**Motion:** subtle only — the live dot pulses (~1.6s loop); new items fade/slide up (~0.2s); buttons
have small hover transforms. Nothing flashy.

---

## 7. Microcopy & formats (fixed strings)

Reproduce these **exactly** (note the deliberate English/Portuguese mix):

- Document title: `Plow — Live To-Dos`
- Headline: `Live to‑dos` ("to‑dos" emphasized/muted, non‑breaking hyphen)
- Live pill: `On air`
- Input placeholder: `Add a to-do and hit Enter…`
- Add button: `Add`
- Counts pills: `<n> done`, `<n> pending`, `<n> total`
- Status badges: pending → `⏳ pendente` (amber); done → `✓ feito` (green)
- Add‑sub button: `+ sub-tarefa`
- Empty sub placeholder: `sub-tarefa…`
- Empty state line: `Nada ainda. Adiciona o primeiro to-do acima.`
- Accessibility labels (Portuguese): check toggle `Marcar como feito` / `Marcar como pendente`;
  up `Mover para cima`; down `Mover para baixo`; delete `Remover`.

**Clock format.** Time is 24‑hour, zero‑padded `HH:MM:SS`, updated every second. Date is rendered as
`<Weekday>, <day> <Mon> <year>` using **Portuguese** names:
- Weekdays (Sun→Sat): `Domingo, Segunda, Terça, Quarta, Quinta, Sexta, Sábado`
- Months (Jan→Dec): `Jan, Fev, Mar, Abr, Mai, Jun, Jul, Ago, Set, Out, Nov, Dez`
- Example: `Domingo, 31 Mai 2026`.

**Relative "ago" format (Portuguese).** Based on elapsed time since `created`:
- `< 60s` → `há <s>s adicionado`
- `< 60min` → `há <m> min adicionado`
- `< 24h` → `há <h>h <m>min adicionado` (minutes = remainder)
- otherwise → `há <d>d adicionado`

---

## 8. Behaviors & interactions (detailed)

**Adding a todo.** Pressing Enter in the input, or clicking "Add", adds the trimmed text as a new
todo **at the top** of the list. Whitespace‑only input is ignored (no item created). After clicking
"Add", the input is cleared and re‑focused; after Enter, the input is cleared.

**Editing a todo.** The item text is edited inline (content is directly editable). Committing on
blur saves the trimmed text — **but if the result is empty, the previous text is kept** (a top‑level
todo can never be blanked to nothing). Pressing **Enter** commits and ends editing (no newline
inserted). Pressing **Tab** (without Shift) while editing the text commits the edit **and creates a
new empty sub‑task under that item, focused for typing** (caret at end).

**Completing.** Clicking the checkbox toggles `done`. Done items dim and strike through; the badge
flips to `✓ feito`; counts update.

**Deleting.** The × removes the item immediately (no confirm).

**Reordering.** ↑/↓ swap the item with its neighbor. The ↑ control is disabled for the first item
and ↓ for the last.

**Sub‑tasks.** "+ sub‑tarefa" (or Tab on the parent text) appends a new empty sub and focuses it.
Subs support toggle / inline edit / delete / reorder exactly like todos but scaled down. **A sub
edited to empty and then blurred is automatically removed** (keeps the list clean). Subs never wrap
mid‑word; long text breaks across lines.

**Counts.** `total` = number of todos **plus** all subs; `done` = todos and subs marked done;
`pending` = total − done. Recomputed on every render.

**Live ticking.** Two independent 1‑second tickers:
- The **clock** updates time (and date) every second.
- The **"ago" timestamps** update every second **without re‑rendering the list**, so an in‑progress
  inline edit never loses focus or caret position. (Implication: the relative‑time refresh must read
  each element's stored `created` value and update text in place, not rebuild the DOM.)

**Focus management.** After adding a sub (button or Tab), the new sub's text field receives focus
with the caret placed at the end.

---

## 9. Edge cases (must handle)

- Corrupt/absent/non‑array `localStorage` → start empty; never throw on load (§3 migration).
- Old saved items without `subs` / subs without `id|done|created` → upgraded on load and persisted.
- Empty or whitespace‑only **new todo** → ignored.
- **Todo** edited to empty → keeps prior text (not deleted).
- **Sub** edited to empty → deleted on blur.
- Reorder at list boundaries → controls disabled; no wrap‑around.
- Very long text (todo or sub) → wraps/breaks rather than overflowing.
- Relative‑time refresh must not steal focus from an active edit.
- App must work from `file://` with no network (fonts degrade to fallbacks; grain & logo are inline).
- Nesting is **one level only** — subs do not themselves have subs.

---

## 10. Verification journeys (how the agent proves it built it right)

Run these after hydration; **all must pass**. (Manual or automated, e.g. via a headless browser.)
Each step states the action and the expected, observable result.

1. **Boot / empty state.** Clear `localStorage`, open the file. *Expect:* header with logo,
   "Live to‑dos", pulsing "On air" pill, a live clock that advances each second; counts read
   `0 done / 0 pending / 0 total`; the list shows `Nada ainda. Adiciona o primeiro to-do acima.`
2. **Add via Enter.** Type "First task", press Enter. *Expect:* a new card at the top; input
   cleared; counts `0 done / 1 pending / 1 total`; badge `⏳ pendente`; an "ago" line like
   `há 0s adicionado`.
3. **Add via button + ordering.** Type "Second task", click "Add". *Expect:* "Second task" appears
   **above** "First task" (newest on top); `2 total`.
4. **Whitespace ignored.** Type only spaces, press Enter. *Expect:* no new item; counts unchanged.
5. **Persistence.** Reload the page. *Expect:* both tasks still present, in the same order, with the
   same done/pending state. (Confirms `localStorage` round‑trip under key `plow.stream.todos.v1`.)
6. **Complete & counts.** Click the checkbox on one task. *Expect:* it dims + strikes through, badge
   → `✓ feito`; counts move (e.g. `1 done / 1 pending / 2 total`). Reload → state persists.
7. **Inline edit + non‑blank guard.** Edit a task's text to "Edited task", press Enter. *Expect:*
   text saved; reload persists it. Now clear the same task's text entirely and blur. *Expect:* the
   **previous text is retained** (todo not blanked/deleted).
8. **Reorder.** With ≥2 todos, click ↓ on the top one. *Expect:* it swaps down one position; the
   top item's ↑ is disabled, the bottom item's ↓ is disabled. Reload → new order persists.
9. **Add sub via button.** Click "+ sub‑tarefa" on a todo, type "Sub A", blur. *Expect:* an indented
   sub appears **below** the parent's text with its own badge/ago; `total` increased by 1 and counts
   include the sub.
10. **Add sub via Tab.** Focus a todo's text, press Tab. *Expect:* a new empty focused sub appears
    (placeholder `sub-tarefa…`), caret ready. Type "Sub B", blur → it persists.
11. **Sub auto‑drop.** Add a sub, leave it empty, blur. *Expect:* the empty sub is removed; counts
    return to prior value.
12. **Sub toggle/reorder/delete.** Mark a sub done → `✓ feito`, counts update. With ≥2 subs, reorder
    with ↑/↓. Delete a sub with ×. Reload → results persist. Confirm subs **cannot** be nested
    inside subs.
13. **Delete todo cascades.** Delete a todo that has subs. *Expect:* the todo and all its subs
    disappear; counts drop by (1 + number of subs).
14. **Live tickers.** Watch ~3s: the clock seconds advance and "ago" labels increment **while you
    are mid‑edit** in a todo — confirm the edit caret/focus is **not** lost when "ago" refreshes.
15. **Date/locale strings.** Confirm the date reads like `Domingo, 31 Mai 2026` (Portuguese
    weekday + month abbrev) and time is `HH:MM:SS`.
16. **Offline / file://.** Open via `file://` with the network disabled. *Expect:* fully functional;
    grain texture and logo still render (inline); fonts fall back gracefully.
17. **Migration.** Manually set `localStorage["plow.stream.todos.v1"]` to an array of items that
    **lack** a `subs` field, then load. *Expect:* no errors; each item gains an empty `subs`, and
    the upgraded shape is written back to storage.

---

## 11. Convergence notes (read before building)

These are the details most likely to drift between two independent rebuilds — lock them in:
- **Storage key** is exactly `plow.stream.todos.v1`.
- **New todos prepend (top); new subs append (bottom).**
- **Counts include subs.**
- **Todos can't be blanked; empty subs are auto‑deleted.**
- **Tab in a todo's text creates a sub** (this is easy to miss).
- **"ago" refresh must not re‑render** (focus preservation).
- The **English‑chrome / Portuguese‑microcopy mix** is intentional (title, headline, placeholder,
  "Add", and the count words are English; badges, "ago", empty state, date, and aria‑labels are
  Portuguese). Keep it.
- **Single file, no server, no deps; localStorage‑only; inline grain + logo.**
- Visual identity = dark background, **volt (#D5EF8A)** accent, **Instrument Serif** headlines,
  film‑grain overlay.

---

## 12. Installation / handoff

To (re)build or "install" the app, hand this seed file (e.g. `./seed.md`) to a coding agent with an instruction like *"Hydrate this seed: build the
app it specifies, in one static HTML file, until every verification journey in §10 passes."* The
agent should output `todos.html` (single file) and then self‑run §10 before declaring done.
