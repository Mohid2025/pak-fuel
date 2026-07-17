# context.md

## 1. What this is

**pak-fuel** is a single-page web app that visualizes Pakistan's notified petroleum
(POL) price history — every officially notified petrol/diesel/kerosene/LDO/Jet-A1
price revision going back to 2006. It solves the problem that no clean, trustworthy,
reusable dataset of Pakistani fuel prices exists in one place: consumer news sites
disagree with each other and the regulator's site blocks scrapers. The project is two
things bolted together: a **Python scraper** that pulls a primary source (Pakistan
State Oil) into a versioned JSON/CSV dataset, and a **React dashboard** that renders it.
The dataset itself (committed to git, republished as CSV) is treated as a public good,
not just backing data for the demo.

## 2. Stack & tooling

- **Frontend:** React 19 (`react` / `react-dom` ^19.2.7), **Recharts 3** for the line chart.
- **Build:** Vite 8 (`@vitejs/plugin-react`), ES modules (`"type": "module"`). Package manager: **npm** (package-lock.json present).
- **Lint:** ESLint 10 flat config with `eslint-plugin-react-hooks` and `eslint-plugin-react-refresh`.
- **Scraper:** Python (local `.venv` is 3.9; **CI runs 3.12**), `requests` + `beautifulsoup4`. Deps pinned in `requirements.txt`.
- **Automation:** GitHub Actions (scheduled scrape + auto-commit).
- **Fonts:** Google Fonts (Space Grotesk, IBM Plex Mono) loaded via `<link>` in `index.html`.
- No TypeScript, no test framework, no CSS framework (hand-written CSS with custom properties).

## 3. Architecture

Two decoupled halves that meet only at a static JSON file. There is **no backend at
runtime** — the app is fully static and reads a file that a scheduled job regenerates.

```
  ┌─────────────── DATA PIPELINE (offline / CI) ───────────────┐
  psopk.com archive ──HTTP──> scrape_pso.py ──> public/data/prices.json
   (paginated HTML)            (BeautifulSoup)   public/data/prices.csv
                                     │                    │
                          GitHub Actions cron        committed to git
                          (2x/day) auto-commits       (versioned dataset)
  └────────────────────────────────────────────────────────────┘
                                     │
  ┌─────────────── FRONTEND (browser, static) ────────────────┐
   index.html ──> src/main.jsx ──> src/App.jsx
                                     │ fetch(BASE_URL + "data/prices.json")
                                     ▼
                        hero "pump" panel (latest price, animated count-up)
                        + product/range chip controls (useState)
                        + Recharts stepAfter LineChart
  └────────────────────────────────────────────────────────────┘
```

**Frontend flow:** `main.jsx` mounts `<App>` in StrictMode → `App` fetches
`prices.json` once on mount into `data` state → derives `latest`/`prev` revision →
renders a hero panel (animated petrol price via `useCountUp` rAF hook), a set of
toggle chips for products and time ranges (`active`/`range` state), and a Recharts
line chart. Chart data is `revisions` mapped to `{t: epoch_ms, ...products}` and
filtered by the selected range cutoff. All state is local component state — no store,
no router, single component.

**Scraper flow:** `scrape_page(n)` fetches an archive page, finds every text node
matching "Effective From", parses the date, grabs the *next* `<table>`, maps product
labels to stable keys, and collects `{effective_from, products}`. `main()` either does
page 1 (daily) or `--backfill` (walk all discovered pages once), upserts by effective
date into existing data, computes per-revision `change` deltas, and writes JSON + CSV.

## 4. Directory map

- `src/` — React app. `main.jsx` (bootstrap/mount), `App.jsx` (the entire UI — one component + helpers), `index.css` (all styling, design tokens as CSS vars). `src/assets/` holds `hero.png` and the Vite logo (assets appear unused by App.jsx).
- `public/` — static served-as-is files. `public/data/prices.json` + `prices.csv` are the **generated dataset** (committed, not build output). `public/icons.svg`, `public/favicon.svg`.
- `scrape_pso.py` — the scraper (single file, ~230 lines, well-commented).
- `.github/workflows/update-prices.yml` — scheduled scrape-and-commit job.
- `index.html` — Vite entry HTML; sets `<title>`/meta and loads Google Fonts.
- `requirements.txt` — Python deps for the scraper.
- `.venv/` — local Python 3.9 virtualenv (gitignored).
- Root config: `vite.config.js`, `eslint.config.js`, `package.json`.

## 5. How to run it

**Frontend (Node):**
```bash
npm install
npm run dev        # Vite dev server with HMR
npm run build      # production build -> dist/
npm run preview    # serve the built dist/
npm run lint       # eslint .
```

**Scraper (Python):**
```bash
pip install -r requirements.txt      # or: pip install requests beautifulsoup4
python scrape_pso.py --backfill      # one-time: walk the entire archive
python scrape_pso.py                 # incremental: page 1 only (the daily job)
```

**Deploy:** *No deploy step exists in the repo.* The GitHub Actions workflow only
scrapes and commits data — it does **not** build or publish the site. Deployment of the
static build is currently unconfigured (see Gotchas). The CI job runs on cron
`0 2 * * *` and `0 16 * * *` (02:00 & 16:00 UTC, i.e. twice daily) and on manual
`workflow_dispatch`.

## 6. Data & external dependencies

