# SEED: almanac

> A self-contained product-spec "seed" for **Almanac** — a Next.js 14 design-review app (Google/@plow.co auth, anchored comment pins on iframed artifacts, presence, agent-reviewer API).
> **To build:** hand this file to a coding agent — it builds the app and self-runs the §16 acceptance journeys.
> **Hardened (v2):** a blind, zero-context agent reproduced it **one-shot — 27/27 §16 journeys PASS** (22 functional + 5
> visual-fidelity), real headless-browser Playwright, with the §9 design system reproduced from the spec (computed-style + screenshot gates).

> seed-format: 1

> **You're an AI agent reading this seed.** Your job: build the **Almanac** web app — a
> Figma-style design-review surface for Plow's "seed" HTML explorations — from this
> specification alone, until every acceptance journey in **§16** passes. This file is the
> product; the running Next.js app is just the proof. It contains **NO implementation
> code** on purpose: you have reasoning, you pick the file layout and the React/route
> wiring. What this seed pins down — the data model (§4), the KV key schema (§5), the route
> map (§6), the API contracts (§7), the exact constants, regexes, limits, colors, fonts and
> emoji (§9, §13) — is **fixed**. Treat those as load-bearing; everything else you may build
> the idiomatic way.
>
> **Definition of done.** A signed-in `@plow.co` reviewer can open a project, drill into an
> option and a version, see the rendered HTML artifact in an iframe, drop pin-comments on
> it, reply, react, resolve, see who else is viewing live, and an AI agent can read the same
> surface and write comments back through a header-gated API — all behaviors in §16
> observable and green. Run `## Verify` (§15-adjacent) and the §16 journeys; the seed is
> proven only when they pass.

---

## 1. Purpose & context

**Almanac** (codebase package name `seeds-feedback`; product/brand name shown to users:
**"Plow • Almanac"**) is Plow's **internal design-review room**. Plow's product process
generates lots of self-contained HTML "seed" explorations (landing pages, catalog layouts,
feature mocks — each a single `.html` file). Almanac is where the team **critiques** them:
it renders each artifact in an iframe and lets reviewers leave **pin-anchored comments**
directly on the design, exactly like commenting in Figma, plus threaded replies, emoji
reactions, resolve/unresolve, live presence ("who's looking right now"), and a side
activity panel.

It is **internal and gated**: only `@plow.co` Google accounts get in (`robots: noindex`).
A second, **header-gated API** lets **AI review agents** (not humans) read an artifact and
its thread and write comments back programmatically — so an automated design critic can
participate in the same review surface as the humans.

The product evolved through a **data-model refactor** from a 2-level shape
(Project → Version) to a **3-level shape (Project → Option → Version)**. The seed targets
the **3-level model** as canonical, but the read paths must keep **legacy 2-level fallbacks**
alive (see §4, §5, §10) because a deploy can run ahead of the migration script.

Character traits the rebuild must preserve:
- **Figma-style commenting** over an iframe'd static artifact — pins live *inside* the seed
  document, numbered, avatar-glyphed, clustered when they overlap.
- **Optimistic everywhere** — every mutation updates the UI immediately and rolls back on
  failure.
- **Plow brand** — chalk background, volt-lime accent, Instrument-Serif headings, film-grain
  overlay (see §9).
- **Two front doors** — a human (Google-auth, session-cookie) surface and an agent
  (two-header) surface, writing into the **same** comment store.

---

## 2. Technical approach (stack, prerequisites, constraints)

- **Framework**: **Next.js 14 App Router** (React 18, TypeScript, `strict`). Server
  Components for pages; `"use client"` for interactive components. Route handlers under
  `src/app/api/**`. Path alias `@/* → src/*`.
- **Runtime**: dev + prod server on **port 3210** (`next dev -p 3210` / `next start -p 3210`).
- **Auth**: **NextAuth v4** with the **Google** provider, JWT session strategy. Edge
  **middleware** is the first gate.
- **Persistence**: **Vercel KV** (`@vercel/kv`, a Redis-compatible store) for ALL mutable
  state (comments, replies, reactions, viewers, resolves, project/option/version metadata,
  display-name overrides, status, anchor caches). **Dev fallback**: when KV env vars are
  absent, fall back to an **in-memory `Map`** implementing the same `get/set/del/llen/rpush/
  lrange/lrem/hincrby/hgetall/hset/sismember/sadd/srem` surface, so `next dev` works with no
  KV provisioned (warn once on stderr; never use the memory store in production).
- **Seed corpus on disk**: HTML artifacts live under `cookoff-seeds/<projectDir>/<file>.html`
  at the **repo root** (`SEEDS_ROOT = <cwd>/cookoff-seeds`). These are **auto-discovered**
  (§4). The repo ships a corpus; the seed treats `cookoff-seeds/` as an input.
- **HTML parsing** (agent surface only): **cheerio** for server-side selector/text anchor
  resolution and candidate-anchor extraction. No headless browser in the function bundle
  (Vercel Functions ship no browser binary) — bounding boxes are therefore `null`.
- **No other heavyweight deps**: no CSS framework, no emoji-picker library (a curated
  in-house set, §9), no state library beyond React.
- **Deploy target**: Vercel. `vercel.json` sets security headers (`X-Frame-Options: DENY`,
  `Content-Security-Policy: frame-ancestors 'none'`, HSTS) on **all paths EXCEPT** `/seed/`
  and `/seed-kv/` — those two must remain frameable because the VersionViewer iframes them
  same-origin.
- **E2E**: Playwright (`npm run e2e`).

---

## 3. The two front doors (mental model)

1. **Human surface** — browser, NextAuth Google session cookie. Reaches every page + every
   `/api/*` route except the agent ones. Identity = the signed-in `@plow.co` email.
2. **Agent surface** — server-to-server, **two request headers** (no cookie). Reaches exactly
   three endpoints (`GET /api/agent-artifact/*`, `POST /api/agent-comments`,
   `DELETE|PATCH /api/agent-comments/[id]`). Writes into the **same** comment KV shape humans
   use, tagged with `agentAuthored: true`.

