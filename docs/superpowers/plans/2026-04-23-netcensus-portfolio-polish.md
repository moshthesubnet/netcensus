# netcensus Portfolio Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform netcensus into a hiring-manager-ready GitHub surface — restyled dashboard matching moshthesubnet.com, bundled demo mode for reproducible screenshots, rewritten README with inline architecture diagrams, case-study-style `ARCHITECTURE.md`, and a clean repo root.

**Architecture:** Pure docs + UI polish — no feature changes, no module refactors, no dependency upgrades. Existing single-file `frontend/index.html` is restyled in-place. A new `src/demo_seed.py` + `docker-compose.demo.yml` + `DEMO_MODE` env flag lets anyone run a reproducible seeded instance for screenshots. README/ARCHITECTURE rewritten against the new visuals. Hygiene pass cleans repo root.

**Tech Stack:** Python 3.12 · FastAPI · asyncio · aiosqlite · Tailwind CDN · vanilla HTML/CSS/JS · Docker Compose. Inline SVG for diagrams.

**Source spec:** [`../specs/2026-04-23-netcensus-portfolio-polish-design.md`](../specs/2026-04-23-netcensus-portfolio-polish-design.md)

---

## File Structure

### New files

- `src/demo_seed.py` — deterministic seed that populates a fresh SQLite DB with one coherent homelab narrative. ~200 lines. Exports `seed_demo_db(db_path)`.
- `tests/test_demo_seed.py` — unit test asserting the seed is deterministic and produces the counts the spec requires.
- `docker-compose.demo.yml` — secondary compose file with `DEMO_MODE=true` on host port 8080.
- `docs/images/architecture.svg` — inline architecture diagram (data sources → app → surfaces).
- `docs/images/vlan-before-after.svg` — inline before/after diagram for the "why ARP fails" story.
- `docs/images/dashboard.png` — high-res screenshot of the restyled dashboard against seeded data.
- `ARCHITECTURE.md` — case-study deep dive (replaces `PROJECT_SUMMARY.md` via `git mv`).

### Modified files

- `frontend/index.html` — restyled in-place. Same regions, new typography / palette / overview strip / quieter chrome.
- `src/main.py` — lifespan checks `DEMO_MODE`; if set, skip scanner + syslog and call `seed_demo_db`.
- `start.sh` — accept `DEMO=1` shortcut that exports `DEMO_MODE=true`.
- `README.md` — full rewrite per spec §3.
- `CLAUDE.md` — retitle to netcensus, correct the scapy reference. (Local only; gitignored.)
- `.gitignore` — add `.superpowers/` so visual-companion artifacts stay local.
- `requirements.txt` — no changes expected; verified by grep during Phase 0.

### Deleted files

- `scan.py` (tracked, pre-OPNsense-era scratch).
- `_full_scan_tmp.py`, `_live_scan_tmp.py`, `_verify_scan_tmp.py` (untracked on-disk scratch).
- `network_monitor.db` (untracked on-disk 10 GB local SQLite; gitignored already). Will require `sudo` because root-owned.
- `PROJECT_SUMMARY.md` (renamed to `ARCHITECTURE.md` via `git mv`; content rewritten in Phase 5).

---

## Execution order and checkpoints

- **Phase 0 — Hygiene pass.** Small and mechanical. Unblocks a clean workspace before other work lands.
- **Phase 1 — Dashboard restyle (CHECKPOINT C1).** Dashboard visually done; repo still shippable with current README.
- **Phase 2 — Demo mode (CHECKPOINT C2).** Third parties can `docker compose -f docker-compose.demo.yml up` and see the restyled dashboard with seeded data. Screenshots can now be taken reproducibly.
- **Phase 3 — Screenshots and SVG diagrams.** Build the three visuals the README references.
- **Phase 4 — README rewrite.**
- **Phase 5 — ARCHITECTURE.md rewrite (CHECKPOINT C3).** Full portfolio state.
- **Phase 6 — Quality gates.** Manual verification against spec success criteria.

---

## Phase 0 — Hygiene pass

### Task 0.1: Remove the 10 GB local SQLite file

**Files:**
- Delete: `network_monitor.db` (repo root, untracked, root-owned).

- [ ] **Step 1: Confirm the file is untracked**

Run: `cd /home/skyler/network-monitoring-app && git ls-files | grep -c network_monitor.db`
Expected output: `0`

If non-zero, STOP — file is tracked and removing it requires coordination. Alert the user.

- [ ] **Step 2: Confirm it is covered by .gitignore**

Run: `cd /home/skyler/network-monitoring-app && git check-ignore network_monitor.db && echo ok`
Expected output: `network_monitor.db` followed by `ok`.

- [ ] **Step 3: Delete the file (requires sudo; root-owned)**

Run: `sudo rm /home/skyler/network-monitoring-app/network_monitor.db`
Then: `ls -la /home/skyler/network-monitoring-app/network_monitor.db 2>&1`
Expected output: `ls: cannot access ... No such file or directory`

- [ ] **Step 4: No commit needed**

The file was never tracked. Working tree is already clean for this change.

---

### Task 0.2: Delete on-disk scratch Python files

**Files:**
- Delete: `_full_scan_tmp.py`, `_live_scan_tmp.py`, `_verify_scan_tmp.py` (untracked; gitignored via `_*_tmp.py`).

- [ ] **Step 1: Verify they are untracked**

Run: `cd /home/skyler/network-monitoring-app && git ls-files | grep -E "^_.*_tmp\.py$" | wc -l`
Expected output: `0`

- [ ] **Step 2: Delete**

Run: `rm /home/skyler/network-monitoring-app/_full_scan_tmp.py /home/skyler/network-monitoring-app/_live_scan_tmp.py /home/skyler/network-monitoring-app/_verify_scan_tmp.py`
Then: `ls /home/skyler/network-monitoring-app/_*_tmp.py 2>&1`
Expected output: `ls: cannot access ...`

- [ ] **Step 3: No commit needed** (files were untracked).

---

### Task 0.3: Remove tracked `scan.py` scratch file

**Files:**
- Delete: `scan.py` (tracked, 7 KB, pre-OPNsense-era ARP scratch script).

- [ ] **Step 1: Confirm it is not imported from `src/`**

Run: `cd /home/skyler/network-monitoring-app && grep -rn "from scan\|import scan" src/ 2>&1`
Expected output: empty (no matches).

If non-empty, STOP — scan.py is actually used. Alert the user.

- [ ] **Step 2: Remove from tracking**

Run: `cd /home/skyler/network-monitoring-app && git rm scan.py`

- [ ] **Step 3: Commit**

Run:
```bash
cd /home/skyler/network-monitoring-app && git commit -m "chore: remove scan.py scratch script

Leftover ARP scratch from before OPNsense API replaced scapy as the
primary discovery path."
```

---

### Task 0.4a: Verify `.env` is not tracked

**Files:** (read-only)

- [ ] **Step 1: Confirm `.env` is not in the git index**

Run: `cd /home/skyler/network-monitoring-app && git ls-files | grep -E "^\.env$"`
Expected output: empty.

If non-empty, STOP. Removing a tracked `.env` with real credentials requires coordination — alert the user, don't silently `git rm` a secrets file.

- [ ] **Step 2: Confirm `.env` is gitignored**

Run: `cd /home/skyler/network-monitoring-app && git check-ignore .env && echo ok`
Expected output: `.env` followed by `ok`.

No commit needed.

---

### Task 0.4b: Rename the docker-compose service to `netcensus`

**Files:**
- Modify: `docker-compose.yml`.

- [ ] **Step 1: Rename the service**

Use the Edit tool. Old:
```yaml
services:
  network-monitor:
```
New:
```yaml
services:
  netcensus:
```

- [ ] **Step 2: Verify nothing else in the repo references the old service name**

Run: `cd /home/skyler/network-monitoring-app && grep -rn "network-monitor:" . --include="*.yml" --include="*.yaml" --include="*.sh" --include="*.md" 2>/dev/null | grep -v docs/_archive`
Expected output: empty.

- [ ] **Step 3: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add docker-compose.yml && git commit -m "chore: rename docker-compose service network-monitor -> netcensus"
```

---

### Task 0.4: Harden `.gitignore`

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append `.superpowers/` to `.gitignore`**

Run:
```bash
cd /home/skyler/network-monitoring-app && grep -q "^\.superpowers/" .gitignore || printf '\n# Visual brainstorming artifacts\n.superpowers/\n' >> .gitignore
```

- [ ] **Step 2: Verify**

Run: `grep -n ".superpowers" /home/skyler/network-monitoring-app/.gitignore`
Expected output: one line containing `.superpowers/`.

- [ ] **Step 3: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add .gitignore && git commit -m "chore: ignore .superpowers brainstorming artifacts"
```

---

### Task 0.5: Retitle local `CLAUDE.md` and correct the tech-stack line

**Files:**
- Modify: `CLAUDE.md` (gitignored, local-only — affects Claude-session memory, not the public repo).

- [ ] **Step 1: Retitle header**

Use the Edit tool on `/home/skyler/network-monitoring-app/CLAUDE.md`:

Old:
```markdown
# Network Discovery & Syslog Monitor
```

New:
```markdown
# netcensus
```

- [ ] **Step 2: Correct the scapy line in the Tech Stack block**

Use the Edit tool. Old:
```markdown
* **Backend:** Python 3, FastAPI, `asyncio`, `scapy` (for ARP), `aiosqlite`
```

New:
```markdown
* **Backend:** Python 3.12, FastAPI, `asyncio`, `aiosqlite`. `scapy` remains as an optional fallback only — the primary discovery path is the OPNsense REST API (see commit 5acb0be).
```

- [ ] **Step 3: Verify**

Run: `head -10 /home/skyler/network-monitoring-app/CLAUDE.md`
Expected: first line is `# netcensus`; Tech Stack shows the OPNsense-primary wording.

- [ ] **Step 4: No commit** — `CLAUDE.md` is gitignored.

---

## Phase 1 — Dashboard restyle (Checkpoint C1)

The dashboard is a single 1225-line file at `frontend/index.html`. All changes are made in-place — no new files. Palette, typography, and slop-guardrail rules are codified in the spec §1 and must be followed literally.

**Reference palette (from `/home/skyler/website/assets/css/custom.css`):**

```
Surface:   #111111 body, #1a1a1a card, #1c1c1c alt-card, #262626 border
Text:      #fafafa primary, #b0b0b0 body, #a3a3a3 / #737373 muted, #525252 quietest
Accent:    #5eead4 (teal), #4cc9b0 (pressed)
Error:     #f87171
```

**Typography:**

- Georgia for wordmark and page-level titles.
- `system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif` for UI chrome.
- `'Fira Code', 'Courier New', monospace` for data (IPs, MACs, counters, table body).

**Slop guardrails (must hold at all times):**

1. Accent teal appears in at most two places per viewport: monogram/wordmark + one primary action. Nowhere else.
2. No gradients anywhere.
3. No emoji in UI copy.
4. No generic stock icons. SVGs only where earned (sources, type badges, close/expand/copy).
5. No glassmorphism. Solid dark surfaces + 1 px hairline borders.

---

### Task 1.1: Swap Tailwind font config, add Google font preloads

**Files:**
- Modify: `frontend/index.html` (the `<head>` block lines 1–45).

- [ ] **Step 1: Replace the JetBrains Mono preconnect/link with Fira Code**

Use the Edit tool. Old:
```html
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
```

New:
```html
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&display=swap" rel="stylesheet" />
```

- [ ] **Step 2: Update the Tailwind font config block**

Use the Edit tool. Old:
```javascript
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: { mono: ['JetBrains Mono', 'Fira Code', 'monospace'] },
          transitionProperty: { panel: 'transform, opacity' },
        },
      },
    };
```

New:
```javascript
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: {
            mono: ['Fira Code', 'Courier New', 'monospace'],
            sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
            serif: ['Georgia', 'Times New Roman', 'serif'],
          },
          colors: {
            surface: {
              DEFAULT: '#111111',
              card: '#1a1a1a',
              alt: '#1c1c1c',
              border: '#262626',
            },
            ink: {
              primary: '#fafafa',
              body: '#b0b0b0',
              muted: '#a3a3a3',
              faint: '#737373',
              quiet: '#525252',
            },
            accent: {
              DEFAULT: '#5eead4',
              pressed: '#4cc9b0',
            },
            alert: '#f87171',
          },
          transitionProperty: { panel: 'transform, opacity' },
        },
      },
    };
```

