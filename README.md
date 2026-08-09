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

`tools/import_open_religion.py` converts the research workbook into a guarded
content collection. It imports only exact Tier-A source artifacts carrying an
explicit CC0 or public-domain dedication. Tier B/C/D rows remain research; Tier
X and blocked sources can never enter the catalog through this importer.

The current release candidate contains 57 books: 44 released Open English Bible
books, three complete World English Bible editions, and ten SuttaCentral
translations. Every entry records the immutable upstream commit or archive
checksum and remains marked `humanReviewRequiredBeforeMerge` until reviewed.

Run the importer against pinned local source checkouts, then run the quality
gate:

```bash
python3 tools/import_open_religion.py \
  --workbook-json /path/to/workbook-data.json \
  --oeb-source /path/to/Open-English-Bible \
  --suttacentral-editions /path/to/suttacentral-editions \
  --web-zip-dir /path/to/world-english-bible-zips \
  --write
python3 tools/editorial_quality.py
```