Both doors mutate one store; a comment placed by an agent renders through the same pin path
as a human comment (with the agent's chosen display name + avatar).

---

## 4. Data model (entities & relations — the 3-level model)

```
Project ──< Option ──< Version ──< Comment ──< Reply
                                      │
                                      ├─ Reactions (per comment & per reply)
                                      └─ Resolved flag
Version ──< Viewer (presence)
```

- **Project** — a design problem. `{ id (slug), name, status, options[], source?, description? }`.
  - `status` ∈ **`active` | `archived` | `shipped`** (the three `STATUSES`).
  - `source`: `"fs"` (auto-discovered from disk) or `"kv"` (manually created via UI).
- **Option** — one distinct *direction/exploration* under a Project.
  `{ id (slug), name, source, description?, versions[] }`. Each Option carries its own
  iteration history.
- **Version** — one artifact **revision** under an Option.
  `{ id (slug, e.g. "v1"), author, roundDir, slug, source: "fs"|"kv", fsSlug? }`.
  - `fs` version → HTML lives on disk, served via `/seed/<roundDir>/<slug>`.
  - `kv` version → HTML lives in KV, served via `/seed-kv/<project>/<option>/<version>`.
  - A `kv` version may be **stacked on top of** an `fs` option (an fs-discovered v1 with a
    manually-uploaded v2/v3).
- **Comment** — a pin. `{ id, projectId, optionId, versionId, x, y, author, authorEmail?,
  body, ts, deleted?, deletedAt?, editedAt?, anchorSelector?, anchorText?, movedBy?,
  movedAt?, agentAuthored?, authorAvatar? }`. `x`/`y` are coordinates **in iframe-document
  pixels**.
- **Reply** — `{ id, parentCommentId, author, authorEmail?, body, ts }`.
- **Reactions** — a `Record<emoji, count>` per comment and per reply; plus a per-(target,
  emoji) **set of userIds** so a user toggles their own reaction.
- **Resolved** — per-comment flag with `{ by, at }` meta, mirrored into a per-version
  resolved **set**.
- **Viewer** — presence record `{ email, name, image, lastTs }`, one per person per version
  (a hash keyed by email; revisits refresh name/image/lastTs).

### Auto-discovery rule (fs projects)

Walk `cookoff-seeds/`. Each subdirectory (minus a hidden-dirs skip-list and dotfiles) is a
**Project** (`id = dir name`). Each `*.html` file inside becomes an **Option**
(`id = filename without ".html"`), and that option owns a single **Version** `id = "v1"`,
`source: "fs"`, with the on-disk file as its artifact. (So one HTML file ⇒ one option ⇒ one
v1.) Manual uploads later can append `kv` versions (v2, v3…) onto these options.

- Project display name: a hardcoded override map for a few slugs (`seed` → "Individual seed
  page", `catalog` → "Seed catalog", plus the archived `seed-page`/`seed-catalog` pair),
  else derive by `split("-")` + title-case (words ≤2 chars stay lowercased).
- Version label: `"v" + N` → `"Version N"`; any other slug renders raw.
- Option label default: numeric `vN` slugs render as `"Option N"`; else the stored
  name/slug.
- Hidden dirs (skipped by discovery, kept on disk for provenance): `round-2`, `round-2-deps`,
  `round-3-synthesis`, `round-4-install-order`, `round-5-design-review`, `round-6-catalog`,
  `round-7-catalog-aligned`, `deps-cookoff`, `copy-1`, `eng-1`, `eng-2`.
- Index ordering: `seed-page` first, then `seed-catalog`, then the rest alphabetically.

### Manual (kv) projects

Created via the UI (§7 POST /api/projects). Stored in KV under both a **canonical 3-level
shape** and a **legacy mirror** (so `loadManualProjects` still discovers them if the new read
path falters). On collision, fs-discovered slugs win.

### Migration & legacy fallback (must implement the fallbacks)

The pre-refactor 2-level data keyed comments/viewers/resolves by `(projectId, versionId)`
where that `versionId` is *now* the **optionId**, with the migrated version being **`v1`**.
Every read path that takes `(projectId, optionId, versionId)` must, when the canonical
3-level key is empty **and** `versionId === "v1"`, **fall back** to the legacy 2-level key
`(projectId, optionId)`. A legacy Comment row lacking `optionId` is back-filled on read:
`optionId ← versionId`, `versionId ← "v1"`. A re-runnable migration script (idempotent,
tags done rows in a `migration:v1:done` set) copies legacy keys forward and patches embedded
triplets; it does **not** delete legacy keys.

---

## 5. KV key schema (fixed — these exact key shapes)

> `<p>` = projectId, `<o>` = optionId, `<v>` = versionId, `<id>` = comment/reply id,
> `<e>` = emoji. IDs are `crypto.randomBytes(8).toString("hex")` → **16 hex chars**.

**Comments / replies / reactions / resolve**
- `comment:<id>` → Comment JSON
- `version:<p>:<o>:<v>:comments` → list of comment ids (RPUSH order = pin order)
- `version:<p>:<v>:comments` → **legacy** 2-level list (read-fallback for v1)
- `comment:<id>:replies` → list of reply ids
- `reply:<id>` → Reply JSON
- `comment:<id>:reactions` / `reply:<id>:reactions` → hash `{ emoji: count }`
- `comment:<id>:reactions:<e>:users` / `reply:<id>:reactions:<e>:users` → set of userIds
- `comment:<id>:resolved` → `{ by, at }` | null
- `version:<p>:<o>:<v>:resolved` → set of resolved comment ids (+ legacy `version:<p>:<v>:resolved`)

**Presence / display names / status / per-user**
- `version:<p>:<o>:<v>:viewers` → hash `{ email: ViewerJSON }` (+ legacy `version:<p>:<v>:viewers`)
- `project:<p>:displayName`, `project:<p>:option:<o>:displayName`,
  `version:<p>:<o>:<v>:displayName` (+ legacy `version:<p>:<v>:displayName`)
- `project:<p>:status` → status override string
- `user:<userId>` → display-name (legacy; userId now = lowercased email)

**Manual project (legacy mirror shape)**
- `manual:projects` (list of slugs), `manual:project:<slug>:meta`,
  `manual:project:<slug>:versions`, `manual:project:<slug>:version:<vid>:meta`,
  `manual:project:<slug>:version:<vid>:html`

**Canonical 3-level project shape**
- `project:<slug>:meta`, `project:<slug>:options` (list)
- `project:<slug>:option:<oslug>:meta`, `project:<slug>:option:<oslug>:versions` (list)
- `project:<slug>:option:<oslug>:version:<vslug>:meta`
- `project:<slug>:option:<oslug>:version:<vslug>:html`

**Agent anchor cache**
- `candidate_anchors:<sha256(html) first-32-hex>` → cached candidate-anchor array

**Active-viewer window**: `ACTIVE_VIEWER_WINDOW_MS = 60_000`. A viewer is "live" if
`lastTs >= now - 60s`. The cumulative list still powers the activity feed + viewed-by panel.

---

## 6. Auth & access control (fixed rules)

- **Provider**: Google OAuth. Restrict to the `plow.co` Workspace: set `authorization.params
  .hd = "plow.co"` and `prompt = "select_account"`; the Google OAuth client should be
  configured **Internal**. A `signIn` callback is **defense-in-depth**: reject any email not
  ending in `@plow.co` (lowercased). Session strategy = **JWT**; carry `email/name/picture`
  through the `jwt` + `session` callbacks. Sign-in + error pages both route to `/login`.
- **Identity** (`readIdentity`): from the server session; `userId = lowercased email`,
  plus `name`, `email`, `image`. No session ⇒ null.
- **Edge middleware** gates everything. Verifies the NextAuth JWT (`getToken`) and that the
  email ends in `@plow.co`. Behavior:
  - Skip `/_next`, `/favicon*`, `/robots.txt`.
  - **Public paths** (no session needed): `/api/auth/*`, `/api/agent-comments(/…)`,
    `/api/agent-artifact(/…)`, `/login`. (The two agent paths are public to NextAuth because
    they carry their own header auth.)
  - Not signed in + non-public path ⇒ **redirect to `/login?next=<path+search>`**.
  - Signed in + hitting `/login` ⇒ redirect to `/`.
  - Matcher: everything except `_next` / `favicon.ico` / `robots.txt`.
- **Agent two-header gate** (the three agent endpoints): require **both**
  - `x-vercel-protection-bypass` == `VERCEL_AUTOMATION_BYPASS_SECRET` (layer 1; missing/wrong
    ⇒ **401**), and
  - `x-almanac-agent-key` == `ALMANAC_AGENT_API_KEY` (layer 2; missing/wrong ⇒ **403** on
    POST/DELETE, 401 on the artifact GET).
  Compare with a **constant-time** equal (timing-safe; length-mismatch short-circuits).
- **Per-action authorization**:
  - **Edit comment / delete comment / delete reply**: **author-only** — `authorEmail` must
    case-insensitively match the caller. Non-author ⇒ **403**.
  - **Reposition pin** and **resolve/unresolve**: **open to any signed-in `@plow.co` user**
    (CEO directive — the crit team fixes misplaced pins and resolves regardless of author).
    Repositioning records `movedBy`/`movedAt` (audit, not surfaced yet); tombstoned
    (`deleted`) comments still refuse reposition.

---

## 7. Routes, pages & API surface

### Pages (App Router, all `dynamic = "force-dynamic"`, all gated except /login)

| Path | What it is |
|---|---|
| `/` | **Index**: project list filtered by status. |
| `/login` | Google sign-in card (public). |
| `/welcome` | Obsolete; 307→`/`. |
| `/p/[projectId]` | **Project page**: option grid + status + rename + add-option (manual only). |
| `/p/[projectId]/[optionId]` | Thin resolver → **redirect to the latest version** of the option. |
| `/p/[projectId]/[optionId]/v/[versionId]` | **VersionViewer** (the core review surface, §8). |
| `/p/[projectId]/v/[versionId]` | **Legacy** 2-level URL → **permanent (308) redirect** to `/p/<p>/<v>/v/v1` (old version slug becomes the option slug). 404 if the option doesn't exist post-discovery. |

### Artifact-serving routes (session-gated, `dynamic = "force-dynamic"`)

| Path | Serves |
|---|---|
| `GET /seed/[round]/[slug]` | fs artifact HTML. Validates `(round, slug)` against the auto-discovered seed-path list; 404 if unknown; 401 if not signed in. `Cache-Control: private, max-age=0, must-revalidate`. |
| `GET /seed-kv/[projectId]/[optionId]/[versionId]` | kv artifact HTML from `…:version:<v>:html`. 401 if not signed in, 404 if no HTML. **All** responses (incl. failures) sent `Cache-Control: no-store`. |

### Human API (session-gated, `runtime = "nodejs"`)

| Method + path | Contract |
|---|---|
| `POST /api/projects` | **multipart** create manual project + first option + first v1. Fields: `name`, `slug`, `description?`, `optionName`, `optionSlug?`(=`option-1`), `versionSlug?`(=`v1`), `file`(.html). Validates (see §10). 409 on slug collision. Returns `{ project, redirect: /p/<slug>/<optionSlug>/v/<versionSlug> }`. |
| `PATCH /api/projects/[projectId]` | rename project (display-name override). Body `{ name }`. Slug unchanged. |
| `POST /api/projects/[projectId]/status` | set status. Body `{ status }` ∈ active/archived/shipped. |
| `POST /api/projects/[projectId]/options` | **multipart** add option (+ its v1) to a **manual** project only (fs projects 404 here). Fields `name`, `slug`, `versionSlug?`(=`v1`), `file`. Returns `{ option, redirect }`. |
| `PATCH /api/projects/[projectId]/options/[optionId]` | rename option. Body `{ name }`. |
| `POST /api/projects/[projectId]/options/[optionId]/versions` | **multipart** append version. Works on **both** manual & fs options. `file` required; optional `versionSlug` else **auto-increment** to `v<maxN+1>`. Returns `{ versionId, redirect }`. |
| `PATCH /api/projects/[projectId]/options/[optionId]/versions/[versionId]` | rename version. Body `{ name }`. |
| `POST /api/comments` | create pin. Body `{ projectId, optionId, versionId, x, y, body }`. Validates triplet exists, coords in range, body non-empty. Author = session name/email. Returns `{ comment: <thread-shaped> }`. |
| `PATCH /api/comments/[commentId]` | edit body (**author-only**). 404/403/400. Sets `editedAt`, keeps `ts`. |
| `DELETE /api/comments/[commentId]` | delete (**author-only**). **Soft** (tombstone) if the comment has replies; **hard** purge otherwise (see §10). |
| `PATCH /api/comments/[commentId]/position` | reposition (**any signed-in user**). Body `{ x, y, anchorSelector? }`. Tombstones ⇒ 400. |
| `POST /api/comments/[commentId]/resolve` | toggle resolved (**any signed-in user**). Body `{ resolved: boolean }`. Returns `{ resolved, resolvedBy, resolvedAt }`. |
| `POST /api/replies` | create reply. Body `{ commentId, body }`. |
| `DELETE /api/replies/[replyId]` | delete reply (**author-only**). |
| `POST /api/reactions` | toggle reaction. Body `{ target: "comment"|"reply", id, emoji }`. Returns `{ reactions, userReactions }`. |
| `POST /api/heartbeat` | presence beat. Body `{ projectId, optionId, versionId }`. Records the view, returns `{ active: Viewer[] }` (the live <60s roster). |
| `GET/POST /api/auth/[...nextauth]` | NextAuth handler. |

### Agent API (two-header gate, `runtime = "nodejs"`) — see §11.

`commentId`/`replyId` path-param validation regex: **`/^[a-f0-9]{16}$/`**. Slug validation
regex: **`/^[a-z0-9][a-z0-9-]*$/`**, max 64. HTML upload cap: **3,670,016 bytes (3.5 MB)**;
`.html` only; over cap ⇒ **413**.

---

## 8. UI / UX spec

### 8.1 Global chrome

- **Top bar** (index + project pages): sticky, chalk, bottom rule. Left: brand
  "`plow` · `almanac`" (serif italic wordmark + small volt dot). Right: signed-in name + a
  **"sign out"** button (`signOut → /login`).
- **Footer**: `plow` wordmark · "internal · seeds · 2026".
- Document title template: `Plow • Almanac · %s`; default `Plow • Almanac`. `robots: noindex,
  nofollow`.

### 8.2 Index `/`

- Hero `projects`. A **status-filter pill nav** (`active` | `archived` | `shipped`), default
  `active`; non-active statuses link to `/?status=<s>`. A **"+ new project"** button opening
  the New Project modal.
- Project rows (filtered by **live** status resolved from KV): inline-renamable name (pencil
  trigger), `<N> options · <M> pins`, "open →", and "updated <relative-time>" (latest version
  mtime across all option/version leaves; "no source on disk" when 0). Empty filter ⇒
  "no projects in this status. switch the filter."

### 8.3 Project page `/p/[projectId]`

- Breadcrumb "← all projects". **Click-to-rename `h1`** project title. A **StatusEditor**
  (`active`/`archived`/`shipped` select, optimistic). Lede "`N` options".
- **Manual projects only**: an **"+ add option"** button (AddOption modal).
- **Option grid**: each card = pencil-renamable option name, "open →",
  `<N> versions · <M> pins · <K> reactions` (reactions hidden when 0), "updated <rel>", and a
  compact **ViewerStack** of recent viewers (from the most-recent version). Card links to
  `/p/<p>/<option>` (which redirects to the latest version).

### 8.4 The VersionViewer `/p/[projectId]/[optionId]/v/[versionId]` (the heart)

On load the server records the viewer, then fetches: current-version thread, **cross-version
option thread** (every version's comments, each row tagged with its `versionId`), viewers,
active viewers, an **author-lookup map** (email→{name,image} merged across all versions'
viewers — so a commenter's Google avatar shows on any version), per-(viewer,version) viewer
events, display names, and the version-switcher entries.

**Sticky version-bar header**, left→right:
- Breadcrumb: **`←`** back to project · **project name** (link) · `/` · **option name**
  (link) · `/` · **version name** (click-to-rename `InlineNameEditor`) + a **VersionSwitcher**
  chevron.
- A hint: "**hold ⌥ to comment**".
- A **ViewerStack** (live active viewers, compact).
- A **"+ Comment"** toggle button (enters/exits placement mode; label cycles
  `Comment` → `Drop pin · Esc`).
- An **"Activity"** panel toggle showing a count (`comments + viewers`).

**The artifact iframe**: `src` = the seed/seed-kv URL, `sandbox="allow-same-origin
allow-scripts"`, **fluid** (width/height 100%) so the seed's own media queries fire against
its real rendered viewport (no CSS transform / no fixed 1280px inner width).

**Pin layer** (injected into the iframe document, plain DOM — not React):
- A `<style id="feedback-pin-style">` injected on each real iframe `load` (ignore the
  transient `about:blank`; bump a load counter so dependent effects re-bind to the live doc).
- Each non-resolved comment → a **24px circular pin**, volt (`#d5ef8a`) fill, midnight
  (`#01000a`) 1.5px border, DM-Mono, centered on `(x,y)` via `translate(-50%,-50%)`,
  `z-index` very high. The glyph is the author's **Google avatar image** (round, cover) or
  **deterministic-color initials** fallback. `data-pin-number` = chronological index (1..N).
- **Resolved** comments **hide their pin** from the canvas (the row stays in the panel under
  the "resolved" filter); unresolve re-renders it.
- **Hover** opens the pin popover (with a ~350ms close grace); **click** opens it (a real
  drag suppresses the click).
- **Drag to reposition** (any signed-in user): `data-draggable="1"`, `cursor:grab`; drag
  threshold **4px** distinguishes drag from click; on drop, make the pin transparent to
  `elementsFromPoint`, find the seed element under the drop, build a durable CSS
  **anchor selector** (`#id` shortcut else `tag:nth-of-type(n)` path up to body, ≤12 deep),
  optimistically move + PATCH `/position`; rollback snaps the pin home on failure.
- **Clustering**: pins whose centers fall within **24px** of each other collapse into one
  **cluster glyph** (30px midnight square, top author's avatar + a `+N` count badge). Clicking
  a cluster opens a floating **pop-list** (rendered in the parent document) of its member
  pins; picking one opens that pin's popover.

**Placement modes**:
- **"+ Comment" toggle** = **sticky** placement (drop many pins; stays armed after each
  post/cancel). **Option/Alt + click** = **single-shot** placement. Cursor becomes a
  crosshair in placement mode. **Esc** exits.
- Clicking the artifact in placement (or Alt+click anytime) opens a **Composer** popover at
  the click point: shows the author + "placing pin", a "Leave a note" textarea (Enter posts,
  Shift+Enter newline, max 2000), `cancel` / `post pin`. Posting is optimistic.
- The bare **`c` key shortcut was intentionally removed** (too easy to trigger while reading);
  the only entry points are the toggle and Alt+click.

**Pin popover** (Figma-style): avatar + display name + relative ts (+ "· edited" flag);
an action row (only when not deleted): **add-reaction** (☺+ opens the EmojiPicker), **✓
resolve** toggle (`aria-pressed`), and a **⋯ CommentMenu** (Edit / Delete — author-only).
Body is **linkified** plain text (URLs → real `<a target=_blank rel=noopener>`; never raw
HTML). Below: reaction chips (toggle, `data-mine`), a "✓ resolved" tag when resolved, the
**replies thread** (each reply: author · ts, body, reactions; author sees a `⌫` delete), and
a **reply composer** (Enter sends). Tombstoned comment body renders
`[comment deleted by author]`.

**Delete UX**: deleting a comment or reply removes it optimistically and shows a bottom
**Undo toast** for **5000 ms** ("Comment deleted" / "Reply deleted" + "Undo"). The DELETE
fires only after the window elapses (undo cancels it). Failure restores the row + surfaces an
error.

### 8.5 Activity panel (right drawer, Figma-style)

- Toggled by the header "Activity" button **or the `a` key** (when not typing); open-state
  **persisted in `localStorage` key `almanac.panel.open`** (`"1"`/`"0"`).
- Header: "Comments `<matched>` of `<total>`", a **search** (author/body, with clear), a
  **state filter** (`all` | `open` | `resolved`), a **sort** (`recent` | `reactions`), and —
  when the option has >1 version — a **version-chip multi-select** (empty = all; `clear`).
- Feed = the **cross-version option thread interleaved with viewer events** (viewer rows show
  only under the `all` filter), sorted by ts (or by reaction-total for comments under
  `reactions` sort). Each comment row: avatar, **`#<pinNumber>`** (chronological within its
  version) + a **version chip** (highlighted when current), action row (react / resolve /
  edit-delete), author · ts (+ edited), body, reaction chips, resolved tag, and an action
  link — **"jump to pin"** when the row is on the current version (scrolls the iframe so the
  pin sits ~⅓ down + a 900ms flash-pulse), else **"open <versionId>"** linking to that
  version. Replies are collapsible (`N replies ▾`). Viewer rows read "`<name>` viewed
  `<versionId>` · <rel>".
- Empty: "No activity matches the active filter." + the ⌥-click hint.

### 8.6 VersionSwitcher

A compact chevron dropdown in the version bar listing **all versions of the current option**,
newest-first, the current one marked (`✓`, "current", non-clickable), the newest tagged
"latest". Each row shows label + slug + uploader · relative time, and a **download `↓`**
button that fetches the version HTML and triggers a browser download named
`<project>-<option>-<version>.html`. A **"+ Add version"** action at the bottom opens the
AddVersion modal (auto-increments `v<N+1>`, uploads, redirects). With a single version and no
add action, the compact switcher renders nothing.

### 8.7 Modals (New Project / Add Option / Add Version)

Backdrop + card, Esc/backdrop-click to close (unless busy), focus first field on open.
- **New Project**: project name → auto-kebab slug (editable, shows `/p/<slug>`), optional
  description, a **first option** fieldset (option name → auto-kebab option slug), and an
  **html file** ("becomes v1"). Submits multipart; on success `router.push(redirect)`.
- **Add Option** (manual projects): option name → auto-kebab slug (skips if taken),
  html file. Default slug auto-numbered `option-<n>`.
- **Add Version**: just an html file; header shows the preview slug `v<N+1>`; uploads under
  the current option and redirects.

### 8.8 Inline rename (InlineNameEditor) & StatusEditor

- **InlineNameEditor**: `click` or `pencil` trigger. Edit → PATCH the given endpoint with
  `{ name }` → on success `router.refresh()` (so sibling server-rendered surfaces repaint).
  Enter commits; Esc rolls back; empty/unchanged is a silent no-op. **Slug never changes** —
  only a display-name override is stored.
- **StatusEditor**: a `<select>` (active/archived/shipped); optimistic POST with rollback.

---

## 9. Design system (reproducible spec — get the *feel* right, not just the tokens)

> **Why this section is long.** A correct rebuild is not just the right colors — it's the
> right **fonts + weights**, the **micro-interactions** (every interactive element lifts,
> tints, or reveals on hover), the **transition feel** (one shared easing, a small set of
> durations), and a consistent **shadow/spacing/radius rhythm**. The real app is a light,
> editorial, Plow-branded surface where *everything moves a little* on hover and nothing
> moves a lot. Reproduce the **values and rules** below; you do not need the original CSS.

### 9.1 Palette (exact)

- **Brand**: `--midnight #01000a` · `--volt #d5ef8a` (lime accent) · `--grove #5e7a5e` ·
  `--grove-light #e8ede8` · `--grove-deep #4a6149` · `--iris #c4bfff`.
- **Surfaces**: `--chalk #fafaf7` (page bg) · `--oat #f3f3ee` (hover/secondary fill) ·
  `--card-bg #ffffff` · `--card-border #e5e5e0` · `--card-border-deep #d7d7cf` ·
  `--rule #eceae2` (hairline dividers).
- **Text**: `--text #212121` · `--text-emphasis #181818` · `--text-muted #6b6b6b` ·
  `--text-light #8e8e8e`. **Semantic**: `--danger #ff3b30`.
- **Derived hover shades (exact)**: midnight button hover `#15131f`; volt button hover
  `#c4e07b`; volt-tint hover wash `rgba(213,239,138,0.32)`; volt focus-ring
  `rgba(213,239,138,0.40–0.45)`.
- The app is a **light theme**. `::selection` = volt bg / midnight text.

### 9.2 Typography (the fonts are part of the brand — pin them)

Three families, **loaded from Google Fonts via a `<link>`** in `<head>` (with
`preconnect` to `fonts.googleapis.com` + `fonts.gstatic.com`). Load **these exact weight
axes** — the wrong weights are the single biggest cause of "the fonts look off":

```
family=DM+Mono:wght@400;500;600
&family=DM+Sans:wght@400;500;600;700
&family=Instrument+Serif:ital@0;1   ← both upright AND italic
&display=swap
```

- **`--serif`** = `'Instrument Serif', Georgia, serif` — **used italic** for all display
  headings + wordmarks (brand, hero `h1`, page titles, footer wordmark). Headings are
  weight **400** (the face is light by design — do **not** bold it).
- **`--sans`** = `'DM Sans', system-ui, -apple-system, sans-serif` — body, buttons,
  comment text, breadcrumbs. Base body = **15px / line-height 1.55**, weight 400; emphasis
  weight 500; strongest 600–700.
- **`--mono`** = `'DM Mono', 'SF Mono', Consolas, monospace` — all meta/labels/counts:
  pins, version-bar hint, breadcrumb separators, status pills, eyebrows, `.kbd`, footer,
  viewer counts. Mono labels are typically **uppercase** with **letter-spacing 0.04–0.12em**.
- Degrade gracefully to the system fallbacks offline.

**Type scale (exact sizes / weights / tracking):**

| Role | Family / style | Size · weight · tracking |
|---|---|---|
| Hero `h1` (index "projects") | serif italic | **52px** · 400 · `-0.01em` · lh 1.05 (→ **36px** ≤720px) |
| Project-head `h1` | serif italic | **42px** · 400 · lh 1.05 |
| Auth wordmark | serif italic | **38px** · 400 · lh 1 |
| Brand wordmark (top bar) | serif italic | **22px** · 400 |
| Footer wordmark | serif italic | **18px** |
| Project-row / version-card name | sans | **22px** · 500 · `-0.005em` |
| Body / comment text | sans | **15px** (comments ~14px) · 400 · lh 1.55 |
| Breadcrumb | sans | **14px**; parents 400 muted, current 500 midnight |
| Meta / counts | mono | **12px** · `0.02em` |
| Eyebrow / status pill | mono uppercase | **11px** · `0.08–0.12em` |
| `.kbd`, micro, gate-micro | mono uppercase | **10px** · `0.04–0.1em` |

### 9.3 Motion — one easing, a small duration ladder (this is the missing "feel")

**Every** transition uses **`ease-out`**. Durations come from a fixed ladder — match them:

- **180ms** — the **default** for almost everything (color, background, transform, border).
  When unsure, use `…180ms ease-out`.
- **160ms / 150ms / 140ms** — tighter micro-interactions (small icon buttons, chips,
  emoji-cell, menu items, focus rings).
- **220ms** — layout-scale motion: the activity-panel slide (`padding-right`) and the
  undo-toast entrance.
- **120ms** — snappy taps.
- **1200ms ease-in-out, infinite** — the *provisional* (placing) pin pulse only.

**Keyframes (4, exact behavior):**
- `pop-in` (popovers/menus): **180ms ease-out both**, `opacity 0→1` + `translateY(-4px)→0`.
- `undo-toast-in`: **220ms ease-out**, `opacity 0→1` + `translate(-50%,8px)→(-50%,0)`.
- `pin-pulse` (provisional pin): scale `1 ↔ 1.12` at 50%, around `translate(-50%,-50%)`.
- `sheet-up`: mobile bottom-sheet entrance for the panel (slide up).

**Hover/active/disabled rules — apply consistently (this is what "felt missing"):**

| Element | hover | active / state |
|---|---|---|
| Primary button `.btn` (midnight) | `translateY(-1px)` + bg→`#15131f` | active `translateY(0)` |
| Volt button | bg→`#c4e07b` | — |
| Secondary button | bg→`--oat` | — |
| "+ Comment" toggle | bg→`--oat` + `translateY(-1px)` | active = **volt fill**, midnight border |
| "+ new project" CTA (midnight pill) | `translateY(-1px)` + bg→`#1a1923` | — |
| Breadcrumb crumb | text→midnight + **volt-tint wash** `rgba(213,239,138,0.32)` bg | current = midnight 500, no hover |
| Project-row | **`padding-left: 8px`** (whole row nudges right) | — |
| Project-row arrow ("open →") | color→midnight + **`translateX(4px)`** | — |
| Version/option card | border→midnight + **`translateY(-2px)`** + shadow deepens | — |
| Card "open →" | color→midnight + `translateX(3px)` | — |
| Inline-rename **pencil** | **revealed only on row/card hover** (hidden at rest) | — |
| Status pill / status chip | text or border → midnight | disabled select `opacity 0.55`, cursor progress |
| Small icon buttons (react ☺+, ✓ resolve, ⋯) | bg/oat tint | resolve `[data-active]` = volt/midnight |
| Text input / textarea | — | `:focus` border→midnight; some inputs add a **volt focus-ring** `0 0 0 3px rgba(213,239,138,0.45)` |
| Identity "who" / sign-out, footnotes | muted→midnight | — |

Rule of thumb to converge: **interactive = lifts (`translateY(-1px..-2px)`), tints (oat or
volt-wash), or reveals (pencil/arrow), on a 180ms ease-out.** Directional affordances
("open →", "← back") **translate** toward their direction on hover.

### 9.4 Geometry, spacing & shadows

- **Radius**: `--radius-sm 4px` (crumbs, kbd, small chips) · `--radius 8px` (inputs) ·
  `--radius-lg 12px` (cards, popovers, modals) · **`999px`** for all pills/buttons/avatars.
- **Borders**: hairlines use `--rule`; cards `--card-border`; emphasized `--card-border-deep`
  or `--midnight` (1px, except pins/volt buttons at **1.5px** midnight).
- **Spacing rhythm** (reproduce the rhythm, not pixel-pedantic): page frame max-width
  **980px** (`.wide` 1180px), `padding 0 24px`. Top bar / version bar min-height **56px / 52px**.
  Hero pad `56px 0 24px`; project-head `40px 0 8px`; project rows `22px 0` with a bottom
  `--rule`; card grids `gap 20px`, cards `padding ~22px 24px`; buttons `7–11px × 14–18px`;
  pills `7px 14px`. Activity panel = **340px** desktop drawer (iframe reflows via
  `padding-right`), bottom-sheet ≤720px.
- **Shadow ladder (exact — soft, midnight-tinted, low-spread):**
  - Pin (rest): `0 2px 6px rgba(1,0,10,0.18)`; dragging: deepen to `0 8px 18px rgba(1,0,10,0.32)`.
  - Card hover: `0 14px 30px rgba(1,0,10,0.08→0.18)`.
  - Popover / dropdown menu: `0 14px 40px -8px rgba(1,0,10,0.18), 0 2px 8px rgba(1,0,10,0.06)`.
  - Activity panel (left edge): `-14px 0 32px -16px rgba(1,0,10,0.18)`.
  - Cluster pop-list / undo toast: `0 16px 36px -10px rgba(1,0,10,0.32)`.
  - Modal card: `0 24px 60px rgba(1,0,10,0.22)`.
  - Focus ring (volt glow): `0 0 0 3px rgba(213,239,138,0.40–0.45)`.

### 9.5 Film-grain overlay (brand signature — non-negotiable)

A fixed full-viewport `body::after`: `z-index 1000`, `pointer-events:none`,
`opacity 0.025`, `mix-blend-mode:multiply`, painted from an **inline SVG `feTurbulence`
data-URI** (`baseFrequency 0.85`, `numOctaves 2`, near-black at low alpha) so **nothing is
fetched**. Subtle but present on every page.

### 9.6 Pins, clusters & avatars (canvas identity)

- **Pin**: 24px circle, **volt fill**, **1.5px midnight border**, DM-Mono 11px,
  `translate(-50%,-50%)` centering, very high z-index, rest shadow `0 2px 6px rgba(1,0,10,.18)`.
  `:hover` scale **1.12**; `[data-dragging]` scale **1.18** + deep shadow + `cursor:grabbing`;
  `.provisional` (placing) = white + **dashed** border + `pin-pulse`; `[data-resolved]` =
  grove-light bg / grove text / **0.7 opacity** (→1 on hover); `[data-flash]` = **900ms** volt
  outline flash (jump-to-pin).
- **Cluster glyph**: 30px **midnight square** with the top member's round avatar inset + a
  small **volt `+N`** count badge bottom-right.
- **Avatars** (pins, popover, panel, viewer stack): a Google profile **image** (round,
  `object-fit:cover`) when present, else **deterministic-color initials**. Color =
  `hsl(<hash(email||name)> % 360, 40%, 70%)`. Initials: one word → first 2 chars upper;
  ≥2 words → first + last initial. Sizes: pin glyph 24px; `.fig-avatar.lg` **36px** /
  `.fig-avatar.sm` **24px**; viewer-stack avatars overlap with a `+N` overflow past 5.

### 9.7 Emoji — two scopes

- **Quick reactions** (the canonical `EMOJI` set used for aggregate rollups): exactly
  **`["👍","👎","🔥","🤔","❤️"]`**.
- **EmojiPicker** (the add-reaction surface): a curated **in-house set (~80 emoji)** across
  three categories ("Smileys & People", "Hearts & Reactions", "Symbols"), substring keyword
  **search**, and a **"Frequently used"** row backed by `localStorage` key
  `almanac.emoji.freq.v1` (max 12). **No emoji-picker library** (keeps the bundle lean).
  Picking closes the picker. Emoji cells tint on hover (~140ms).

---

## 10. Business rules & edge cases (must handle)

- **Auth domain**: only `@plow.co`; Google Workspace "Internal" + a server `signIn` check;
  `?error=AccessDenied` on `/login` renders "Almanac is only for @plow.co accounts."
- **Authorship**: edit/delete comment + delete reply are **author-only** (`authorEmail`
  case-insensitive). Reposition + resolve are **open to any signed-in user**.
- **Soft vs hard delete**: deleting a comment **with replies** → **soft** (blank body,
  `deleted:true`, clear its reactions + resolved state; replies stay so the thread reads
  coherently; pin renders the tombstone). **Childless** comment → **hard** purge (remove from
  canonical + legacy lists, delete the row, replies list, resolved, reaction keys).
- **Coordinate clamps**: comment create + reposition require finite `x∈[0,4000]`,
  `y∈[0,30000]`; out of range ⇒ **400 "bad coordinates"**.
- **Body limits**: human comment/reply `clampBody` to **2000** (UI textarea `maxLength=2000`);
  agent body clamps to **4000**.
- **Slugs**: `/^[a-z0-9][a-z0-9-]*$/`, max 64; kebab-cased client-side; collisions ⇒ **409**.
- **Manual-only mutation**: adding an **option** via the UI works only on manual projects (fs
  projects 404 — those go through the external `publish-to-almanac` flow). Adding a **version**
  works on **both** (a kv version can stack on an fs option).
- **Version auto-increment**: scan existing slugs for the highest `v<N>` (across both the kv
  list and the discovered option versions) → `v<N+1>`; explicit slug must be unique (409).
- **Latest-version resolution** (`/p/<p>/<o>` redirect): descending mtime, ties broken by
  slug descending (so v3 beats v2).
- **Legacy URL**: `/p/<p>/v/<v>` → **308** to `/p/<p>/<v>/v/v1`; 404 if option missing.
- **Legacy data fallback**: every `(p,o,v)` read falls back to the 2-level `(p,o)` key when
  the canonical key is empty **and** `v === "v1"`; legacy comment rows back-fill the triplet
  on read.
- **Optimistic + rollback**: post pin, reply, edit, delete (with 5s undo), reposition,
  resolve, react, status, rename — all update locally first and **revert on a non-OK
  response**, surfacing the error text.
- **Presence**: heartbeat every **20s** while the tab is **visible** (Page Visibility API;
  pause when hidden, beat immediately on becoming visible). Live window **60s**.
- **iframe robustness**: ignore the transient `about:blank` document; re-bind pin/cluster/
  click/scroll effects when the real seed document loads (load-counter, not a boolean).
- **Reactions cleanup**: a count hitting 0 is removed from the hash so empty chips don't
  dangle; `userReactions` is per-caller.
- **Security headers**: `X-Frame-Options: DENY` + `frame-ancestors 'none'` on everything
  **except** `/seed/` and `/seed-kv/` (those must be frameable same-origin).
- **Agent comment is identical KV shape** to human comments (+ `agentAuthored:true`,
  `authorAvatar`, optional `anchorText`), so it shows in the same pin path, activity feed and
  rollups with zero read-side merge.

---

## 11. Agent API surface (the non-human reviewer contract)

All three require the **two-header gate** (§6). `runtime = "nodejs"`. Slugs validated
`/^[a-z0-9][a-z0-9-]*$/`; commentId `/^[a-f0-9]{16}$/`.

**`GET /api/agent-artifact/[project]/[option]/[version]`** — the **read** surface. Resolves
the triplet (404 if absent), loads the HTML (fs or kv; 404 if none), and returns JSON:
`{ html, comments (full thread, userReactions empty for the anonymous agent), activity,
candidate_anchors, candidate_anchors_cache: {hash, cached}, project_meta, option_meta,
version_meta }`. **`candidate_anchors`** is a cheerio-extracted, KV-cached list (cap **50**)
of pin-able elements — `{ selector, tag, classes, text_preview (≤120 chars), bbox: null,
bbox_reason: "cheerio_fallback" }` — ranked by text length, drawn from an interest set
(`section, article, aside, nav, header, footer, main, [data-pin-anchor], .card, .deps,
.release, .feature, h1, h2, h3, figure, blockquote`).

**`POST /api/agent-comments`** — **write** a pin. JSON body: `author` (≤80), `avatar?`
(≤256; defaults to `author[0]`), `project`, `option`, `version`, `body` (≤4000), and a
**position** via one of (priority order): **`anchorText`** (≤400) → **`anchorSelector`**
(≤512) → **`x,y`** → sentinel. Requires at least one of those three (else **400**).
Position resolution:
1. **anchorText** → cheerio finds the **smallest containing element** (deepest normalized-text
   match, ties by DOM order); persists text + a derived selector + projected `x,y`. **No
   match ⇒ 400** with a `candidates` array (word-overlap-scored nearby snippets) so the agent
   can retry.
2. **anchorSelector** → cheerio resolves a position (depth-first index projected onto an
   estimated doc height); unresolved ⇒ a sentinel `(320,200)`.
3. **x,y** → used directly (clamped).
4. none → sentinel.
Seeds are treated as **1280px** natural width; selector/text-resolved pins center at
`x = 640`, `y` projected from DOM order (top margin 120, est. height 3200). Returns
`{ commentId, url: https://almanac.plow.co/p/<p>/<o>/v/<v>#pin-<id> }`, `Cache-Control:
no-store`.

**`DELETE /api/agent-comments/[commentId]`** — prune an **agent-authored** comment. Requires
an `x-almanac-agent-author` header; the server compares it (case-insensitively) to the row's
`author` (a **soft** anti-footgun, not a real boundary). Refuses human comments
(`agentAuthored !== true` ⇒ **409 not-agent**); wrong author ⇒ 403; missing ⇒ 404.

**`PATCH /api/agent-comments/[commentId]`** — toggle an agent comment's **resolved** flag
(default `true`; `{resolved:false}` to un-resolve). **No** author check (matches the open
resolve model). Optional `x-almanac-agent-author` → written as the resolve `by` provenance
(else `"agent"`). Refuses human comments (409).

---

## 12. Inputs (Interview)

| name | required | default | detect | ask |
|---|---|---|---|---|
| Node.js ≥ 18 + npm | yes | — | `node -v && npm -v` | (no prompt — agent installs/uses the host toolchain) |
| `cookoff-seeds/` corpus | yes | (repo-supplied) | `[ -d cookoff-seeds ] && ls cookoff-seeds/*/*.html` | "The seed HTML corpus. The repo ships one under `cookoff-seeds/<project>/<file>.html`. If absent, drop at least one `cookoff-seeds/seed/v1.html` so auto-discovery has something to surface." |
| `GOOGLE_CLIENT_ID` | conditional (prod auth) | none | env set | "Google OAuth client id (Workspace **Internal**, plow.co). Dev can skip if you stub auth, but the real product gates on it." |
| `GOOGLE_CLIENT_SECRET` | conditional | none | env set | "Google OAuth client secret paired with the id above." |
| `NEXTAUTH_SECRET` | yes | none | env set | "Random secret for NextAuth JWT signing (`openssl rand -base64 32`). Middleware verifies tokens with it." |
| `NEXTAUTH_URL` | conditional (prod) | `http://localhost:3210` | env set | "Public base URL of the deploy (e.g. `https://almanac.plow.co`)." |
| `KV_REST_API_URL` + `KV_REST_API_TOKEN` | no (dev) / yes (prod) | none → in-memory store | both env set | "Vercel KV credentials. **Absent ⇒ dev in-memory fallback** (data is per-process, non-durable). Provision KV for any shared/prod use." |
| `ALMANAC_AGENT_API_KEY` | conditional (agent door) | none | env set | "Shared secret agents send as `x-almanac-agent-key`. Required only if you exercise the agent endpoints." |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | conditional (agent door) | none | env set | "Vercel protection-bypass secret agents send as `x-vercel-protection-bypass` (layer-1 of the agent gate). Required only for the agent endpoints." |

**Step 0 — Interview (mandatory):** detect each row; send the CEO ONE consolidated message
listing ✓ satisfied / ✗ needed (with the `ask`) / ⚠ prior state to confirm (e.g. an existing
KV with data the rebuild would read). Then build autonomously to `## Verify` + §16.

---

## 13. Components (what this seed assembles)

| Component | Source | Notes |
|---|---|---|
| Next.js 14 + React 18 + TypeScript | npm | App Router, `strict`, port 3210 |
| `next-auth` v4 + Google provider | npm | JWT session, `@plow.co` gate |
| `@vercel/kv` | npm | prod store; in-memory `Map` fallback in dev |
| `cheerio` | npm | server-side anchor/candidate resolution (agent surface) |
| `@playwright/test` | npm (dev) | E2E (`npm run e2e`) |
| Google Fonts: Instrument Serif, DM Sans, DM Mono | CDN | preconnect + stylesheet in `<head>` |
| `cookoff-seeds/` HTML corpus | repo/input | auto-discovered into projects/options/v1 |
| `vercel.json` headers | inline config | DENY framing except `/seed/`,`/seed-kv/` |
| migration script (2-level → 3-level) | inline | idempotent, copies legacy keys forward |

---

## 14. Done (observable conditions)

Each independently checkable from a fresh shell (KV-less dev mode is fine for most):

- `npm run build` succeeds; `npm start` serves on **:3210**.
- Unauthenticated `GET /` ⇒ **redirect to `/login`** (302/307 to a `/login?next=/`).
- `GET /login` ⇒ 200, renders the Google sign-in card.
- With a signed-in `@plow.co` session: `GET /` lists ≥1 auto-discovered project; the status
  pills filter; `GET /p/<project>` shows the option grid; `GET /p/<p>/<o>` 307→ the latest
  version; the version page renders the iframe + version bar.
- `GET /seed/<round>/<slug>` returns the artifact HTML for a discovered path (200) and **404**
  for an unknown path; **401** when unauthenticated.
- A pin posted via `POST /api/comments` round-trips: it appears in `readVersionThread`, the
  iframe pin layer, and the activity panel; editing (author) sets `editedAt`; resolving hides
  the canvas pin but keeps the panel row; deleting a childless comment hard-purges while a
  replied-to comment soft-tombstones with a 5s undo.
- `POST /api/heartbeat` returns `{ active: [...] }` including the caller within 60s.
- Agent door: with both headers, `GET /api/agent-artifact/<p>/<o>/<v>` returns
  `{ html, comments, activity, candidate_anchors, … }`; `POST /api/agent-comments` with an
  `anchorText` that exists returns `{ commentId, url }` and the pin shows up alongside human
  pins; a bad `anchorText` returns 400 + `candidates`. Missing/!wrong headers ⇒ 401/403.
- Security headers present on `/` and **absent-framing-block** on `/seed/…` and `/seed-kv/…`.

---

## 15. Verify (runnable acceptance harness)

`## Verify` is a script whose **exit code is the truth** (0 = Done). Author it to boot the
app (KV-less dev mode acceptable), obtain a session (stub/inject a `@plow.co` JWT, or use a
test bypass), and assert the §14 conditions + the §16 journeys via Playwright (`npm run e2e`)
hitting `http://localhost:3210`. It must:

- start from a fresh shell, not depend on `## Steps` side effects beyond a built app,
- print enough to debug failures,
- finish in < 5 min for the core path.

A reference build ships in the repo with a large Playwright suite under `tests/e2e/`
(`verify-comment-flow`, `verify-resolve`, `verify-draggable-pins`, `verify-agent-artifact`,
`verify-agent-comment`, `verify-anchor-text`, `verify-version-switcher`, `verify-activity`,
`verify-responsive`, `verify-3-level-migration`, …). Treat those as the executable form of
§16 — green suite ⇒ proven for this agent.

---

## 16. Verification journeys (acceptance tests — all must pass)

Each states an action and the observable expected result. Manual or headless (Playwright).

1. **Auth gate.** Hit `/` with no session. *Expect:* redirect to `/login?next=/`. `/login`
   shows the "sign in with Google" card. A non-`@plow.co` rejection surfaces "Almanac is only
   for @plow.co accounts."
2. **Index list + status filter.** Signed in, open `/`. *Expect:* at least one project row
   (`<N> options · <M> pins`, "updated …"); clicking `archived`/`shipped` pills re-filters;
   default is `active`.
3. **Drill-in + latest redirect.** Open a project → option grid renders. Open an option
   (`/p/<p>/<o>`). *Expect:* a redirect to `/p/<p>/<o>/v/<latest>`, where `<latest>` is the
   newest version by mtime.
4. **Artifact renders.** On the version page. *Expect:* the version bar (breadcrumb
   project/option/version + "+ Comment" + "Activity") and an iframe whose document is the seed
   HTML (not `about:blank`).
5. **Drop a pin (toggle mode).** Click "+ Comment", click inside the artifact, type "needs
   more contrast", post. *Expect:* a numbered volt pin appears at the click point with the
   author's initials/avatar; the comment shows in the activity panel; reloading the page keeps
   it.
6. **Drop a pin (Alt+click).** Hold ⌥/Alt and click the artifact. *Expect:* the composer opens
   single-shot; posting drops a pin and returns to idle (mode not sticky).
7. **Hover/click popover + reply + react.** Hover a pin → popover opens; add a reply "agreed";
   open the emoji picker and react 🔥. *Expect:* the reply appears nested; the 🔥 chip shows
   count 1, toggled `data-mine`; clicking it again removes it (count→0, chip gone).
8. **Edit (author-only).** As the author, ⋯ → Edit a comment, save new text. *Expect:* body
   updates + "· edited" flag; `ts`/sort unchanged. A different signed-in user does **not** see
   Edit/Delete for that comment (403 if forced via API).
9. **Resolve hides the pin.** Toggle ✓ resolve on a pin. *Expect:* its canvas pin disappears;
   the panel row remains and is reachable under the "resolved" state filter; unresolve brings
   the pin back.
10. **Delete with undo.** Delete a **childless** comment. *Expect:* the pin vanishes + an Undo
    toast for ~5s; clicking Undo restores it; letting it elapse hard-deletes (gone after
    reload). Delete a comment **with replies** ⇒ tombstone "[comment deleted by author]" with
    replies intact.
11. **Drag to reposition (any user).** As a **non-author** signed-in user, drag a pin >4px and
    drop on a different element. *Expect:* the pin persists at the new spot after reload; a
    failed PATCH snaps it back.
12. **Pin clustering.** Place two pins within ~24px. *Expect:* they collapse into one cluster
    glyph with a `+N` badge; clicking it opens a pop-list of the members; picking one opens
    that pin's popover.
13. **Activity panel filters.** Open the panel (button or `a` key). *Expect:* search by author/
    body narrows the feed; `open`/`resolved` tabs filter; `recent`/`reactions` re-sorts; with
    >1 version, version chips multi-select; "jump to pin" scrolls + flashes the current-version
    pin; cross-version rows show "open <vN>". Panel open-state survives reload
    (`almanac.panel.open`).
14. **Version switcher + download + add version.** Open the switcher. *Expect:* all versions
    newest-first, current marked ✓, newest "latest"; the `↓` downloads
    `<p>-<o>-<v>.html`; "+ Add version" uploads an `.html` and redirects to the new `v<N+1>`.
15. **New project / add option (manual).** "+ new project" → fill name/slug/first-option +
    upload `.html` → redirect to the new version. On that project (manual) "+ add option"
    appears and works; on an **fs** project it does not (API 404 if forced).
16. **Inline rename keeps slug.** Rename a project (and an option, and a version) inline.
    *Expect:* the display name changes everywhere after `router.refresh()`, but the **URL/slug
    is unchanged** and existing pins/data still resolve.
17. **Presence.** Open the same version in two sessions. *Expect:* each sees the other in the
    ViewerStack within ~20s; a session whose tab is hidden drops out of the live (<60s) roster.
18. **Status edit.** Change a project status active→shipped. *Expect:* it moves to the
    `shipped` filter on the index immediately.
19. **Legacy URL redirect.** Hit `/p/<p>/v/<oldVersionSlug>`. *Expect:* a 308 to
    `/p/<p>/<oldVersionSlug>/v/v1` (or 404 if that option doesn't exist).
20. **Agent read.** `GET /api/agent-artifact/<p>/<o>/<v>` with both headers. *Expect:* JSON
    with `html`, `comments`, `activity`, and a non-empty `candidate_anchors` (each
    `bbox:null`, with `selector` + `text_preview`). Missing/wrong `x-vercel-protection-bypass`
    ⇒ 401; wrong `x-almanac-agent-key` ⇒ 401.
21. **Agent write (text anchor).** `POST /api/agent-comments` with `anchorText` matching real
    seed copy. *Expect:* `{ commentId, url:…#pin-<id> }`; the pin renders in the iframe + panel
    next to human pins, marked agent-authored. A bogus `anchorText` ⇒ **400** with a
    `candidates` array. Both agent-write headers missing ⇒ 401/403.
22. **Agent resolve / delete.** `PATCH /api/agent-comments/<id>` flips resolved (no author
    check); `DELETE` with the matching `x-almanac-agent-author` prunes it. Targeting a
    **human** comment ⇒ **409 not-agent**.

### Visual fidelity (the rebuild must *look* like §9, not just function)

Functional journeys 1–22 pass even on a wrong-looking build, so add these. Two tiers:
**computed-style assertions** (deterministic, primary) and **screenshot diff** (high-fidelity
gate, secondary). All run after a `@plow.co` test session is established.

23. **Fonts resolve correctly.** Via `getComputedStyle`: `body` `font-family` resolves to a
    **DM Sans** stack; the hero/page-title `h1` resolves to **Instrument Serif** with
    `font-style: italic` and `font-weight: 400`; a mono label (status pill / `.kbd`) resolves
    to **DM Mono**. *Expect:* exact matches — this is what "the fonts look distinct" was.
24. **Tokens + shadows exact.** Computed `--volt` = `rgb(213,239,138)`; page bg = chalk;
    a card's `box-shadow` and a popover's `box-shadow` match the §9.4 ladder; radius on a
    card = 12px, on a pill = 999px.
25. **Hover micro-interactions fire.** Programmatic hover + computed-style/bounding-box diff:
    `.project-row` gains `padding-left: 8px` and its arrow `translateX(4px)`; a breadcrumb
    crumb gains the volt-tint wash `rgba(213,239,138,0.32)`; the "+ Comment" toggle lifts
    `translateY(-1px)`; a card lifts `translateY(-2px)`; the rename **pencil** is hidden at
    rest and becomes visible on row hover. *Expect:* each state change observed (not just
    "element exists").
26. **Transition feel.** Computed `transition-duration`/`timing-function` on the sampled
    interactive elements are from the §9.3 ladder (default **180ms ease-out**; panel slide
    **220ms**). *Expect:* no `0s`/`linear` defaults left on interactive elements.
27. **Screenshot diff (gate, ~0.2% threshold).** Baselines of: index, version-bar +
    iframe, an open pin popover, the activity panel, a modal. Compared with Playwright
    `toHaveScreenshot`. *Expect:* within threshold vs the captured-from-real baselines;
    flags spacing/shadow/layout drift the computed checks can't. (Secondary — environment
    sensitive; computed-style tiers 23–26 are the hard gate.)

---

## 17. Failure modes (known)

**Symptom: pins/listeners attach to a blank doc and never fire.**
- Detect: pins don't render though comments exist; iframe shows content.
- Fix: don't trust `readyState==="complete"` on the initial `about:blank`; bump a load
  **counter** on the real `load` (URL ≠ `about:blank`) and key pin/click/cluster effects on it.

**Symptom: `/seed*` won't load in the iframe (blocked by X-Frame-Options).**
- Detect: empty iframe + a framing console error.
- Fix: the security-header rule must **exclude** `/seed/` and `/seed-kv/` (the regex source in
  `vercel.json` negative-lookahead is load-bearing).

**Symptom: legacy projects show 0 comments/viewers after deploy.**
- Detect: a known project's pins/viewed-by vanished.
- Fix: implement the **2-level read fallback** for `v === "v1"` (and triplet back-fill on
  legacy rows); don't blank the surface ahead of the migration script.

**Symptom: agent endpoints 307→/login.**
- Detect: agent POST/GET redirected to the sign-in page.
- Fix: add `/api/agent-comments` and `/api/agent-artifact` to middleware **PUBLIC_PATHS** (they
  carry their own header auth).

**Symptom: HTML upload 413s.**
- Detect: large seed files rejected.
- Fix: cap at **3.5 MB** (3,670,016 bytes) — under Vercel's 4.5 MB serverless body limit with
  multipart headroom.

**Symptom: reposition/resolve 403 for non-authors.**
- Detect: the crit team can't move/resolve others' pins.
- Fix: reposition + resolve are **open to any signed-in user** by design — only edit/delete are
  author-gated.

**Symptom: dev has no KV and the app crashes.**
- Detect: `@vercel/kv` errors with no `KV_REST_API_*`.
- Fix: the **in-memory Map fallback** must engage when those env vars are absent (warn once;
  never in production).

---

## 18. Convergence notes (read before building)

Details most likely to drift between two independent rebuilds — lock them in:
- **3-level model is canonical** (Project → Option → Version) but **every v1 read falls back to
  the legacy 2-level key**; legacy comment rows back-fill `optionId←versionId, versionId←"v1"`.
- **KV key shapes in §5 are exact.** IDs = 16 hex chars (`/^[a-f0-9]{16}$/`).
- **Two auth doors**: session-cookie (humans, `@plow.co`) and two-header (agents); both write
  the **same** comment shape; agent rows carry `agentAuthored:true`.
- **Authorship split**: edit/delete = author-only; **reposition + resolve = any signed-in
  user**.
- **Soft-delete iff replies exist**, else hard purge; **5s undo** window.
- **Pins live inside the iframe doc**, numbered chronologically, **resolved pins hidden from
  canvas**, **24px clustering** with a pop-list.
- **Placement**: "+ Comment" sticky toggle + **Alt/⌥-click single-shot**; the bare **`c`
  shortcut is removed**; `a` toggles the panel; **Esc** exits placement.
- **Quick-reaction set is exactly `👍 👎 🔥 🤔 ❤️`**; the picker is a curated in-house ~80-emoji
  set (no library) with a `localStorage` frequently-used row.
- **Heartbeat 20s / live window 60s**, paused on hidden tabs.
- **Optimistic-with-rollback** on every mutation; `router.refresh()` after renames.
- **Security headers DENY framing except `/seed/` and `/seed-kv/`.**
- **Port 3210.** Brand: **chalk bg, volt accent, Instrument Serif headings, film-grain
  overlay**; fonts DM Sans / DM Mono / Instrument Serif.
- **Agent position priority**: `anchorText` > `anchorSelector` > `(x,y)` > sentinel; text-miss
  returns `candidates`.

---

## 19. Installation / handoff

Hand this seed to a coding agent: *"Hydrate this seed: build the Almanac app it specifies (a
Next.js 14 + NextAuth-Google + Vercel-KV design-review surface) until every §16 journey
passes. Run §15 to self-verify before declaring done."* The canonical source of truth is the
running app on `:3210` plus a green Playwright suite; the reference build lives at
`github.com/plow-pbc/almanac` (codebase package `seeds-feedback`).