- [ ] **Step 3: Update the base `<style>` block to use the new fonts**

Use the Edit tool. Old:
```css
    html { color-scheme: dark; }
    body { font-family: 'JetBrains Mono', monospace; }
```

New:
```css
    html { color-scheme: dark; }
    body { font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }
    .wordmark { font-family: Georgia, 'Times New Roman', serif; font-weight: 400; letter-spacing: -0.01em; }
    .mono { font-family: 'Fira Code', 'Courier New', monospace; }

    /* Respect reduced-motion preference (spec §1 slop-guardrails). */
    @media (prefers-reduced-motion: reduce) {
      #panel, #overlay, * { transition: none !important; animation: none !important; }
    }
```

- [ ] **Step 4: Update `<body>` class**

Use the Edit tool. Old:
```html
<body class="dark bg-gray-950 text-gray-100 min-h-screen antialiased">
```

New:
```html
<body class="dark bg-surface text-ink-primary min-h-screen antialiased">
```

- [ ] **Step 5: Open in a browser, confirm nothing is blatantly broken**

Run: `cd /home/skyler/network-monitoring-app && python3 -m http.server 8765 --directory frontend` (background) and open `http://10.30.30.30:8765` in a browser. Confirm the page loads (even though it'll look wrong — that's expected; the subsequent tasks fix the rest). Kill the server (`Ctrl-C`) when done.

- [ ] **Step 6: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add frontend/index.html && git commit -m "feat(ui): add website-matched fonts and tailwind palette

Swap JetBrains Mono → Fira Code for data, add Georgia for wordmark,
add system sans for body chrome. Introduce surface/ink/accent palette
tokens that match moshthesubnet.com."
```

---

### Task 1.2: Restyle the header wordmark bar

**Files:**
- Modify: `frontend/index.html` (the `<header>` block, lines 48–62).

- [ ] **Step 1: Replace the brand + stats-row + source-row + refresh block with a clean wordmark bar**

Use the Edit tool. Old (lines 48–121, the full `<header>` opening down through the closing `</header>`):

```html
<header class="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-30">
  <div class="max-w-screen-2xl mx-auto px-6 py-4 flex items-center justify-between gap-6 flex-wrap">

    <!-- Brand -->
    <div class="flex items-center gap-3">
      ...
```

(Replace the **entire** `<header>...</header>` block.)

New:
```html
<header class="border-b border-surface-border bg-surface sticky top-0 z-30">
  <div class="max-w-screen-2xl mx-auto px-6 py-4 flex items-center justify-between gap-4">

    <!-- Brand -->
    <div class="flex items-center gap-3">
      <div class="w-7 h-7 rounded-md bg-surface-card border border-surface-border flex items-center justify-center text-accent mono text-sm font-semibold">nc</div>
      <div class="flex items-baseline gap-2.5">
        <span class="wordmark text-ink-primary text-xl">netcensus</span>
        <span class="text-ink-quiet text-xs" id="deployment-label">/ homelab-core</span>
      </div>
    </div>

    <!-- Live dot + Refresh -->
    <div class="flex items-center gap-4">
      <span class="flex items-center gap-2 text-xs text-ink-faint">
        <span class="dot live-dot bg-accent" style="box-shadow:0 0 8px rgba(94,234,212,0.5);"></span>
        <span id="last-updated">–</span>
      </span>
      <button id="btn-refresh"
        class="px-3.5 py-1.5 rounded-md text-xs font-medium border border-accent text-accent hover:bg-accent hover:text-surface transition-colors">
        Refresh
      </button>
    </div>
  </div>
</header>
```

- [ ] **Step 2: Smoke-test**

Open `frontend/index.html` in a browser the same way as Task 1.1 Step 5. Confirm:
- Wordmark shows `netcensus` in Georgia.
- `nc` monogram is a teal letter on a dark tile.
- Live dot is teal with glow.
- Refresh is an outlined teal chip (no fill).

- [ ] **Step 3: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add frontend/index.html && git commit -m "feat(ui): rewrite dashboard header as a clean wordmark bar

Replace the crowded brand/stats/source/refresh row with a minimal bar:
nc monogram + netcensus wordmark + deployment label + live dot +
outlined refresh. Stats and sources move to the overview strip in a
follow-up commit."
```

---

### Task 1.3: Add the overview strip (4 cards) below the header

**Files:**
- Modify: `frontend/index.html` — insert a new section at the top of `<main>`, before the existing search row (currently at line 124).

- [ ] **Step 1: Insert overview-strip markup immediately after the `<main>` opening tag**

Use the Edit tool. Old:
```html
<!-- ═══════════════════════════════════════════ MAIN ══ -->
<main class="max-w-screen-2xl mx-auto px-6 py-6">

  <!-- Search + filter bar -->
```

New:
```html
<!-- ═══════════════════════════════════════════ MAIN ══ -->
<main class="max-w-screen-2xl mx-auto px-6 py-6">

  <!-- Overview strip -->
  <section id="overview" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
    <div class="bg-surface-card border border-surface-border rounded-lg px-4 py-3">
      <div class="text-[10px] text-ink-faint uppercase tracking-[0.12em] font-semibold">Devices</div>
      <div class="mono text-2xl text-ink-primary mt-1" id="ov-total">–</div>
      <div class="text-[11px] text-accent mt-0.5" id="ov-new">&nbsp;</div>
    </div>
    <div class="bg-surface-card border border-surface-border rounded-lg px-4 py-3">
      <div class="text-[10px] text-ink-faint uppercase tracking-[0.12em] font-semibold">VLANs</div>
      <div class="mono text-2xl text-ink-primary mt-1" id="ov-vlans">–</div>
      <div class="text-[11px] text-ink-faint mt-0.5" id="ov-vlans-note">&nbsp;</div>
    </div>
    <div class="bg-surface-card border border-surface-border rounded-lg px-4 py-3">
      <div class="text-[10px] text-ink-faint uppercase tracking-[0.12em] font-semibold">Composition</div>
      <div class="mono text-xs mt-1.5 flex gap-3 flex-wrap">
        <span class="text-ink-body">BM <span class="text-ink-primary font-medium" id="ov-bm">–</span></span>
        <span class="text-accent">D <span class="font-medium" id="ov-docker">–</span></span>
        <span class="text-ink-body">V <span class="text-ink-primary font-medium" id="ov-vm">–</span></span>
        <span class="text-ink-muted">L <span class="font-medium" id="ov-lxc">–</span></span>
      </div>
      <div class="mt-2 flex h-[3px] rounded-sm overflow-hidden" id="ov-bar">
        <div class="bg-ink-quiet" id="ov-bar-bm"></div>
        <div class="bg-accent" id="ov-bar-docker"></div>
        <div class="bg-ink-body" id="ov-bar-vm"></div>
        <div class="bg-ink-muted" id="ov-bar-lxc"></div>
      </div>
    </div>
    <div class="bg-surface-card border border-surface-border rounded-lg px-4 py-3">
      <div class="text-[10px] text-ink-faint uppercase tracking-[0.12em] font-semibold">Alerts</div>
      <div class="mono text-2xl text-alert mt-1" id="ov-alerts">–</div>
      <div class="text-[11px] text-alert mt-0.5" id="ov-alerts-note">&nbsp;</div>
    </div>
  </section>

  <!-- Source-health row -->
  <section id="source-row" class="mono text-[11px] text-ink-quiet flex flex-wrap gap-x-4 gap-y-1 mb-5">
    <span>sources</span>
    <span data-source="opnsense_arp"><span class="text-ink-quiet">○</span> opnsense-arp</span>
    <span data-source="opnsense_dhcp"><span class="text-ink-quiet">○</span> dhcp</span>
    <span data-source="opnsense_ndp"><span class="text-ink-quiet">○</span> ndp</span>
    <span data-source="proxmox"><span class="text-ink-quiet">○</span> proxmox</span>
    <span data-source="docker"><span class="text-ink-quiet">○</span> docker</span>
    <span data-source="nmap"><span class="text-ink-quiet">○</span> nmap</span>
    <span data-source="snmp"><span class="text-ink-quiet">○</span> snmp</span>
  </section>

  <!-- Search + filter bar -->
```

- [ ] **Step 2: Update the existing JS that populates the old `count-*` chips**

Search for the existing render function that writes `count-total`, `count-bm`, `count-docker`, `count-vm`, `count-lxc` in `frontend/index.html`. Find the first occurrence and extend it to also write the new `ov-*` elements and set the flex ratios on the composition bar.

Run: `grep -n "count-total\|count-bm\|count-docker\|count-vm\|count-lxc" /home/skyler/network-monitoring-app/frontend/index.html`

Expected: several lines, one in the header (to be removed in the next step) and a block of JS that sets `textContent` on these IDs.

Edit the JS block. Locate the pattern:
```javascript
document.getElementById('count-total').textContent = total;
document.getElementById('count-bm').textContent = bm;
document.getElementById('count-docker').textContent = docker;
document.getElementById('count-vm').textContent = vm;
document.getElementById('count-lxc').textContent = lxc;
```

(Exact variable names may differ. Keep the existing variables; rename them in the replacement if needed.)

Replace with a block that also writes to the overview strip:
```javascript
// Legacy chip IDs (header still references them until Task 1.4)
const setText = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
setText('count-total', total); setText('count-bm', bm);
setText('count-docker', docker); setText('count-vm', vm); setText('count-lxc', lxc);

// Overview strip
setText('ov-total', total);
setText('ov-bm', bm);
setText('ov-docker', docker);
setText('ov-vm', vm);
setText('ov-lxc', lxc);

// Composition bar flex ratios
const bar = (id, n) => { const el = document.getElementById(id); if (el) el.style.flex = String(n || 0); };
bar('ov-bar-bm', bm); bar('ov-bar-docker', docker);
bar('ov-bar-vm', vm); bar('ov-bar-lxc', lxc);

// Derived: VLAN count and alerts (compute from the same payload)
const vlans = new Set((devices || []).map(d => d.vlan).filter(Boolean));
setText('ov-vlans', vlans.size || '–');
setText('ov-vlans-note', vlans.size ? 'all reachable' : '');
const alerts = (devices || []).filter(d => d.disappearance_count >= 3).length;
setText('ov-alerts', alerts);
setText('ov-alerts-note', alerts ? 'device_gone' : '');
```

(If the existing render function uses a different variable name than `devices`, use the existing one.)

- [ ] **Step 3: Update the source-health update JS**

Search: `grep -n "source-chip\|source-health\|dot bg" /home/skyler/network-monitoring-app/frontend/index.html`.

Locate the function that sets per-source health (there's a block that iterates `opnsense_arp | opnsense_dhcp | proxmox | docker | opnsense_ndp | nmap | snmp` and toggles dot classes). The old code sets a Tailwind class on `span.dot` children of `.source-chip`. Update it to target the new `#source-row span[data-source]` and flip the dot character and colour:

Replace the per-source class-toggle code with:
```javascript
function paintSource(key, healthy) {
  const el = document.querySelector(`#source-row span[data-source="${key}"]`);
  if (!el) return;
  const dot = el.firstElementChild;
  if (healthy === null || healthy === undefined) {
    // disabled / not configured
    dot.textContent = '○';
    dot.className = 'text-ink-quiet';
  } else if (healthy) {
    dot.textContent = '●';
    dot.className = 'text-accent';
  } else {
    dot.textContent = '●';
    dot.className = 'text-alert';
  }
}
```

Wherever the previous code looked up `.source-chip[data-source=...]` and toggled classes, call `paintSource(key, healthy)` instead.

- [ ] **Step 4: Smoke-test in a browser**

Same procedure as Task 1.1 Step 5. Confirm: overview strip renders under the header with four cards; composition bar has visible flex ratios; source row is a quiet text line underneath.

(Values will be `–` until the backend runs. That's expected.)

- [ ] **Step 5: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add frontend/index.html && git commit -m "feat(ui): add overview strip and quiet source row

Four palette-safe cards (Devices, VLANs, Composition, Alerts) replace
the in-header chip-row. Sources become a quiet Fira Code line below.
Legacy count-* IDs still populated so the old markup doesn't break
before its removal in the next commit."
```

---

### Task 1.4: Remove legacy chip-row and source-chip markup

**Files:**
- Modify: `frontend/index.html`.

- [ ] **Step 1: Delete the old legacy-chip JS branch**