- **Data source:** `https://psopk.com/fuel-prices/pol/archives` (Pakistan State Oil, paginated server-rendered HTML). Chosen over OGRA (blocks bots) and news aggregators (unreliable/contradictory) — see the module docstring in `scrape_pso.py`.
- **`public/data/prices.json` shape:**
  ```json
  {
    "updated_at": "ISO-8601 UTC",
    "source": "…", "note": "…",
    "revision_count": 379,
    "revisions": [
      { "effective_from": "YYYY-MM-DD",
        "products": { "petrol": 62.13, "hsd": 62.65, "ldo": …, "sko": …, "jp1": … },
        "change":   { "petrol": -7.13, … } }   // delta vs previous revision, computed in the scraper
    ]
  }
  ```
  Current dataset: **379 revisions**, `2006-01-01` → `2026-07-11`. `prices.csv` is the flat form (`effective_from, product, price_pkr_per_litre, change`).
- **Stable product keys:** `petrol`, `hsd` (high-speed diesel), `sko` (kerosene), `ldo` (light diesel oil), `jp1` (Jet A-1). Scraper also maps `e10` and `hobc`, but the frontend `PRODUCTS` map only renders the five above.
- **External services at build/dev time:** Google Fonts CDN (frontend), psopk.com (scraper only). No API keys, **no environment variables required** anywhere.
- **Runtime deps:** none — fully static; the browser only fetches the local `prices.json`.

## 7. Conventions & patterns

- **Stable keys over source labels:** PSO's product names drift over the years (`MOGAS` → `PMG` → `PREMIER EURO 5`, etc.). `PRODUCT_MAP` in the scraper normalizes all variants to fixed keys; the frontend and CSS only ever reference the stable keys.
- **Fail loud, never silent:** the scraper exits non-zero and writes nothing if it scrapes zero revisions, and prints unmapped product labels loudly rather than dropping them. Rationale (stated in comments): stale-but-served numbers are worse than an honest outage.
- **Structure-based parsing, not CSS selectors:** the scraper locates data by finding "Effective From" text then the next `<table>`, deliberately so CSS/markup reshuffles on PSO's site don't silently break it.
- **Derive-once:** per-revision price `change` is computed in the scraper and stored, not recomputed in the UI.
- **Styling via CSS custom properties:** all colors/fonts are tokens in `:root` (`index.css`); product line colors are `var(--petrol)` etc., referenced from `App.jsx`'s `PRODUCTS` map. Class naming is BEM-ish (`.pump__price`, `.chip__dot`).
- **Accessibility:** `aria-pressed` on toggle chips, `prefers-reduced-motion` respected (count-up animation and transitions disabled), visible `:focus-visible` outlines.
- **Single-component frontend:** everything lives in `App.jsx` with small module-level helpers (`rs`, `longDate`, `useCountUp`, `Tip`). No component library, no state manager.

## 8. Non-obvious decisions & gotchas

- **The README is NOT project documentation.** `README.md` is the stock Vite+React template boilerplate — it says nothing about fuel prices. Do not treat it as ground truth; `index.html`'s `<title>`/meta and the `scrape_pso.py` docstring are the real project description.
- **No deployment is wired up.** CI scrapes and commits data only; nothing builds/publishes `dist/`. `App.jsx` fetches via `import.meta.env.BASE_URL`, but `vite.config.js` sets **no `base`** — so it defaults to `/`. If this is ever deployed to GitHub Pages under a repo subpath (`/pak-fuel/`), you must set `base` in the Vite config or the `prices.json` fetch (and asset paths) will 404. *(Inference — the `BASE_URL` usage suggests subpath deployment was anticipated, but it isn't configured.)*
- **Python version mismatch:** local `.venv` is **3.9**, CI uses **3.12**. And CI does `pip install requests beautifulsoup4` directly rather than `pip install -r requirements.txt`, so the pinned versions in `requirements.txt` are **not** what runs in CI.
- **Dataset has genuinely odd historical values** (e.g. `2006-01-09` shows `jp1: 12.0`, `sko: 33.0`; deltas swing wildly across adjacent 2006 revisions). The scraper trusts the source verbatim and does no sanity-clamping — these reflect what PSO's archive actually publishes, not scraper bugs.
- **Daily job only sees page 1.** New revisions are assumed to appear on archive page 1. `--backfill` is a one-time manual operation; if PSO ever back-inserts an old revision on a deeper page, the daily job won't pick it up.
- **Upsert-by-date, newest-scrape-wins:** re-running the scraper merges on `effective_from`; a changed value for an existing date overwrites the stored one. There is no history of corrections.
- **`Rs.0/Ltr` means "not offered", not free** — the scraper explicitly drops zero/negative prices so a discontinued product doesn't render as ₨0.
- **Recharts uses `type="stepAfter"`** deliberately — fuel prices are step functions (flat until the next notification), so interpolated lines would misrepresent the data. Chart animation is disabled (`isAnimationActive={false}`) and `connectNulls` bridges revisions where a product wasn't listed.
- **`e10` and `hobc`** are scraped and stored but have no entry in the frontend `PRODUCTS` map, so they're in the dataset/CSV but invisible in the UI.

## 9. Current state & open threads

- **Working:** scraper (backfill + incremental), 379-revision dataset through 2026-07-11, twice-daily GitHub Actions auto-update (recent commits confirm it's running), full dashboard (hero panel, product/range toggles, step-line chart, tooltip, error/loading states, reduced-motion + focus handling).
- **Incomplete / open:**
  - No site deployment configured (build is never published; `base` unset — see Gotchas).
  - No tests anywhere (no JS or Python test framework present).
  - `requirements.txt` and CI's ad-hoc `pip install` are out of sync.
  - `src/assets/hero.png` and `vite.svg` appear unused by `App.jsx`.
  - `e10`/`hobc` products carried in data but not surfaced in the UI.
- **No TODO/FIXME markers** were found in the source; the above are gaps observed from reading the code, not annotated tasks.
