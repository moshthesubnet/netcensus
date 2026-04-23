# netcensus — Portfolio Polish Design

**Date:** 2026-04-23
**Author:** Skyler King
**Status:** Approved for planning

## Summary

Transform `netcensus` from a functional homelab tool into a hiring-manager-ready GitHub surface. The work is docs + UI polish only — no new features, no code refactors. Three coordinated deliverables: a restyled single-page dashboard, a bundled demo mode for reproducible screenshots, and a rewritten README anchored on architecture visuals.

## Context

The project currently works but reads as unfinished on GitHub:

- Four different names across artifacts (`Network Monitor` / `netcensus` / `Network Discovery & Syslog Monitor` / `API-Driven Cross-VLAN Network Monitor`).
- README is accurate but text-heavy with no visuals and inconsistent framing.
- Dashboard is functional but visually dense and generic-feeling; header crowds five stat-chips, seven source-chips, a refresh button, and branding into one row.
- Repo root is cluttered with `_*_tmp.py` scratch files, a 10 GB root-owned `network_monitor.db`, and a committed `.env`.
- `PROJECT_SUMMARY.md` (28 KB) is a strong case study buried behind a generic filename.

The viewing context is **GitHub README + screenshots/GIFs** for a **mixed audience** (infra/SRE, backend, security). The goal is to make the repo's first-impression surface signal careful engineering to all three lenses in ~60 seconds of skimming.

## Goals

- Hiring-manager-ready README that reads well to infra / backend / security lenses in 60 seconds.
- Consistent visual language between `netcensus` and `moshthesubnet.com` — same palette, same typography, same editorial-dark voice.
- Reproducible screenshots via a bundled `--demo` mode that third parties can also run to try the dashboard.
- Project identity consolidated under the single name `netcensus`.
- Clean repo surface: no scratch files, no committed DB, no stale docs.

## Non-goals

- No feature additions (no new scanners, no new integrations, no new API endpoints).
- No dashboard structural redesign — regions stay where they are; only visual language and the stat-strip composition change.
- No hosted demo, no landing page outside the repo, no CI/CD work.
- No test-coverage push.
- No module refactors, no code reorganization, no dependency upgrades.
- No animated GIF / video demo in this pass (deferred).

## Approach

Execution order is **dashboard restyle → demo mode → screenshots → README rewrite → hygiene**. The dashboard drives the README's best visuals, so reversing the order means writing the README blind and re-doing it.

Three natural ship points:

- **C1 — Dashboard restyle complete.** Current README still works; the dashboard is simply better. Safe stop.
- **C2 — Demo mode works end-to-end.** Screenshots can be taken reproducibly on a fresh machine. Safe stop.
- **C3 — README + `ARCHITECTURE.md` rewritten, hygiene done.** Full portfolio state.

---

## §1 — Dashboard restyle

### What stays

- Single-page `frontend/index.html`. No framework adoption, no component split, no build step. Tailwind via CDN is fine.
- Regions: header → search+export row → bulk-action bar → device table → slide-in right detail panel.
- All current features: search, filter, CSV/JSON export, bulk retype, device detail panel, Docker/Proxmox metadata, disappearance alerts.

### What changes (visual language)

Palette (sourced from `/home/skyler/website/assets/css/custom.css` to match `moshthesubnet.com`):

- **Surface:** `#111111` (body), `#1a1a1a` / `#1c1c1c` (cards), `#262626` (hairline borders).
- **Text:** `#fafafa` (primary), `#b0b0b0` (body), `#a3a3a3` / `#737373` (muted), `#525252` (quietest).
- **Accent:** `#5eead4` teal with `#4cc9b0` as hover/pressed. No gradients.
- **Error/alert:** `#f87171`.

Typography:

- **Georgia** for wordmark and page-level titles (matches website hero).
- **System sans** for UI chrome (labels, buttons, body copy).
- **Fira Code** for data (IPs, MACs, counters, table body) — replaces the current JetBrains Mono to match the website.

Concrete changes:

- **Header:** replace chip-row with a clean wordmark bar (`nc` monogram tile + `netcensus` in Georgia + `/ <deployment-label>` in quiet grey). Live dot gets a soft teal glow. Refresh becomes an outlined teal chip, not a filled button.
- **Overview strip (new):** 4 cards below the header — `Devices` / `VLANs` / `Composition` (with stacked-bar) / `Alerts`. Replaces the 5 in-header stat-chips.
- **Source-health row:** stays, but demoted to a quiet Fira-Code row of short labels (`opnsense`, `docker(3)`). Healthy = teal dot, disabled = hollow grey ring.
- **Table:** tighter row padding, Status as dot + text instead of a pill, hover uses accent teal at low opacity. Columns unchanged.
- **Side panel:** same structure; upgraded type badge, subtle header accent, aligned metadata grids.
- **Motion:** respect `prefers-reduced-motion`; no bouncy transitions.