Search: `grep -n "count-total\|count-bm" /home/skyler/network-monitoring-app/frontend/index.html`.

The header no longer contains `count-*` IDs after Task 1.2. If any `setText('count-...')` lines remain from Task 1.3, delete them — they target DOM that no longer exists.

- [ ] **Step 2: Verify no stale `source-chip` references remain**

Run: `grep -n "source-chip\|count-total\|count-bm\|count-docker\|count-vm\|count-lxc" /home/skyler/network-monitoring-app/frontend/index.html`
Expected output: empty (no matches).

If any remain, remove them.

- [ ] **Step 3: Smoke-test** — reload the page, confirm no console errors and the overview still updates.

- [ ] **Step 4: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add frontend/index.html && git commit -m "chore(ui): remove legacy count-* and source-chip references"
```

---

### Task 1.5: Restyle the search and export row

**Files:**
- Modify: `frontend/index.html` (the search + filter bar block, currently lines ~127–156 but shifted after previous tasks).

- [ ] **Step 1: Update the search input styling and the export buttons**

Use the Edit tool. Old (the search input wrapper):
```html
      <input id="search" type="text" placeholder="Filter by IP, vendor, alias…"
        class="w-full pl-9 pr-3 py-2 rounded-lg bg-gray-800 border border-gray-700
               text-sm text-gray-200 placeholder-gray-500 focus:outline-none
               focus:ring-2 focus:ring-indigo-500 focus:border-transparent" />
```

New:
```html
      <input id="search" type="text" placeholder="Filter by IP, vendor, alias…"
        class="w-full pl-9 pr-3 py-2 rounded-md bg-surface-card border border-surface-border
               text-sm text-ink-primary placeholder-ink-quiet focus:outline-none
               focus:border-accent focus:ring-1 focus:ring-accent transition-colors mono" />
```

Old (the search-icon SVG wrapper keeps `text-gray-500` — change to `text-ink-faint`):
```html
      <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500"
```
New:
```html
      <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-faint"
```

Old (Export CSV button and Export JSON button — identical structure, class replace each):
```html
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
               bg-gray-800 border border-gray-700 hover:bg-gray-700 text-gray-300 transition-colors">
```
New (apply to **both** Export CSV and Export JSON):
```html
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium
               bg-surface-card border border-surface-border hover:border-ink-quiet text-ink-body transition-colors">
```

- [ ] **Step 2: Smoke-test** — confirm the search input has a teal focus ring and the export buttons look like subtle outlined chips.

- [ ] **Step 3: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add frontend/index.html && git commit -m "feat(ui): restyle search + export row to match palette"
```

---

### Task 1.6: Restyle the bulk-action bar

**Files:**
- Modify: `frontend/index.html` (the `#bulk-bar` block).

- [ ] **Step 1: Re-theme the bulk bar from indigo to neutral surface with teal accent on the primary action**

Use the Edit tool. Old:
```html
  <div id="bulk-bar" class="hidden mb-4 rounded-xl bg-indigo-950 border border-indigo-700 px-4 py-3 flex items-center gap-3 flex-wrap">
    <span id="bulk-count" class="text-sm font-medium text-indigo-200"></span>
```

New:
```html
  <div id="bulk-bar" class="hidden mb-4 rounded-lg bg-surface-card border border-surface-border px-4 py-3 flex items-center gap-3 flex-wrap">
    <span id="bulk-count" class="text-sm font-medium text-ink-primary"></span>
```

Old (the select inside bulk-bar):
```html
      <select id="bulk-type-select"
        class="px-3 py-1.5 rounded-lg bg-gray-800 border border-gray-700 text-sm text-gray-200
               focus:outline-none focus:ring-2 focus:ring-indigo-500">
```
New:
```html
      <select id="bulk-type-select"
        class="px-3 py-1.5 rounded-md bg-surface-card border border-surface-border text-sm text-ink-primary
               focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent">
```

Old (the Apply Type button — filled indigo; this is the primary action):
```html
      <button id="bulk-retype"
        class="px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors">
```
New:
```html
      <button id="bulk-retype"
        class="px-3 py-1.5 rounded-md text-xs font-medium border border-accent text-accent hover:bg-accent hover:text-surface transition-colors">
```

Old (Export Selection — secondary):
```html
      <button id="bulk-export"
        class="px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-700 hover:bg-gray-600 text-gray-200 transition-colors">
```
New:
```html
      <button id="bulk-export"
        class="px-3 py-1.5 rounded-md text-xs font-medium bg-surface-card border border-surface-border hover:border-ink-quiet text-ink-body transition-colors">
```

Old (Clear — quietest):
```html
      <button id="bulk-clear"
        class="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 hover:text-gray-300 transition-colors">
```
New:
```html
      <button id="bulk-clear"
        class="px-3 py-1.5 rounded-md text-xs font-medium text-ink-faint hover:text-ink-primary transition-colors">
```

- [ ] **Step 2: Smoke-test** — select a few rows; confirm the bulk bar theme reads right (teal outline on the primary action only).

- [ ] **Step 3: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add frontend/index.html && git commit -m "feat(ui): re-theme bulk-action bar from indigo to palette neutrals"
```

---

### Task 1.7: Restyle the device table

**Files:**
- Modify: `frontend/index.html` (the table wrapper and its children).

- [ ] **Step 1: Update the table wrapper surface**

Use the Edit tool. Old:
```html
  <div class="rounded-xl border border-gray-800 overflow-hidden bg-gray-900">
```
New:
```html
  <div class="rounded-lg border border-surface-border overflow-hidden bg-surface-card">
```

- [ ] **Step 2: Update the loading state colors**

Use the Edit tool. Old:
```html
    <div id="table-loading" class="flex items-center justify-center py-16 text-gray-600 gap-2">
```
New:
```html
    <div id="table-loading" class="flex items-center justify-center py-16 text-ink-faint gap-2">
```

- [ ] **Step 3: Update the table header row theme**

Use the Edit tool. Old:
```html
    <table id="device-table" class="w-full text-sm hidden">
      <thead>
        <tr class="border-b border-gray-800 text-xs text-gray-500 uppercase tracking-wider">
```
New:
```html
    <table id="device-table" class="w-full text-sm hidden mono">
      <thead>
        <tr class="border-b border-surface-border text-[10px] text-ink-faint uppercase tracking-[0.1em]">
```

- [ ] **Step 4: Update the `select-all` checkbox theme**

Use the Edit tool. Old:
```html
          <input id="select-all" type="checkbox" class="rounded border-gray-600 bg-gray-800 text-indigo-500 focus:ring-indigo-500 focus:ring-offset-0 cursor-pointer" />
```
New:
```html
          <input id="select-all" type="checkbox" class="rounded border-surface-border bg-surface-card text-accent focus:ring-accent focus:ring-offset-0 cursor-pointer" />
```

- [ ] **Step 5: Update the empty-state theme**

Use the Edit tool. Old:
```html
    <div id="table-empty" class="hidden flex-col items-center justify-center py-16 text-center gap-2">
      <svg class="w-10 h-10 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      <p class="text-gray-500 text-sm">No devices found.</p>
      <p class="text-gray-600 text-xs">Check that the scanner is running with sufficient privileges.</p>
    </div>
```
New:
```html
    <div id="table-empty" class="hidden flex-col items-center justify-center py-16 text-center gap-2">
      <svg class="w-10 h-10 text-ink-quiet" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
        <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
      </svg>
      <p class="text-ink-body text-sm">No devices found.</p>
      <p class="text-ink-faint text-xs">Check that the scanner is running with sufficient privileges.</p>
    </div>
```

- [ ] **Step 6: Find and update the per-row JS render function**

Run: `grep -n "tr\.device-row\|device-tbody\|insertRow\|innerHTML" /home/skyler/network-monitoring-app/frontend/index.html` to locate the render function.

There's an existing inline `<style>` rule at the top:
```css
tr.device-row:hover td { background-color: rgba(99,102,241,0.08); }
```
Change it to:
```css
tr.device-row:hover td { background-color: rgba(94,234,212,0.06); }
```

(Changes hover tint from indigo to accent teal at low alpha.)

Then scan the render function for hard-coded Tailwind colour classes on the per-row cells: anywhere it says `text-gray-300`, `text-gray-400`, `text-gray-500`, `text-gray-600`, replace with `text-ink-body`, `text-ink-muted`, `text-ink-faint`, `text-ink-quiet` respectively. Anywhere it says `bg-gray-800` replace with `bg-surface-card`; `border-gray-800` → `border-surface-border`.

Type-badge tints (`bg-cyan-*`, `bg-amber-*`, `bg-purple-*`): keep the hue so Docker / VM / LXC are still recognizable, but desaturate by using the 300 weight on text and omitting the filled background:
- Docker: `text-accent` (teal = Docker in this palette).
- VM: `text-ink-body` with an uppercase "VM" label.
- LXC: `text-ink-muted` with "LXC" label.
- Bare-metal: `text-ink-primary` with "BM" label.
- Firewall / Switch / AP / etc.: `text-ink-body` — keep it neutral.

If a type mapping helper function exists (e.g. `typeBadge(type)` returning HTML), rewrite it once; don't scatter changes.

- [ ] **Step 7: Smoke-test**

Same procedure — confirm the table renders, hover is a subtle teal tint, row typography is Fira Code, type labels are letters in palette colours instead of filled pills.

- [ ] **Step 8: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add frontend/index.html && git commit -m "feat(ui): restyle device table to palette tokens

Surface/border/text swapped to palette tokens. Table body is Fira Code.
Type badges are letter-label + palette colour, not filled pills. Hover
tint uses accent teal at 6% alpha."
```

---

### Task 1.8: Restyle the side detail panel

**Files:**
- Modify: `frontend/index.html` (the `<aside id="panel">` block).

- [ ] **Step 1: Update the panel wrapper and border**

Use the Edit tool. Old:
```html
<aside id="panel"
  class="fixed top-0 right-0 h-full z-50 w-full sm:w-[520px] bg-gray-900 border-l border-gray-800
         shadow-2xl flex flex-col panel-enter overflow-hidden">
```
New:
```html
<aside id="panel"
  class="fixed top-0 right-0 h-full z-50 w-full sm:w-[520px] bg-surface-card border-l border-surface-border
         shadow-2xl flex flex-col panel-enter overflow-hidden">
```

- [ ] **Step 2: Update the panel header block (name, IP, MAC, vendor)**

Use the Edit tool. Old:
```html
  <div class="flex items-start justify-between gap-3 px-6 pt-6 pb-4 border-b border-gray-800 flex-shrink-0">
    <div class="min-w-0">
      <div class="flex items-center gap-2 flex-wrap">
        <span id="panel-type-badge" class="badge"></span>
        <h2 id="panel-name" class="text-base font-semibold text-gray-100 truncate"></h2>
      </div>
      <p id="panel-ip" class="text-sm text-gray-400 mt-1 font-mono"></p>
      <p id="panel-ipv6" class="text-xs text-blue-400 font-mono mt-0.5 hidden"></p>
      <p id="panel-mac" class="text-xs text-gray-600 font-mono mt-0.5"></p>
      <p id="panel-vendor" class="text-xs text-gray-500 mt-0.5"></p>
      <p id="panel-first-seen" class="text-xs text-gray-600 mt-0.5"></p>
      <p id="panel-disappearance" class="text-xs text-amber-600 mt-0.5 hidden"></p>
    </div>
    <button id="panel-close"
      class="flex-shrink-0 p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors">
```

New:
```html
  <div class="flex items-start justify-between gap-3 px-6 pt-6 pb-4 border-b border-surface-border flex-shrink-0">
    <div class="min-w-0">
      <div class="flex items-center gap-2 flex-wrap">
        <span id="panel-type-badge" class="badge"></span>
        <h2 id="panel-name" class="wordmark text-lg text-ink-primary truncate"></h2>
      </div>
      <p id="panel-ip" class="text-sm text-ink-body mt-1 mono"></p>
      <p id="panel-ipv6" class="text-xs text-accent mono mt-0.5 hidden"></p>
      <p id="panel-mac" class="text-xs text-ink-faint mono mt-0.5"></p>
      <p id="panel-vendor" class="text-xs text-ink-muted mt-0.5"></p>
      <p id="panel-first-seen" class="text-xs text-ink-faint mt-0.5"></p>
      <p id="panel-disappearance" class="text-xs text-alert mt-0.5 hidden"></p>
    </div>
    <button id="panel-close"
      class="flex-shrink-0 p-1.5 rounded-md text-ink-faint hover:text-ink-primary hover:bg-surface transition-colors">
```

