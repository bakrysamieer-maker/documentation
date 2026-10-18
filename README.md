# Supplier Scout

A multi-agent pipeline that finds Chinese **clothing-textile suppliers** that exhibit at the Canton
Fair, rules out trading companies and weak suppliers, researches the rest in depth (including
their ability to export to **Saudi Arabia**), and produces **PDF profiles** with contact details.
It processes **50 suppliers per batch**: up to 25 garment factories and 25 woven fabric mills.

## The four layers

| Layer | Who does it | What it does | Rules |
|---|---|---|---|
| 1. Discovery | 4 agents, one per product/region slice (plus top-up agents if a segment is short) | Finds Canton Fair exhibitors that make woven clothing or woven apparel fabric, with evidence | [`guidelines/01-discovery.md`](guidelines/01-discovery.md) |
| 2. Vetting | One agent per 5 suppliers | Rejects trading companies, suppliers without their own factory, knitting specialists, non-clothing suppliers, and suppliers below the quality bar | [`guidelines/02-vetting.md`](guidelines/02-vetting.md) |
| 3. Deep dive | One agent per 2 suppliers | Researches Chinese registry data, factory location and capacity, certificates, KSA export ability and contacts; scores each supplier | [`guidelines/03-deep-dive.md`](guidelines/03-deep-dive.md) |
| 4. Report | One batch-editor agent, then a PDF script | Ranks suppliers, writes the batch overview, renders the PDFs | [`guidelines/04-report.md`](guidelines/04-report.md) |

Every agent also follows [`guidelines/00-common-rules.md`](guidelines/00-common-rules.md). It
defines scope, forbidden sites, evidence rules and contact rules. Each layer passes structured
JSON to the next one, and every claim carries a source link.

## What counts as a match

- **Garment factories**: finished **woven** clothing, such as shirts, trousers, suits, jackets,
  dresses, abayas, thobes and workwear.
- **Fabric mills**: **woven** fabric for clothing, such as shirting, suiting, denim, linen,
  rayon, thobe fabric and abaya fabric.
- **Excluded**:
  - home textiles, furniture and upholstery, shoes, bags and accessories
  - non-woven and technical textiles
  - knitting specialists (knit fabric, knitwear, sweaters, jersey T-shirts)
- **Quality bar**:
  - the supplier's own factory, with evidence
  - at least 3 years in business
  - at least one quality signal: ISO 9001, BSCI, SEDEX, WRAP, OEKO-TEX, GOTS or GRS, a
    third-party audit, Canton Fair brand or award status, or known brand customers

## Sources and limits

- **The Canton Fair website is not used.** Its `robots.txt` asks AI tools, including Claude,
  not to access it. Layer 1 finds exhibitors through public sources instead: company websites,
  government-published exhibitor lists, B2B platforms such as Made-in-China, and search results.
- **LinkedIn is never opened.** LinkedIn URLs are copied from search results only.
  `baidu.com` and `globalsources.com` are skipped because they block automated visitors.
- **Contacts come from public sources** (company websites and B2B pages). Canton Fair's own
  contact details require a buyer login, so each PDF links to the evidence you need to look
  them up yourself.
- **Self-reported claims are labelled.** Always confirm certificates, factory status and SABER
  documents with the supplier before ordering.

## Running a batch

Open a Claude Code session on this branch and say **"run the next supplier-scout batch"**.
Claude runs these steps:

1. `python3 scripts/batch.py known-names` returns the suppliers already processed, which are
   skipped.
2. Run the workflow `.claude/workflows/supplier-scout-discover.js`. Its args are the slices from
   `config/discovery-slices.json` and the known names.
3. `python3 scripts/batch.py save-discovery runs/batch-NN <discover transcript dir> --batch batch-NN --date YYYY-MM-DD`
4. Run `.claude/workflows/supplier-scout-research.js` with `{run_dir, candidate_ids}`. One run
   per segment can go in parallel.
5. `python3 scripts/batch.py collect runs/batch-NN <research transcript dirs...>`
6. `python3 scripts/batch.py report-input runs/batch-NN`, then run
   `.claude/workflows/supplier-scout-report.js` with `{run_dir}`, then
   `python3 scripts/batch.py save-report runs/batch-NN <report transcript dir>`.
7. `python3 scripts/render_pdfs.py runs/batch-NN` writes the PDFs to `runs/batch-NN/reports/`.
8. `python3 scripts/batch.py registry runs/batch-NN` records the batch in `data/processed.json`,
   so the next batch finds new suppliers. It also keeps leftover candidates in
   `data/backlog.json`.

## Folder layout

```
guidelines/            rules for each agent layer (edit these to change behaviour)
config/                discovery slices: which products and regions Layer 1 searches
.claude/workflows/     the multi-agent workflow scripts
scripts/               batch.py (glue) and render_pdfs.py (Layer 4 PDFs)
runs/batch-NN/         one folder per batch: JSON from each layer, plus reports/ with the PDFs
data/                  processed.json and backlog.json (suppliers seen so far)
tests/                 test_render.py, a PDF smoke test with made-up sample data
```

## Changing the rules

The guidelines and the slices file are plain text. To make vetting stricter, to search other
cities, or to change what "quality" means, edit the matching file. The next batch follows the
new rules. No code changes are needed.

## Test

```
python3 tests/test_render.py
```

Needs Python 3 with `reportlab` and `pypdf`.