### Slop-guardrail rules (hard constraints)

1. Accent `#5eead4` appears in at most two places per viewport: the monogram/wordmark area and one primary action. Nowhere else.
2. No gradients anywhere.
3. No emoji in UI copy.
4. No generic stock icons. SVGs only where they earn their place (sources, device-type badges, close/expand/copy actions).
5. No glassmorphism. Solid dark surfaces with 1 px hairline borders.
6. Demo seed data must look plausible (real image names, real hostnames), not `42 / 1337 / foo-bar`.

---

## §2 — Demo mode

### Purpose

Bundled into the repo so third parties can run it (`docker compose -f docker-compose.demo.yml up`). Also the source-of-truth for README screenshots.

### Invocation

- New env var: `DEMO_MODE=true`. Activated by a dedicated `docker-compose.demo.yml` (different port to avoid clashing with a real instance) and a `DEMO=1 ./start.sh` shortcut for bare-metal.
- When active: scanner loop is bypassed (no OPNsense / Proxmox / Docker calls), no UDP 514 bind, no webhooks fired. A seeder writes fixtures into a fresh SQLite DB on startup and then idles.

### Seeded narrative (one coherent homelab)

- **VLANs:** `mgmt` (VLAN 10), `servers` (20), `lab` (30), `iot` (40), `guests` (50), `dmz` (99).
- **Bare metal:** 1 OPNsense firewall, 1 managed switch, 2 APs on `mgmt`.
- **Proxmox:** 2 nodes (`pve-01`, `pve-02`), 8 VMs (Grafana, Prometheus, Postgres, Gitea, Vaultwarden, Home Assistant, Plex, pi-hole), 4 LXCs (nginx-proxy, cloudflared, syslog-ng, unifi-controller).
- **Docker:** 3 hosts, ~20 containers using real public image names (`grafana/grafana`, `postgres:16`, `ghcr.io/home-assistant/home-assistant`, etc.).
- **IoT endpoints:** a printer, two cameras, a smart plug on VLAN 40.
- **One intentional `device_gone` alert** on a VLAN 99 device — so the alerts card isn't empty and the disappearance feature is visible in screenshots.
- **Syslog:** a trickle of seeded entries with varied severities, including two OPNsense `filterlog` BLOCK lines so the log panel has real content.

### Implementation shape

- New file: `src/demo_seed.py` (~200 lines). Exports `seed_demo_db(db_path)`.
- New file: `docker-compose.demo.yml`. Same image, `DEMO_MODE=true`, publishes on host port `8080` (main app uses `8000`) so both can run side-by-side.
- `src/main.py` lifespan: if `DEMO_MODE=true`, skip starting scanner/syslog tasks and call `seed_demo_db` once.
- Seed is deterministic (fixed random seed) so screenshots are reproducible across runs.
- Documented in the new README under "Try it."

### Non-goals for demo mode

- Not a playground — no interactivity simulation, no timer-driven "fake" events. Static-snapshot fidelity only.
- Doesn't touch production code paths — scanner/syslog remain unmodified by the demo path.

---

## §3 — README rewrite

### Length target

~600–900 words of prose + 3 inline visuals + code blocks. Scannable in 60 seconds, deep-readable in 5 minutes.

### README structure

1. **Hero (~60 words).** Project name in Georgia, one-line tagline, 1-sentence "what it does," a single CTA code-block: `docker compose -f docker-compose.demo.yml up`. No badges row, no TOC.
2. **The problem (~80 words).** ARP doesn't cross VLANs. Running a scanner per VLAN is brittle. Layer-2 scanning can't distinguish a VM from bare metal. Credibility paragraph for the networking lens.
3. **Visual #5 — Before/after diagram.** Inline SVG. Left panel: single-host ARP scanner with X'd arrows to three VLANs. Right panel: OPNsense/Proxmox/Docker APIs pointing inward to a merged view.
4. **The approach (~80 words).** Three bullets: OPNsense for global ARP/NDP, Proxmox for VM/LXC inventory by MAC, Docker daemons for containers. Merged into one registry. No raw sockets, no per-VLAN probes. Async and concurrent.
5. **Visual #1 — Architecture diagram.** Inline SVG. Left: data sources. Middle: scanner loop, syslog receiver, SQLite. Right: FastAPI / Web UI / webhooks. Real names, not "Service A."
6. **Visual #3 — Dashboard screenshot (seeded demo).** Single high-res PNG of the restyled dashboard against the seeded data. Caption names what's visible.
7. **Feature highlights (~150 words).** 4–6 one-sentence bullets, each linking deeper into `ARCHITECTURE.md`.
8. **Try it (~80 words).** Two tabbed blocks: Demo (no infra) · Real usage (`.env` setup).
9. **Stack (~30 words).** One line: Python 3.11 · FastAPI · asyncio · aiosqlite · Tailwind CDN. No badge forest.
10. **Footer.** `Skyler King · moshthesubnet.com · MIT License · See ARCHITECTURE.md for the deep dive.`