- [ ] **Step 3: Update the three metadata grids (Docker, Host-network containers, Proxmox)**

For **each** of: `#docker-meta`, `#host-containers-meta`, `#proxmox-meta`:

Search: `grep -n "border-gray-800\|text-gray-500\|text-gray-400\|text-gray-300\|text-cyan-300" /home/skyler/network-monitoring-app/frontend/index.html | head -40`

Apply the same neutral-palette swap as Task 1.7 Step 6 within these three blocks. Preserve the tiny Docker-image accent — replace `text-cyan-300` with `text-accent` so the image name still stands out.

- [ ] **Step 4: Update the badge CSS rule to use palette tokens**

Locate the `.badge` rule in the top `<style>` block:
```css
    .badge        { display: inline-flex; align-items: center; padding: 2px 8px;
                    border-radius: 9999px; font-size: 0.7rem; font-weight: 600;
                    letter-spacing: 0.05em; text-transform: uppercase; white-space: nowrap; }
```

Extend with type-specific palette classes (pure CSS so the existing JS that sets `className = 'badge badge-docker'` etc. still works):
```css
    .badge              { display: inline-flex; align-items: center; padding: 2px 8px;
                          border-radius: 9999px; font-size: 0.68rem; font-weight: 600;
                          letter-spacing: 0.05em; text-transform: uppercase; white-space: nowrap;
                          border: 1px solid #262626; background: #1a1a1a; color: #b0b0b0; }
    .badge-docker       { color: #5eead4; border-color: rgba(94,234,212,0.3); }
    .badge-vm           { color: #fafafa; }
    .badge-lxc          { color: #a3a3a3; }
    .badge-bare-metal,
    .badge-firewall,
    .badge-hypervisor   { color: #fafafa; }
    .badge-alert        { color: #f87171; border-color: rgba(248,113,113,0.3); }
```

If the existing JS sets classes like `badge-docker-container`, rename to `badge-docker` (or keep the JS mapping consistent — the key is that the CSS class names and JS-emitted class names agree).

- [ ] **Step 5: Smoke-test** — click a row, confirm the side panel opens in the new palette and the metadata grids align.

- [ ] **Step 6: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add frontend/index.html && git commit -m "feat(ui): restyle side detail panel and type-badge CSS

Panel header uses Georgia for the device name, Fira Code for IP/MAC.
Metadata grids use palette tokens. Type badges become outlined chips
with palette colors instead of saturated pills."
```

---

### Task 1.9: Scrubber — sweep remaining indigo / gray-* classes

**Files:**
- Modify: `frontend/index.html`.

- [ ] **Step 1: List every remaining legacy colour class**

Run:
```bash
cd /home/skyler/network-monitoring-app && grep -oE "(indigo|gray|slate|zinc|neutral|blue|emerald|amber|cyan|purple|violet)-[0-9]{2,3}" frontend/index.html | sort -u
```

Expected output after prior tasks: a small list of residual uses (logs panel, docker image color, severity colours on log rows, emerald dot for "live"). Some **are** allowed — severity colours on syslog rows can stay (they encode information). Anything that's just chrome should be swapped.

- [ ] **Step 2: Swap chrome colours to palette tokens**

For each remaining chrome class in the output of Step 1, apply the swap conventions:
- `bg-gray-{700-900,950}` → `bg-surface` (body), `bg-surface-card` (cards), `bg-surface-alt` (alt)
- `border-gray-*` → `border-surface-border`
- `text-gray-{900..500}` / `text-slate-*` etc. → `text-ink-primary | body | muted | faint | quiet` by lightness
- `bg-indigo-*` / `text-indigo-*` → neutral (this is the common slop signal — no indigo chrome remains)
- `bg-emerald-500` on the live dot → `bg-accent` (Task 1.2 already did this; double-check)

Leave these as-is (they encode meaning, not chrome):
- Severity colours on syslog rows (`text-red-400`, `text-amber-400`, `text-sky-400` etc.) — but reconcile with palette by using `#f87171` for error instead of generic red. If the existing classes are acceptable, leave.
- Info-dense chart-axis labels if any.

- [ ] **Step 3: Re-run the grep from Step 1**

Confirm: every remaining match is an information-encoding use, not chrome. Explicitly list any that remain in the commit message.

- [ ] **Step 4: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add frontend/index.html && git commit -m "chore(ui): scrub residual gray/indigo chrome classes to palette tokens

Severity colours on syslog rows intentionally retained as information-
encoding, not chrome."
```

---

### Task 1.10: Dashboard smoke test — Checkpoint C1

**Files:** (none modified; verification only)

- [ ] **Step 1: Build and run the real app locally (or via Docker, whichever is faster)**

Run the existing stack against a real `.env` (or a placeholder, since the UI still renders with empty data):
```bash
cd /home/skyler/network-monitoring-app && docker compose up --build
```

Open `http://localhost:8000`.

- [ ] **Step 2: Walk through the checklist**

Confirm in the browser:
- [ ] Wordmark reads `netcensus` in Georgia.
- [ ] `nc` monogram is a teal letter on a near-black tile.
- [ ] Live-dot has a teal glow; "Refresh" is an outlined teal chip.
- [ ] Overview strip shows 4 cards (Devices / VLANs / Composition / Alerts).
- [ ] Composition card includes a thin stacked bar and letter-coded counts.
- [ ] Source row is a Fira-Code line of short labels with teal filled dots (or quiet rings if disabled).
- [ ] Search has a teal focus ring; Export buttons are subtle outlined chips.
- [ ] Bulk-action bar theme: only the primary action is teal-outlined.
- [ ] Table body is Fira Code; hover is a subtle teal tint.
- [ ] Click a row: side panel opens; device name is Georgia; IP/MAC are Fira Code.
- [ ] DevTools console shows no new errors.
- [ ] `prefers-reduced-motion: reduce` in DevTools → panel and overlay do not animate.

- [ ] **Step 3: A11y spot-check**

Use DevTools → Lighthouse → Accessibility.
- Contrast: Primary text on surface must be AA. `#fafafa` on `#111111` is well above AA; verify muted text (`#737373`, `#525252`) isn't used on `#111111` for important info. If it is, move that text to `#a3a3a3` or above.
- Focus rings: tab through header → search → export → table rows → side panel; confirm every focusable has a visible focus indicator.

- [ ] **Step 4: Tag Checkpoint C1**

Run:
```bash
cd /home/skyler/network-monitoring-app && git tag c1-dashboard-restyle && git log --oneline -10
```

