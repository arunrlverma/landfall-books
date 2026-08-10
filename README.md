# landfall-books

The deep shelf behind [Landfall](https://madelandfall.com): hundreds of public-domain
books, cleaned by the same deterministic pipeline as the app's bundled classics
(Project Gutenberg boilerplate stripped, paragraphs unwrapped, chapter structure
normalized, openings cleaned — zero prose altered), and filtered to a
conservative worldwide rights rule (every author and translator dead 70+ years,
unknowns excluded).

- `catalog.json` — the searchable index the app fetches
- `books/<slug>.md` — one cleaned text per book
- `collections/open-religion.json` — the rights-first open religion collection
- `rights/open-religion.json` — exact source, version, checksum, license, and capability ledger
- `rights/evidence/` — immutable local snapshots of the controlling license notices
- `research/open-religion/` — the full curated and discovery queues from the research workbook

Served as static files; the app downloads a book once on first open.
All texts are in the public domain. © 2026 NextBase LLC for the tooling.

## Editorial quality gate

Run `python3 tools/editorial_quality.py` before publishing. It verifies every
catalog object, checksum, title, and high-confidence ebook-production artifact.
`--write` applies only the reviewed, prose-preserving cleanup rules and refreshes
the catalog hashes.

## Open Religion Library

`tools/import_open_religion.py` converts the research workbook into a guarded,
deduplicated content collection. It imports exact Tier-A source artifacts plus
a fixed, reviewed allowlist of Tier-B Project Gutenberg candidates. Tier-B
records are fail-closed (`releaseAllowed: false`) until a person approves the
exact edition and territories. Tier C/D/X and blocked sources cannot enter the
catalog through this importer.

The current review wave contains 28 distinct books: nine non-overlapping
SuttaCentral collections and nineteen standalone Project Gutenberg works. It
deliberately excludes additional Bible editions and the SuttaCentral
Dhammapada, which would duplicate books already available in Landfall. Every
entry records immutable source checksums and remains marked
`humanReviewRequiredBeforeMerge` until reviewed.

Run the importer against pinned local source checkouts, then run the quality
gate:

```bash
python3 tools/import_open_religion.py \
  --workbook-json /path/to/workbook-data.json \
  --suttacentral-editions /path/to/suttacentral-editions \
  --curated-gutenberg-dir /path/to/reviewed-gutenberg-output \
  --bundled-manifest /path/to/landfall/Classics/manifest.json \
  --write
python3 tools/editorial_quality.py
```