### What the README will not contain

- No emoji headings.
- No animated GIFs (deferred).
- No shields.io badges.
- No 20-item "Features" checklist.
- No "Roadmap" / "Coming soon" section.
- No AI-generated-sounding language ("seamless," "lightning-fast," "powerful platform").

---

## §4 — ARCHITECTURE.md (renamed from PROJECT_SUMMARY.md)

### Change

Rename `PROJECT_SUMMARY.md` → `ARCHITECTURE.md`. Industry convention, searchable, sets the right expectation.

### Target length

~15–18 KB (down from 28 KB).

### Case-study structure

1. Problem (specific and technical).
2. Solution summary.
3. Architecture walk-through (reuses the README's architecture SVG, expands with sub-diagrams if useful).
4. **Design decisions and tradeoffs.** The section that differentiates this doc from every other GitHub architecture doc: "Why SQLite, not Postgres. Why async-first, not threaded. Why I ripped out scapy. Why webhooks, not push notifications." This is where hiring managers judge whether the author thinks or just ships.
5. Implementation notes — one short paragraph per module (what it does, the interesting constraint, the tradeoff).
6. "What I'd change / what's next" — short, honest, not a marketing roadmap.

---

## §5 — Hygiene pass

1. **Remove committed DB.** `network_monitor.db` (10 GB, root-owned) is in the working tree. Ensure `.gitignore` covers `*.db`. If the file is in git history, decide during implementation whether to rewrite history (acceptable here — no contributors) or accept the bloat.
2. **Clean up tmp scripts.** `_full_scan_tmp.py`, `_live_scan_tmp.py`, `_verify_scan_tmp.py`, `scan.py` — delete or move to a gitignored `scratch/` directory.
3. **Remove committed `.env`.** Confirm it isn't tracked; if it is, remove from history.
4. **Consolidate naming to `netcensus`.** Retitle `CLAUDE.md`. Correct its Tech Stack (scapy is no longer the primary path — commit `5acb0be` replaced it with the OPNsense API). Audit `docker-compose.yml` service name and `LICENSE` copyright holder.
5. **LICENSE sanity.** Confirm MIT copyright line names "Skyler King."
6. **`.gitignore` hardening.** Add / confirm: `*.db`, `data/*.db`, `.env`, `venv/`, `.superpowers/`, `__pycache__/`, `*.pyc`.
7. **Optional — make syslog bind non-fatal.** If UDP 514 can't be bound on bare metal (no sudo), log a clear warning and continue. Keeps the Docker flow the recommended path; reduces cloning friction. Defer if it complicates the async lifespan.

### Non-goals for hygiene

- No Python-symbol renames, no module moves, no class renames.
- No dependency upgrades beyond trivial syncs.

---

## Success criteria

1. A hiring manager opening `github.com/moshthesubnet/netcensus` on a phone, in 30 seconds, can answer: what does this do, how does it work at a glance, and should I be impressed?
2. The screenshot in the README matches the live dashboard (no drift between claim and code).
3. `docker compose -f docker-compose.demo.yml up` on a clean machine reproduces the dashboard in the screenshot.
4. Visual language is consistent between `netcensus` and `moshthesubnet.com`.
5. Repo root is clean: no `_*_tmp.py`, no 10 GB DB, no `.env`.

### Quality gates

- **Dashboard restyle.** Manual smoke test every visible control. A11y spot-check (contrast, focus rings). No new console errors.
- **Demo mode.** Run on a clean machine (throwaway VM or fresh clone), confirm startup under 30 seconds, confirm screenshots match.
- **README.** Read top-to-bottom on desktop and mobile GitHub views. All links resolve. All images render at reasonable size.
- **ARCHITECTURE.md.** Read top-to-bottom. No contradictions with the README. "Design decisions" section is the strongest part.
- **Hygiene.** `git ls-files | grep -E '(\.env$|\.db$|^_.*_tmp)'` returns nothing.

### Explicit non-measurements

- Test coverage.
- Lighthouse performance score.
- Bundle size.

## Risks

- **Seed drift.** Adding UI fields later without updating the seed makes screenshots go stale. Mitigation: seed lives in the repo, updated in the same PR as UI changes.
- **Inline SVGs in GitHub markdown.** GitHub renders SVGs in `.md` but can strip certain styles. Mitigation: test both diagrams in GitHub's rendered view before shipping. Fallback to PNG export if needed.
- **ARCHITECTURE.md scope creep.** Trimming 28 KB → 15 KB can balloon into a 40 KB rewrite. Mitigation: "Design decisions" is the only section allowed to grow; everything else shrinks.

## Out of scope (for a future pass)

- Animated GIF / MP4 of discovery and log streaming.
- Hosted live demo.
- Test-coverage expansion.
- Python-module refactors.
- CI/CD workflows.