Checkpoint C1 reached. The dashboard is now visually done. The current README still works (it just doesn't yet screenshot the new UI).

---

## Phase 2 — Demo mode (Checkpoint C2)

### Task 2.1: Inspect the `devices` and `syslogs` schema

**Files:** (read-only)

- [ ] **Step 1: Extract the exact schema the seeder must write against**

Run: `grep -n -A 40 "CREATE TABLE\|CREATE INDEX" /home/skyler/network-monitoring-app/src/database.py`

Capture the field list for `devices` (ip, mac, vendor, type, name, last_seen, first_seen, vlan, disappearance_count, manual_alias, docker_*, proxmox_*, syslog_source_ip, etc.) and for `syslogs` (timestamp, severity, facility, source_ip, message, etc.).

- [ ] **Step 2: Record the insert/update helpers that `src/demo_seed.py` should call**

Run: `grep -n "async def " /home/skyler/network-monitoring-app/src/database.py | head -40`

Pick the helpers that upsert a device and append a syslog row. The seed should call these helpers (same code path as real scans) rather than issue raw SQL — that keeps the seed in sync with schema changes automatically.

- [ ] **Step 3: No commit** — read-only step.

---

### Task 2.2: Write the failing test for `src/demo_seed.py`

**Files:**
- Create: `tests/__init__.py` (empty).
- Create: `tests/test_demo_seed.py`.
- Create: `pyproject.toml` only if the repo currently has no pytest config; otherwise skip. (Check first: `ls /home/skyler/network-monitoring-app/pyproject.toml /home/skyler/network-monitoring-app/setup.cfg 2>&1`. If both missing, create a minimal `pyproject.toml` with just the `[tool.pytest.ini_options]` stanza.)

- [ ] **Step 1: Add pytest and pytest-asyncio to requirements if missing**

Run: `grep -E "pytest" /home/skyler/network-monitoring-app/requirements.txt`

If empty, append to `requirements.txt`:
```
pytest>=8.0
pytest-asyncio>=0.23
```

- [ ] **Step 2: Create `tests/__init__.py`** (empty file).

Run: `touch /home/skyler/network-monitoring-app/tests/__init__.py`

- [ ] **Step 3: Create `tests/test_demo_seed.py`**

Content:
```python
"""Tests for the demo seeder.

The seed must be deterministic and must produce the counts specified in
the design spec (see docs/superpowers/specs/2026-04-23-netcensus-portfolio-polish-design.md §2).
"""
import os
import tempfile
import pytest

from src.demo_seed import seed_demo_db


@pytest.mark.asyncio
async def test_seed_is_deterministic():
    """Seeding the same fresh DB twice must produce identical device rows."""
    with tempfile.TemporaryDirectory() as d:
        db1 = os.path.join(d, "a.db")
        db2 = os.path.join(d, "b.db")
        counts1 = await seed_demo_db(db1)
        counts2 = await seed_demo_db(db2)
        assert counts1 == counts2


@pytest.mark.asyncio
async def test_seed_counts_match_spec():
    """The seed produces the narrative required by the spec."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "demo.db")
        counts = await seed_demo_db(db)
        # Spec §2: 6 VLANs, 2 Proxmox nodes, 8 VMs, 4 LXCs,
        #         3 Docker hosts with ~20 containers,
        #         1 firewall + 1 switch + 2 APs, 4 IoT endpoints,
        #         1 intentional device_gone alert.
        assert counts["vlans"] == 6
        assert counts["vms"] == 8
        assert counts["lxcs"] == 4
        assert 18 <= counts["containers"] <= 22
        assert counts["bare_metal"] >= 4  # firewall + switch + 2 APs
        assert counts["iot"] == 4
        assert counts["alerts"] == 1


@pytest.mark.asyncio
async def test_seed_includes_at_least_one_syslog_block_line():
    """Seed must include OPNsense filterlog BLOCK lines so the log panel isn't empty."""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "demo.db")
        counts = await seed_demo_db(db)
        assert counts["syslog_block_lines"] >= 2
```

- [ ] **Step 4: Confirm the test fails with ModuleNotFoundError**

Run: `cd /home/skyler/network-monitoring-app && source venv/bin/activate && pytest tests/test_demo_seed.py -v 2>&1 | tail -20`

Expected: `ModuleNotFoundError: No module named 'src.demo_seed'` (or pytest missing — if missing, `pip install -r requirements.txt` first).

- [ ] **Step 5: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add tests/ requirements.txt && git commit -m "test: add failing tests for src/demo_seed.py

Asserts the seed is deterministic and produces the narrative counts
required by the portfolio-polish design spec §2."
```

---

### Task 2.3: Implement `src/demo_seed.py`

**Files:**
- Create: `src/demo_seed.py`.

- [ ] **Step 1: Write the seeder**

Create `/home/skyler/network-monitoring-app/src/demo_seed.py` with:

```python
"""Demo-mode seeder.

Writes a deterministic, coherent homelab narrative into a fresh SQLite
database so the dashboard renders with realistic data for screenshots
and third-party demos. Invoked from src/main.py's lifespan when
DEMO_MODE=true.

Design ref: docs/superpowers/specs/2026-04-23-netcensus-portfolio-polish-design.md §2
"""
from __future__ import annotations

import os
import time
import random
from dataclasses import dataclass
from typing import Dict

from src.database import init_db, upsert_device, append_syslog

# Fixed seed so runs are reproducible.
_SEED = 20260423


@dataclass(frozen=True)
class DemoDevice:
    ip: str
    mac: str
    vendor: str
    type: str
    name: str
    vlan: int
    extras: Dict[str, object] | None = None


# ── Narrative ──────────────────────────────────────────────────────────────
_VLANS = {
    10: "mgmt",
    20: "servers",
    30: "lab",
    40: "iot",
    50: "guests",
    99: "dmz",
}

_BARE_METAL = [
    DemoDevice("10.30.10.1",   "ac:1f:6b:00:00:01", "Deciso",    "firewall",   "opnsense-gw",   10),
    DemoDevice("10.30.10.2",   "f0:9f:c2:00:00:02", "Ubiquiti",  "switch",     "usw-core",      10),
    DemoDevice("10.30.10.3",   "f0:9f:c2:00:00:03", "Ubiquiti",  "ap",         "uap-office",    10),
    DemoDevice("10.30.10.4",   "f0:9f:c2:00:00:04", "Ubiquiti",  "ap",         "uap-lab",       10),
]

_PROXMOX_NODES = [
    ("pve-01", "10.30.10.11", "bc:24:11:00:00:11"),
    ("pve-02", "10.30.10.12", "bc:24:11:00:00:12"),
]

_VMS = [
    # (name, vmid, node, ip, mac, vlan)
    ("grafana",        101, "pve-01", "10.30.20.11", "bc:24:11:01:01:01", 20),
    ("prometheus",     102, "pve-01", "10.30.20.12", "bc:24:11:01:01:02", 20),
    ("postgres-16",    103, "pve-01", "10.30.20.13", "bc:24:11:01:01:03", 20),
    ("gitea",          104, "pve-01", "10.30.20.14", "bc:24:11:01:01:04", 20),
    ("vaultwarden",    201, "pve-02", "10.30.20.21", "bc:24:11:02:02:01", 20),
    ("home-assistant", 202, "pve-02", "10.30.20.22", "bc:24:11:02:02:02", 20),
    ("plex",           203, "pve-02", "10.30.20.23", "bc:24:11:02:02:03", 20),
    ("pihole",         204, "pve-02", "10.30.10.24", "bc:24:11:02:02:04", 10),
]

_LXCS = [
    ("nginx-proxy",       301, "pve-01", "10.30.99.31", "bc:24:11:03:03:01", 99),
    ("cloudflared",       302, "pve-01", "10.30.99.32", "bc:24:11:03:03:02", 99),
    ("syslog-ng",         303, "pve-02", "10.30.10.33", "bc:24:11:04:04:01", 10),
    ("unifi-controller",  304, "pve-02", "10.30.10.34", "bc:24:11:04:04:02", 10),
]

_DOCKER_HOSTS = [
    ("dock-01", "10.30.20.101", "02:42:ac:11:01:00"),
    ("dock-02", "10.30.20.102", "02:42:ac:11:02:00"),
    ("dock-03", "10.30.30.103", "02:42:ac:11:03:00"),
]

_CONTAINERS = [
    # (name, image, host_index, last_octet, vlan)
    ("grafana-agent",      "grafana/agent:latest",                0, 11, 20),
    ("loki",               "grafana/loki:2.9",                    0, 12, 20),
    ("promtail",           "grafana/promtail:2.9",                0, 13, 20),
    ("cadvisor",           "gcr.io/cadvisor/cadvisor:v0.49",      0, 14, 20),
    ("node-exporter",      "quay.io/prometheus/node-exporter",    0, 15, 20),
    ("traefik",            "traefik:v3.0",                        1, 21, 20),
    ("postgres-dev",       "postgres:16",                         1, 22, 20),
    ("redis",              "redis:7",                             1, 23, 20),
    ("minio",              "minio/minio:latest",                  1, 24, 20),
    ("ollama",             "ollama/ollama:latest",                1, 25, 20),
    ("opensearch",         "opensearchproject/opensearch:2",      1, 26, 20),
    ("n8n",                "n8nio/n8n:latest",                    1, 27, 20),
    ("jellyfin",           "jellyfin/jellyfin:10",                2, 31, 30),
    ("uptime-kuma",        "louislam/uptime-kuma:1",              2, 32, 30),
    ("code-server",        "codercom/code-server:latest",         2, 33, 30),
    ("portainer",          "portainer/portainer-ce:2.20",         2, 34, 30),
    ("authentik-server",   "ghcr.io/goauthentik/server:2025.6",   2, 35, 30),
    ("authentik-worker",   "ghcr.io/goauthentik/server:2025.6",   2, 36, 30),
    ("watchtower",         "containrrr/watchtower",               2, 37, 30),
    ("tailscale",          "tailscale/tailscale:latest",          2, 38, 30),
]

_IOT = [
    DemoDevice("10.30.40.41", "00:80:77:00:00:01", "Brother Industries", "printer",     "brother-hl-mfp", 40),
    DemoDevice("10.30.40.42", "b8:27:eb:00:00:02", "Raspberry Pi",        "iot",         "camera-front",   40),
    DemoDevice("10.30.40.43", "b8:27:eb:00:00:03", "Raspberry Pi",        "iot",         "camera-back",    40),
    DemoDevice("10.30.40.44", "ec:fa:bc:00:00:04", "Shelly",              "iot",         "plug-office",    40),
]

# ── Syslog narrative ───────────────────────────────────────────────────────
_FILTERLOG_BLOCK_LINES = [
    # (timestamp_offset_sec, source_ip, csv_message)
    (-60, "10.30.10.1",
     "filterlog: 100,,,0,igb0,match,block,in,4,0x0,,63,54321,0,none,6,tcp,44,"
     "203.0.113.44,10.30.20.11,33012,443,0,S,0,,8192,,mss"),
    (-32, "10.30.10.1",
     "filterlog: 101,,,0,igb1,match,block,in,4,0x0,,63,54322,0,none,17,udp,76,"
     "198.51.100.12,10.30.40.41,5353,5353,56"),
]

_INFO_SYSLOG = [
    (-12, "10.30.20.11", "info", "grafana", "Starting Grafana, version=11.0.0"),
    (-8,  "10.30.20.13", "info", "postgres", "database system is ready to accept connections"),
    (-5,  "10.30.10.2",  "notice", "vyatta", "Port 12 link up at 1 Gbps full-duplex"),
    (-2,  "10.30.10.1",  "info", "dhcpd", "DHCPACK on 10.30.40.42 to b8:27:eb:00:00:02 via igb2"),
]


async def seed_demo_db(db_path: str) -> Dict[str, int]:
    """Populate a fresh SQLite DB with the demo narrative.

    Returns a counts dict the tests and logs verify against.
    """
    # Always start fresh.
    if os.path.exists(db_path):
        os.remove(db_path)

    os.environ["DB_PATH"] = db_path
    await init_db()

    rng = random.Random(_SEED)
    now = int(time.time())
    counts = {k: 0 for k in (
        "vlans", "bare_metal", "vms", "lxcs", "containers",
        "iot", "alerts", "syslog_block_lines",
    )}
    counts["vlans"] = len(_VLANS)

    # Bare metal
    for d in _BARE_METAL:
        await upsert_device(
            ip=d.ip, mac=d.mac, vendor=d.vendor, type=d.type,
            name=d.name, vlan=d.vlan, last_seen=now,
        )
        counts["bare_metal"] += 1

    # Proxmox hypervisors (as bare-metal rows with type=hypervisor)
    for (name, ip, mac) in _PROXMOX_NODES:
        await upsert_device(ip=ip, mac=mac, vendor="Supermicro", type="hypervisor",
                            name=name, vlan=10, last_seen=now)
        counts["bare_metal"] += 1

    # VMs
    for (name, vmid, node, ip, mac, vlan) in _VMS:
        await upsert_device(
            ip=ip, mac=mac, vendor="QEMU Virtual", type="vm", name=name,
            vlan=vlan, last_seen=now,
            extras={"proxmox_node": node, "proxmox_vmid": vmid, "proxmox_status": "running"},
        )
        counts["vms"] += 1

    # LXCs
    for (name, vmid, node, ip, mac, vlan) in _LXCS:
        await upsert_device(
            ip=ip, mac=mac, vendor="Proxmox LXC", type="lxc", name=name,
            vlan=vlan, last_seen=now,
            extras={"proxmox_node": node, "proxmox_vmid": vmid, "proxmox_status": "running"},
        )
        counts["lxcs"] += 1

    # Docker hosts
    for (name, ip, mac) in _DOCKER_HOSTS:
        await upsert_device(ip=ip, mac=mac, vendor="Intel", type="bare-metal",
                            name=name, vlan=20, last_seen=now)
        counts["bare_metal"] += 1

    # Containers (type=docker-container, attributed to a docker host)
    for (name, image, host_idx, last_octet, vlan) in _CONTAINERS:
        host_name, host_ip, _ = _DOCKER_HOSTS[host_idx]
        ip = f"172.{20+vlan//10}.{host_idx}.{last_octet}"
        mac = f"02:42:ac:{host_idx:02x}:{last_octet:02x}:01"
        await upsert_device(
            ip=ip, mac=mac, vendor="Docker", type="docker-container",
            name=name, vlan=vlan, last_seen=now,
            extras={"docker_image": image, "docker_host": host_name,
                    "docker_status": "running"},
        )
        counts["containers"] += 1

    # IoT
    for d in _IOT:
        await upsert_device(ip=d.ip, mac=d.mac, vendor=d.vendor, type=d.type,
                            name=d.name, vlan=d.vlan, last_seen=now)
        counts["iot"] += 1

    # Intentional device_gone alert on VLAN 99
    await upsert_device(
        ip="10.30.99.99", mac="00:00:00:00:de:ad",
        vendor="Unknown", type="bare-metal", name="staging-vm-decommissioned",
        vlan=99, last_seen=now - 4 * 300,  # 4 intervals missed, above default threshold of 3
        extras={"disappearance_count": 5},
    )
    counts["alerts"] = 1

    # Syslog narrative
    for (offset, src_ip, csv) in _FILTERLOG_BLOCK_LINES:
        await append_syslog(source_ip=src_ip, severity="warning", facility="local0",
                            timestamp=now + offset,
                            message=csv)
        counts["syslog_block_lines"] += 1

    for (offset, src_ip, sev, prog, msg) in _INFO_SYSLOG:
        await append_syslog(source_ip=src_ip, severity=sev, facility="daemon",
                            timestamp=now + offset,
                            message=f"{prog}: {msg}")

    # Unused, but keeps rng import stable for future randomized content
    _ = rng.random()

    return counts
```

**IMPORTANT:** Before submitting, verify the `upsert_device` and `append_syslog` signatures match what `src/database.py` actually exposes. If the real signatures differ (different parameter names, returning awaitable Connection vs direct call, etc.), adjust the seeder and the test to match. The shape above is the target; the database module is the source of truth.

- [ ] **Step 2: Run the tests**

Run: `cd /home/skyler/network-monitoring-app && source venv/bin/activate && pytest tests/test_demo_seed.py -v 2>&1 | tail -30`

Expected: all three tests pass.

If tests fail with signature mismatches, fix the seeder (not the tests — the tests encode the spec).

- [ ] **Step 3: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add src/demo_seed.py && git commit -m "feat(demo): add deterministic demo seeder

Populates a fresh SQLite DB with one coherent homelab narrative:
6 VLANs, 2 Proxmox nodes, 8 VMs, 4 LXCs, 3 Docker hosts, 20 containers,
4 IoT endpoints, one intentional device_gone alert on VLAN 99, and
a handful of seeded syslog entries including OPNsense filterlog BLOCK
lines. Deterministic via a fixed random seed."
```

---

### Task 2.4: Wire `DEMO_MODE` into `src/main.py` lifespan

**Files:**
- Modify: `src/main.py` (the `lifespan` function, currently starting at line 401).

- [ ] **Step 1: Read the current lifespan**

Run: `sed -n '395,445p' /home/skyler/network-monitoring-app/src/main.py`

Expected: the lifespan we saw earlier (init_db → syslog → scan_task → yield → cancel in reverse).

- [ ] **Step 2: Branch the lifespan on DEMO_MODE**

Use the Edit tool. Old:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Database
    await init_db()
    logger.info("Database initialised at %s", os.path.abspath(
        os.environ.get("DB_PATH", "network_monitor.db")
    ))

    # 2. Syslog UDP server
    syslog_transport = None
    try:
        syslog_transport = await start_syslog_server(SYSLOG_HOST, SYSLOG_PORT)
    except PermissionError:
        logger.error(
            "Cannot bind UDP port %d — re-run with sudo or set "
            "SYSLOG_PORT to a value > 1023 for unprivileged testing.",
            SYSLOG_PORT,
        )
    except OSError as exc:
        logger.error("Syslog server failed to start: %s", exc)

    # 3. Background ARP scan loop
    scan_task = asyncio.create_task(_scan_loop())

    try:
        yield
    finally:
        # Shut down in reverse order
        scan_task.cancel()
        try:
            await scan_task
        except asyncio.CancelledError:
```

New:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    demo_mode = os.environ.get("DEMO_MODE", "").lower() in ("1", "true", "yes")

    if demo_mode:
        # Demo path: bypass scanners and syslog; populate DB once and idle.
        from src.demo_seed import seed_demo_db
        db_path = os.environ.get("DB_PATH", "network_monitor.db")
        counts = await seed_demo_db(db_path)
        logger.info("DEMO_MODE active: seeded %s", counts)
        try:
            yield
        finally:
            logger.info("DEMO_MODE shutdown: nothing to clean up")
        return

    # 1. Database
    await init_db()
    logger.info("Database initialised at %s", os.path.abspath(
        os.environ.get("DB_PATH", "network_monitor.db")
    ))

    # 2. Syslog UDP server
    syslog_transport = None
    try:
        syslog_transport = await start_syslog_server(SYSLOG_HOST, SYSLOG_PORT)
    except PermissionError:
        logger.error(
            "Cannot bind UDP port %d — re-run with sudo or set "
            "SYSLOG_PORT to a value > 1023 for unprivileged testing.",
            SYSLOG_PORT,
        )
    except OSError as exc:
        logger.error("Syslog server failed to start: %s", exc)

    # 3. Background ARP scan loop
    scan_task = asyncio.create_task(_scan_loop())

    try:
        yield
    finally:
        # Shut down in reverse order
        scan_task.cancel()
        try:
            await scan_task
        except asyncio.CancelledError:
```

- [ ] **Step 3: Smoke-test locally**

Run:
```bash
cd /home/skyler/network-monitoring-app && source venv/bin/activate && \
  DEMO_MODE=true DB_PATH=/tmp/netcensus-demo.db \
  python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8080 --log-level info 2>&1 | head -20
```

In another terminal:
```bash
curl -s http://localhost:8080/api/devices | head -c 500
```

Expected: JSON with the seeded devices (firewall, switch, VMs, containers, etc.). Kill the uvicorn process.

- [ ] **Step 4: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add src/main.py && git commit -m "feat(demo): DEMO_MODE env var bypasses scanners and seeds DB

When DEMO_MODE=true, lifespan skips the syslog bind and the scan loop,
and calls seed_demo_db once. Real scanner path is untouched."
```

---

### Task 2.5: Create `docker-compose.demo.yml`

**Files:**
- Create: `docker-compose.demo.yml`.

- [ ] **Step 1: Write the demo compose file**

Create `/home/skyler/network-monitoring-app/docker-compose.demo.yml`:

```yaml
# Demo instance — seeded with a coherent homelab narrative.
# No network scanning, no syslog binding, no OPNsense/Proxmox/Docker API calls.
# Third parties can run this with zero config:
#   docker compose -f docker-compose.demo.yml up
# Then open http://localhost:8080

services:
  netcensus-demo:
    build: .
    container_name: netcensus-demo
    restart: unless-stopped

    # Publish to 8080 so it can run alongside a real instance on 8000.
    ports:
      - "8080:8000"

    # Keep DB inside the container — it's a seed, not persistent state.
    environment:
      DEMO_MODE: "true"
      DB_PATH: "/tmp/netcensus-demo.db"

    # Demo has no state worth persisting.
    # No volumes, no cap_add, no host networking.
```

- [ ] **Step 2: Smoke-test on a clean Docker state**

Run:
```bash
cd /home/skyler/network-monitoring-app && docker compose -f docker-compose.demo.yml down -v 2>&1 || true
docker compose -f docker-compose.demo.yml up --build -d
sleep 5
curl -s http://localhost:8080/api/devices | python3 -c "import sys, json; d = json.load(sys.stdin); print(f'devices: {len(d)}')"
```

Expected: `devices: 47` (or whatever count matches the seed). Non-zero and > 40 is a pass.

Then:
```bash
docker compose -f docker-compose.demo.yml logs netcensus-demo | grep DEMO_MODE
```
Expected: a line containing `DEMO_MODE active: seeded {...}`.

Stop:
```bash
docker compose -f docker-compose.demo.yml down
```

- [ ] **Step 3: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add docker-compose.demo.yml && git commit -m "feat(demo): docker-compose.demo.yml for one-command seeded instance

Publishes on host port 8080 so it can run alongside a real netcensus
on 8000. No volumes, no env file, no cap_add — runs anywhere Docker
runs."
```

---

### Task 2.6: Add `DEMO=1` shortcut to `start.sh`

**Files:**
- Modify: `start.sh`.

- [ ] **Step 1: Read current start.sh**

Run: `cat /home/skyler/network-monitoring-app/start.sh`

- [ ] **Step 2: Add a DEMO branch at the top**

Use the Edit tool. Prepend immediately after the existing shebang/header. Old (the top of the file, first few lines):
```bash
#!/bin/bash
```

New:
```bash
#!/bin/bash

# DEMO=1 shortcut: bypass scanners, seed the DB, run unprivileged on port 8080.
if [ "${DEMO:-}" = "1" ]; then
  export DEMO_MODE=true
  export DB_PATH="${DB_PATH:-/tmp/netcensus-demo.db}"
  export PORT="${PORT:-8080}"
  # No sudo needed — no UDP 514 bind in demo mode.
  exec python3 -m uvicorn src.main:app --host 0.0.0.0 --port "${PORT}" --log-level info
fi
```

(If `start.sh` already has non-trivial contents between the shebang and the main body, insert this block immediately after the shebang and any leading comments.)

- [ ] **Step 3: Verify it runs**

Run:
```bash
cd /home/skyler/network-monitoring-app && source venv/bin/activate && DEMO=1 timeout 6 ./start.sh 2>&1 | head -10
```
Expected: uvicorn startup logs showing `DEMO_MODE active: seeded {...}`.

- [ ] **Step 4: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add start.sh && git commit -m "feat(demo): DEMO=1 shortcut in start.sh for bare-metal demo runs"
```

---

### Task 2.7: Checkpoint C2 verification

**Files:** (none modified; verification only)

- [ ] **Step 1: Run the demo on a "clean" simulation of a third-party machine**

Use a fresh worktree or a clean clone:
```bash
cd /tmp && rm -rf /tmp/netcensus-smoke && \
  git clone /home/skyler/network-monitoring-app /tmp/netcensus-smoke && \
  cd /tmp/netcensus-smoke && \
  docker compose -f docker-compose.demo.yml up --build -d
sleep 8
curl -sS http://localhost:8080/ | head -c 300
curl -sS http://localhost:8080/api/devices | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
```

Expected: HTML landing, device count ~47.

- [ ] **Step 2: Open in a browser, walk the dashboard checklist again**

Open `http://localhost:8080`. Confirm the same 10 visual bullets from Task 1.10 Step 2. Confirm the overview Alerts card shows `1` (the intentional `device_gone`). Confirm the syslog panel has at least 2 filterlog BLOCK lines.

- [ ] **Step 3: Tear down and tag**

```bash
cd /tmp/netcensus-smoke && docker compose -f docker-compose.demo.yml down -v
cd /home/skyler/network-monitoring-app && git tag c2-demo-mode
```

Checkpoint C2 reached. Third parties can now run the dashboard in one command; screenshots are reproducible.

---

## Phase 3 — Screenshots and SVG diagrams

### Task 3.1: Capture the dashboard screenshot

**Files:**
- Create: `docs/images/dashboard.png`.

- [ ] **Step 1: Start the demo**

```bash
cd /home/skyler/network-monitoring-app && docker compose -f docker-compose.demo.yml up --build -d && sleep 6
```

- [ ] **Step 2: Take a high-res screenshot of the dashboard**

Open `http://localhost:8080` in a browser at 1440×900 (DevTools → Device Toolbar → Responsive → 1440 × 900). Full-page PNG capture.

Use either:
- Firefox: right-click → "Take Screenshot" → "Save full page"
- Chromium: DevTools → three-dot menu → "Capture full-size screenshot"

Save to `/home/skyler/network-monitoring-app/docs/images/dashboard.png`.

Constraints:
- Width = 1440 px (retina-display friendly, fits in GitHub's README column).
- File size < 800 KB. If larger, run `pngquant --quality=65-85 --output docs/images/dashboard.png --force docs/images/dashboard.png` (install via `sudo apt install pngquant` if missing).

- [ ] **Step 3: Verify contents**

Open the PNG and confirm:
- Wordmark reads `netcensus`.
- Overview strip shows `Devices 47` (or whatever count), `VLANs 6`, Composition bar visible, `Alerts 1`.
- At least one row shows "4h · gone" in the Last-Seen column.
- Source row shows teal dots, no hollow rings (all sources "healthy" in demo mode because the seed doesn't simulate health).

If the Alerts card shows `0`, the intentional `device_gone` row didn't take effect — check that the seeder's `disappearance_count` and stale `last_seen` are being honored by the aggregation logic.

- [ ] **Step 4: Tear down demo, commit**

```bash
cd /home/skyler/network-monitoring-app && docker compose -f docker-compose.demo.yml down
git add docs/images/dashboard.png && git commit -m "docs: add dashboard screenshot from DEMO_MODE seed"
```

---

### Task 3.2: Create the architecture SVG

**Files:**
- Create: `docs/images/architecture.svg`.

- [ ] **Step 1: Write the SVG**

Create `/home/skyler/network-monitoring-app/docs/images/architecture.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 360" role="img" aria-label="netcensus architecture: data sources feed the scanner loop and syslog receiver, which write to SQLite and expose FastAPI endpoints for the dashboard and webhooks.">
  <defs>
    <style>
      .bg      { fill: #111111; }
      .card    { fill: #1a1a1a; stroke: #262626; stroke-width: 1; rx: 6; ry: 6; }
      .app     { fill: #1c1c1c; stroke: #5eead4; stroke-width: 1; rx: 6; ry: 6; }
      .label   { font: 600 12px 'Fira Code', 'Courier New', monospace; fill: #fafafa; }
      .sub     { font: 400 10px system-ui, -apple-system, sans-serif; fill: #a3a3a3; }
      .title   { font: 400 16px Georgia, serif; fill: #fafafa; }
      .axis    { font: 600 9px system-ui, sans-serif; fill: #737373; letter-spacing: 0.12em; text-transform: uppercase; }
      .arrow   { stroke: #5eead4; stroke-width: 1.5; fill: none; marker-end: url(#arrow); }
      .arrow-q { stroke: #525252; stroke-width: 1;   fill: none; marker-end: url(#arrow-q); stroke-dasharray: 3 3; }
    </style>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="#5eead4"/>
    </marker>
    <marker id="arrow-q" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="#525252"/>
    </marker>
  </defs>

  <rect class="bg" width="900" height="360"/>

  <text x="30" y="34" class="title">netcensus architecture</text>
  <text x="30" y="54" class="sub">Three authoritative sources · one merged view · no raw sockets</text>

  <text x="60"  y="100" class="axis">Sources</text>
  <text x="410" y="100" class="axis">Application</text>
  <text x="740" y="100" class="axis">Surfaces</text>

  <!-- Sources -->
  <g>
    <rect class="card" x="40" y="115" width="220" height="40"/>
    <text x="56" y="140" class="label">OPNsense</text>
    <text x="138" y="140" class="sub">ARP / NDP / DHCP</text>

    <rect class="card" x="40" y="165" width="220" height="40"/>
    <text x="56" y="190" class="label">Proxmox</text>
    <text x="138" y="190" class="sub">VM / LXC inventory</text>

    <rect class="card" x="40" y="215" width="220" height="40"/>
    <text x="56" y="240" class="label">Docker</text>
    <text x="138" y="240" class="sub">Engine API per host</text>

    <rect class="card" x="40" y="265" width="220" height="40"/>
    <text x="56" y="290" class="label">nmap · SNMP</text>
    <text x="138" y="290" class="sub">optional supplemental</text>
  </g>

  <!-- App box -->
  <g>
    <rect class="app" x="320" y="115" width="260" height="190"/>
    <text x="336" y="140" class="label">Scanner loop</text>
    <text x="336" y="156" class="sub">async, concurrent, 300s cycle</text>

    <line x1="336" y1="170" x2="564" y2="170" stroke="#262626" stroke-width="1"/>

    <text x="336" y="192" class="label">Syslog receiver</text>
    <text x="336" y="208" class="sub">UDP :514, filterlog parser</text>

    <line x1="336" y1="222" x2="564" y2="222" stroke="#262626" stroke-width="1"/>

    <text x="336" y="244" class="label">SQLite (aiosqlite)</text>
    <text x="336" y="260" class="sub">devices + syslogs + alerts</text>

    <line x1="336" y1="274" x2="564" y2="274" stroke="#262626" stroke-width="1"/>

    <text x="336" y="294" class="label">FastAPI · asyncio lifespan</text>
  </g>

  <!-- Surfaces -->
  <g>
    <rect class="card" x="640" y="130" width="220" height="40"/>
    <text x="656" y="155" class="label">Web dashboard</text>

    <rect class="card" x="640" y="180" width="220" height="40"/>
    <text x="656" y="205" class="label">REST API · /api/*</text>

    <rect class="card" x="640" y="230" width="220" height="40"/>
    <text x="656" y="255" class="label">Webhook alerts</text>
  </g>

  <!-- Arrows: sources → app -->
  <path class="arrow" d="M 260 135 H 320"/>
  <path class="arrow" d="M 260 185 H 320"/>
  <path class="arrow" d="M 260 235 H 320"/>
  <path class="arrow-q" d="M 260 285 H 320"/>

  <!-- Arrows: app → surfaces -->
  <path class="arrow" d="M 580 150 H 640"/>
  <path class="arrow" d="M 580 200 H 640"/>
  <path class="arrow" d="M 580 250 H 640"/>
</svg>
```

- [ ] **Step 2: Open in a browser, confirm it renders**

Run: `xdg-open /home/skyler/network-monitoring-app/docs/images/architecture.svg 2>/dev/null || firefox /home/skyler/network-monitoring-app/docs/images/architecture.svg &`

Confirm: all cards are visible, arrows connect, text is readable.

- [ ] **Step 3: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add docs/images/architecture.svg && git commit -m "docs: inline architecture SVG for README"
```

---

### Task 3.3: Create the before/after VLAN SVG

**Files:**
- Create: `docs/images/vlan-before-after.svg`.

- [ ] **Step 1: Write the SVG**

Create `/home/skyler/network-monitoring-app/docs/images/vlan-before-after.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 320" role="img" aria-label="Before: an ARP scanner on one VLAN cannot reach devices on other VLANs. After: netcensus queries OPNsense, Proxmox, and Docker, which all already see every VLAN.">
  <defs>
    <style>
      .bg      { fill: #111111; }
      .panel   { fill: #1a1a1a; stroke: #262626; stroke-width: 1; rx: 8; ry: 8; }
      .vlan    { fill: #1c1c1c; stroke: #262626; stroke-width: 1; rx: 4; ry: 4; }
      .label   { font: 600 11px 'Fira Code','Courier New',monospace; fill: #fafafa; }
      .sub     { font: 400 10px system-ui, -apple-system, sans-serif; fill: #a3a3a3; }
      .axis    { font: 600 9px system-ui,sans-serif; fill: #737373; letter-spacing: 0.12em; text-transform: uppercase; }
      .title   { font: 400 16px Georgia, serif; fill: #fafafa; }
      .good    { stroke: #5eead4; stroke-width: 1.5; fill: none; marker-end: url(#good); }
      .bad     { stroke: #f87171; stroke-width: 1.5; fill: none; marker-end: url(#bad); }
      .block   { fill: #f87171; font: 700 16px system-ui,sans-serif; }
    </style>
    <marker id="good" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="#5eead4"/>
    </marker>
    <marker id="bad" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="#f87171"/>
    </marker>
  </defs>

  <rect class="bg" width="900" height="320"/>
  <text x="30" y="34" class="title">The VLAN problem — and the way around it</text>

  <!-- BEFORE panel -->
  <g>
    <rect class="panel" x="30" y="60" width="400" height="240"/>
    <text x="50" y="84" class="axis">Before · ARP broadcast</text>

    <rect class="vlan" x="50"  y="100" width="100" height="36"/>
    <text x="60" y="123" class="label">scanner</text>

    <rect class="vlan" x="280" y="100" width="120" height="36"/>
    <text x="294" y="123" class="label">VLAN 10</text>
    <rect class="vlan" x="280" y="150" width="120" height="36"/>
    <text x="294" y="173" class="label">VLAN 20</text>
    <rect class="vlan" x="280" y="200" width="120" height="36"/>
    <text x="294" y="223" class="label">VLAN 30</text>
    <rect class="vlan" x="280" y="250" width="120" height="36"/>
    <text x="294" y="273" class="label">VLAN 99</text>

    <!-- Crossed-out arrows to other VLANs -->
    <path class="bad" d="M 150 118 C 210 118, 230 168, 280 168"/>
    <path class="bad" d="M 150 118 C 210 118, 230 218, 280 218"/>
    <path class="bad" d="M 150 118 C 210 118, 230 268, 280 268"/>
    <text x="215" y="174" class="block">×</text>
    <text x="215" y="224" class="block">×</text>
    <text x="215" y="274" class="block">×</text>
    <path class="good" d="M 150 118 H 280"/>
  </g>

  <!-- AFTER panel -->
  <g>
    <rect class="panel" x="470" y="60" width="400" height="240"/>
    <text x="490" y="84" class="axis">After · API-driven</text>

    <rect class="vlan" x="490" y="100" width="140" height="32"/>
    <text x="504" y="121" class="label">OPNsense API</text>

    <rect class="vlan" x="490" y="142" width="140" height="32"/>
    <text x="504" y="163" class="label">Proxmox API</text>

    <rect class="vlan" x="490" y="184" width="140" height="32"/>
    <text x="504" y="205" class="label">Docker API</text>

    <rect class="vlan" x="720" y="140" width="130" height="36"/>
    <text x="736" y="163" class="label">netcensus</text>

    <path class="good" d="M 630 116 C 680 116, 700 158, 720 158"/>
    <path class="good" d="M 630 158 H 720"/>
    <path class="good" d="M 630 200 C 680 200, 700 158, 720 158"/>

    <text x="490" y="260" class="sub">Every VLAN is visible — the router / hypervisor / daemons</text>
    <text x="490" y="276" class="sub">already see every segment. One auth'd HTTPS call each.</text>
  </g>
</svg>
```

- [ ] **Step 2: Open in browser, confirm it renders** — same procedure as Task 3.2 Step 2.

- [ ] **Step 3: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add docs/images/vlan-before-after.svg && git commit -m "docs: before/after VLAN SVG for README"
```

---

### Task 3.4: Verify inline SVG rendering on GitHub

**Files:** (read-only verification)

- [ ] **Step 1: Push to a throwaway branch and view in GitHub's renderer**

Run:
```bash
cd /home/skyler/network-monitoring-app && git checkout -b svg-render-check && git push origin svg-render-check 2>&1 | tail -5
```

- [ ] **Step 2: Create a temporary markdown stub that references the SVGs**

Create `/home/skyler/network-monitoring-app/docs/images/SVG_CHECK.md`:

```markdown
# SVG rendering check

![architecture](./architecture.svg)
![before-after](./vlan-before-after.svg)
```

Commit and push:
```bash
cd /home/skyler/network-monitoring-app && git add docs/images/SVG_CHECK.md && git commit -m "chore: temp SVG rendering check (to be removed)" && git push
```

Open the file on GitHub (`https://github.com/moshthesubnet/netcensus/blob/svg-render-check/docs/images/SVG_CHECK.md`). Confirm both SVGs render with all text and colors visible.

- [ ] **Step 3: If GitHub strips CSS**

GitHub's markdown renderer runs SVGs through a sanitizer that preserves `<style>` inside `<svg>` in most cases but can strip complex rules. If text is invisible:

Option A (simplest): inline each `fill=`/`stroke=` as element attributes instead of relying on CSS classes. Rewrite both SVGs to set `fill="#fafafa"` directly on `<text>` elements, etc.

Option B: export the SVG to PNG and link to the PNG in the README instead. Use Inkscape: `inkscape docs/images/architecture.svg --export-filename=docs/images/architecture.png --export-dpi=150`.

Decide in the moment based on rendering. Whichever fallback is used, repeat the push-and-view check before declaring the diagram done.

- [ ] **Step 4: Clean up**

```bash
cd /home/skyler/network-monitoring-app && git checkout main && git branch -D svg-render-check
git push origin --delete svg-render-check 2>&1 | tail -3
# Remove the throwaway markdown stub from main (it only existed on the branch, so nothing to do on main).
```

(If you pushed `SVG_CHECK.md` to main by accident, `git rm docs/images/SVG_CHECK.md && git commit -m "chore: remove SVG check stub"`.)

---

## Phase 4 — README rewrite

### Task 4.1: Back up the current README and write the new one

**Files:**
- Modify: `README.md` (full rewrite).
- Create: `docs/_archive/old-README-2026-04.md` (captures the pre-rewrite version so no content is lost).

- [ ] **Step 1: Stash the old README**

Run:
```bash
cd /home/skyler/network-monitoring-app && mkdir -p docs/_archive && cp README.md docs/_archive/old-README-2026-04.md
```

- [ ] **Step 2: Write the new README**

Overwrite `/home/skyler/network-monitoring-app/README.md`:

```markdown
<h1>netcensus</h1>

Cross-VLAN homelab device inventory — every bare-metal host, VM, LXC, and container in one view. Queries OPNsense, Proxmox, and Docker instead of broadcasting, so no raw sockets and no per-segment scanners.

**Try it in one command** (no config, no credentials):

```bash
docker compose -f docker-compose.demo.yml up
```

Then open <http://localhost:8080>.

---

## The problem

Standard network scanners rely on layer-2 ARP broadcasts. A process runs on a host, sends ARP requests, and maps replies to IP / MAC pairs. In a segmented network, this has a fundamental flaw: **ARP does not cross VLAN boundaries**. A scanner running on VLAN 30 is blind to VLANs 10, 20, 99. The usual workarounds — one scanner per VLAN, promiscuous-mode capture, flooding every segment — all need raw sockets, root, or brittle host-level configuration. None of them scale cleanly to a homelab with 5+ VLANs, dozens of VMs, and multiple Docker hosts.

Layer-2 also can't answer *is this IP a VM or a bare-metal host? Which Proxmox node owns it? What containers share a host's network stack?*

![Why ARP fails — and the way around it](docs/images/vlan-before-after.svg)

## The approach

- **OPNsense** as the edge router sees every VLAN it routes — its API returns the global ARP and NDP tables in one authenticated call.
- **Proxmox** knows every VM and LXC by MAC, node, and status before a packet hits the wire.
- **Docker Engine API** reports running containers with their virtual MACs and bridge IPs.

Query all three concurrently each cycle, merge into one SQLite-backed device registry, and you have every endpoint on the network — no raw sockets, no per-VLAN probes, no root required for the core discovery path.

![netcensus architecture](docs/images/architecture.svg)

## Dashboard

![netcensus dashboard](docs/images/dashboard.png)

*The demo seed above: 6 VLANs, 47 devices, one intentional `device_gone` alert on VLAN 99.*

## Feature highlights

- **Cross-VLAN discovery via OPNsense** — one authenticated call covers every VLAN the router is aware of.
- **Proxmox VM and LXC inventory** — per-node concurrent polling, QEMU Guest Agent IP fallback when ARP hasn't resolved yet, LXC `/interfaces` fallback, stopped guests tracked too.
- **Distributed Docker mapping** — multiple Docker Engine TCP sockets queried in parallel; host-network containers correctly attributed to the daemon host's ARP entry.
- **Automatic hostnames via OPNsense DHCP** — active leases populate names on discovery; manual aliases always win.
- **Integrated real-time syslog receiver** — async UDP on port 514, parses OPNsense `filterlog` CSV into human-readable rule summaries, links logs to their source device.
- **Optional supplemental scanning (nmap + SNMP)** — covers subnets not managed by OPNsense; SNMP walks managed-switch ARP caches.
- **Disappearance tracking and webhook alerts** — `device_gone` and `device_discovered` events POST to any HTTP endpoint.

Deeper technical detail in **[ARCHITECTURE.md](./ARCHITECTURE.md)**.

## Try it

**Demo (no infrastructure required):**

```bash
docker compose -f docker-compose.demo.yml up
# Dashboard: http://localhost:8080
```

The demo bypasses the scanner and syslog server and populates a fresh SQLite DB with a deterministic seeded homelab.

**Real usage:**

```bash
git clone https://github.com/moshthesubnet/netcensus.git
cd netcensus
cp .env.example .env
# Fill in OPNsense / Proxmox / Docker credentials
docker compose up -d
# Dashboard: http://<host-ip>:8000
# Syslog:    UDP <host-ip>:514
```

Bare-metal install (Python 3.12+): `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && sudo ./start.sh`. Root is required only to bind UDP 514.

## Stack

Python 3.12 · FastAPI · asyncio · aiosqlite · Tailwind (CDN). No build step.

---

Skyler King · [moshthesubnet.com](https://moshthesubnet.com) · MIT License · See [ARCHITECTURE.md](./ARCHITECTURE.md) for the deep dive.
```

- [ ] **Step 3: Validate length and slop-guardrails**

Run:
```bash
cd /home/skyler/network-monitoring-app && wc -w README.md
```
Expected: between 450 and 900 words (the README intentionally shrunk; if > 900, trim feature bullets).

Scan for banned AI-sounding phrases:
```bash
grep -iE "seamless|lightning.fast|powerful platform|robust|leverag|state.of.the.art|cutting.edge|ground.breaking" README.md
```
Expected: empty.

Confirm no emoji headings:
```bash
grep -P "^#+.*[\x{1F000}-\x{1FFFF}\x{2600}-\x{27BF}]" README.md
```
Expected: empty.

- [ ] **Step 4: Preview the rendering**

Push to a throwaway branch and view on GitHub, or use `grip` if installed: `pip install grip && grip README.md`. Confirm images render inline at reasonable sizes.

- [ ] **Step 5: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add README.md docs/_archive/old-README-2026-04.md && git commit -m "docs: rewrite README as a case-study-style landing page

Hero with one-command demo CTA. Problem/approach narrative with an
inline VLAN before/after SVG and an architecture SVG. Dashboard
screenshot from DEMO_MODE. Feature bullets link to ARCHITECTURE.md.
Pre-rewrite README archived at docs/_archive/."
```

---

## Phase 5 — ARCHITECTURE.md rewrite (Checkpoint C3)

### Task 5.1: Rename `PROJECT_SUMMARY.md` → `ARCHITECTURE.md`

**Files:**
- Rename: `PROJECT_SUMMARY.md` → `ARCHITECTURE.md`.

- [ ] **Step 1: git mv**

Run:
```bash
cd /home/skyler/network-monitoring-app && git mv PROJECT_SUMMARY.md ARCHITECTURE.md
```

- [ ] **Step 2: Update any repo-internal references**

Run: `grep -rn "PROJECT_SUMMARY" /home/skyler/network-monitoring-app --include="*.md" --include="*.yml" --include="*.py" --include="*.sh" 2>/dev/null`

For each hit: replace `PROJECT_SUMMARY.md` → `ARCHITECTURE.md`.

- [ ] **Step 3: Commit the rename alone**

```bash
cd /home/skyler/network-monitoring-app && git add -A && git commit -m "docs: rename PROJECT_SUMMARY.md -> ARCHITECTURE.md"
```

(Rename-then-rewrite in two commits preserves git history tracking through the rename.)

---

### Task 5.2: Restructure ARCHITECTURE.md as a case-study

**Files:**
- Modify: `ARCHITECTURE.md` (trim + restructure, keeping the raw technical content).

- [ ] **Step 1: Read the current file and identify what to keep vs. cut**

Run: `wc -c /home/skyler/network-monitoring-app/ARCHITECTURE.md`
Expected: ~28000 bytes.

Open the file. Identify:
- **Keep:** problem statement, architecture explanation, per-source descriptions, disappearance/alert flow, SQLite schema choice justification.
- **Cut / compress:** any section that duplicates the new README word-for-word, any "we might in the future" hedges, any "as discussed above" references, any bullet list longer than 6 items.

- [ ] **Step 2: Rewrite to this skeleton**

Overwrite `/home/skyler/network-monitoring-app/ARCHITECTURE.md` with the case-study structure below. The writer fills in the body from the retained content of the old file — no inventing new claims.

```markdown
# netcensus — architecture

*A unified view of every device on a segmented homelab network — bare metal, VMs, LXCs, and containers — discovered without raw sockets, without layer-2 probes on every VLAN, and without root on the core discovery path.*

---

## 1. The problem

[Retained from the old doc's problem section, compressed. Specifically name the VLAN boundary, the scanner-per-VLAN burden, the VM-vs-bare-metal ambiguity, and why promiscuous capture isn't a real answer. 2–3 paragraphs.]

## 2. Solution

[Retained from the old doc's solution section, compressed. State the three authoritative sources, name why each is authoritative. 2 paragraphs + the architecture SVG embedded.]

![architecture](docs/images/architecture.svg)

## 3. Architecture walk-through

### 3.1 Discovery loop

[How the scanner loop runs; `asyncio.gather` on all sources; timeout handling; what happens when a source is unavailable (source-health surfaced on the UI).]

### 3.2 Merge strategy

[How conflicting ARP/NDP entries across sources are resolved, who wins (OPNsense first, SNMP/nmap supplemental).]

### 3.3 Syslog pipeline

[UDP 514 DatagramProtocol, RFC 3164 + 5424, filterlog CSV parser. Why not logrotate/journald — we want live, not archived.]

### 3.4 Disappearance and alerting

[Per-cycle disappearance_count increment, configurable threshold, webhook payload shape.]

## 4. Design decisions and tradeoffs

**This section is the differentiator — answer each in 2–4 sentences. Prefer concrete reasoning over vague upside.**

### Why SQLite, not Postgres

[Reasoning.]

### Why async-first, not threaded

[Reasoning — GIL, syslog concurrency with scan cycle, aiosqlite for non-blocking.]

### Why the OPNsense API replaced scapy as the primary discovery path

[Reasoning — VLAN boundary, root requirement, authoritative data.]

### Why webhooks, not push notifications

[Reasoning — integration freedom, homelab users own the alert target.]

### Why vanilla HTML + Tailwind CDN, not a framework

[Reasoning — no build step, fits the project's "one container, one file" ergonomics.]

### Why MAC as the device identity, not IP

[Reasoning — IPs move; MAC uniquely identifies hardware/VM across DHCP churn.]

## 5. Implementation notes (per module)

- **`src/main.py`** — FastAPI app, lifespan, endpoint definitions. The lifespan branches on `DEMO_MODE` so the demo path never touches production integrations.
- **`src/scanner.py`** — scapy ARP fallback. Legacy; the OPNsense path is the primary. Still present for air-gapped homelabs with no OPNsense.
- **`src/opnsense.py`** — REST client. Notable constraint: dnsmasq's DHCP endpoint returns hostnames in a paginated form that's easy to miss.
- **`src/identifiers.py`** — MAC OUI lookup, Docker TCP socket client, Proxmox API client. The interesting case is host-network Docker containers — they share the daemon host's MAC, so the merge logic attributes them back to the host rather than emitting a phantom IP.
- **`src/syslog_server.py`** — async UDP DatagramProtocol. Notable constraint: OPNsense filterlog CSV position-26 can be missing on older builds; parser treats positions as optional.
- **`src/database.py`** — aiosqlite schema, upserts by MAC. All writes go through one async connection to avoid SQLite's single-writer lock surprising the scan+syslog concurrency.
- **`src/demo_seed.py`** — deterministic seed for `DEMO_MODE`. Lives here so a UI change and its screenshot update land in the same PR.

## 6. What's next

[Short, honest, not marketing. Examples:]
- Optional Prometheus metrics exporter (not yet — unclear if anyone but me wants it).
- Per-device timeline graph (scan-miss history over time — useful, needs a thoughtful schema change).
- UI tests via Playwright, scoped to the critical flows only (deferred; not worth the maintenance tax until the UI churns less).

---

*Back to [README](./README.md). Maintainer: Skyler King · [moshthesubnet.com](https://moshthesubnet.com).*
```

Fill in the bracketed `[…]` sections with real content from the old PROJECT_SUMMARY.md (trimmed and reworked, not verbatim copy-paste). The "Design decisions" section is the only one allowed to grow beyond the sketch above — reviewers read that section hardest.

- [ ] **Step 3: Validate length**

Run: `wc -c /home/skyler/network-monitoring-app/ARCHITECTURE.md`
Expected: 14000–19000 bytes.

If > 19 KB, trim (the usual suspects: duplicated problem-statement wording also in README; overly-specific per-function walkthroughs in §5; hedges in §6).

If < 14 KB, the Design Decisions section is probably underdeveloped — add real reasoning, not filler.

- [ ] **Step 4: Verify no contradictions with README**

Run: `grep -iE "SCAN_INTERVAL_SECONDS|ALERT_DISAPPEARANCE_THRESHOLD|scapy|OPNsense API|VLAN boundary" /home/skyler/network-monitoring-app/README.md /home/skyler/network-monitoring-app/ARCHITECTURE.md`

Spot-check: every factual claim (threshold defaults, primary scan path, VLAN reasoning) is consistent between the two files. If they disagree, fix the one that's wrong — code wins as the source of truth; cross-check against `src/main.py` env-var defaults and `src/scanner.py`.

- [ ] **Step 5: Commit**

```bash
cd /home/skyler/network-monitoring-app && git add ARCHITECTURE.md && git commit -m "docs: rewrite ARCHITECTURE.md as a case-study

Trim ~28 KB -> ~16 KB. Restructure into a problem/solution/walk-through
arc, add a Design Decisions section, consolidate per-module notes."
```

---

## Phase 6 — Quality gates

### Task 6.1: Run the full quality-gate checklist

**Files:** (none modified; verification only)

- [ ] **Step 1: Hygiene check**

Run:
```bash
cd /home/skyler/network-monitoring-app && git ls-files | grep -E "(\.env$|\.db$|^_.*_tmp|^scan\.py$)"
```
Expected: empty.

Run:
```bash
cd /home/skyler/network-monitoring-app && ls network_monitor.db _*_tmp.py scan.py 2>&1
```
Expected: each `No such file or directory`.

LICENSE copyright sanity:
```bash
cd /home/skyler/network-monitoring-app && grep -iE "copyright|your name" LICENSE
```
Expected: a line containing "Copyright (c) 2026 Skyler King" and no "Your Name" placeholder.

Docker-compose service name:
```bash
cd /home/skyler/network-monitoring-app && grep -E "^\s*(netcensus|network-monitor):" docker-compose.yml
```
Expected: exactly one line matching `netcensus:`.

- [ ] **Step 2: Test suite passes**

Run:
```bash
cd /home/skyler/network-monitoring-app && source venv/bin/activate && pytest tests/ -v
```
Expected: all tests pass.

- [ ] **Step 3: Demo path works on a clean clone**

```bash
rm -rf /tmp/netcensus-final-check && git clone /home/skyler/network-monitoring-app /tmp/netcensus-final-check && cd /tmp/netcensus-final-check
docker compose -f docker-compose.demo.yml up --build -d && sleep 8
curl -s http://localhost:8080/api/devices | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d) >= 40, f'only {len(d)} devices'; print(f'OK: {len(d)} devices')"
docker compose -f docker-compose.demo.yml down
```
Expected: `OK: 47 devices` (or similar).

- [ ] **Step 4: Real path still works (smoke)**

```bash
cd /home/skyler/network-monitoring-app && docker compose up --build -d && sleep 10
curl -sI http://localhost:8000/ | head -1
docker compose down
```
Expected: `HTTP/1.1 200 OK`. (Data may be empty if the user's real `.env` credentials aren't present; the dashboard rendering is what we're checking.)

- [ ] **Step 5: README renders on GitHub**

Push to a branch (or main if already merged), view on GitHub. Check every inline image renders. Check every link resolves. Check the hero code block is copy-pasteable.

- [ ] **Step 6: ARCHITECTURE.md renders on GitHub**

Same treatment. Check the architecture SVG renders inline.

- [ ] **Step 7: Tag C3**

```bash
cd /home/skyler/network-monitoring-app && git tag c3-portfolio-complete && git log --oneline c1-dashboard-restyle..HEAD
```

Checkpoint C3 reached. Full portfolio state: restyled dashboard, bundled demo mode, rewritten README with inline visuals, case-study ARCHITECTURE.md, clean repo root.

---

## Execution choice

**Plan complete and saved to `docs/superpowers/plans/2026-04-23-netcensus-portfolio-polish.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
