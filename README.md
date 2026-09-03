# landfall-books

The deep shelf behind [Landfall](https://madelandfall.com): ~1,000 public-domain
books, cleaned by the same deterministic pipeline as the app's bundled classics
(Project Gutenberg boilerplate stripped, paragraphs unwrapped, chapter structure
normalized, openings cleaned — zero prose altered), and filtered to a
conservative worldwide rights rule (every author and translator dead 70+ years,
unknowns excluded).

- `catalog.json` — the searchable index Landfall fetches
- `editions/catalog.json` — the index the faith/philosophy editions fetch: every
  entry in `catalog.json`, in the same order, followed by the titles those
  editions ship. The extra entries carry an `editions` list naming the editions
  that show them. Landfall never reads this file, so a title landing here is
  invisible to the shipping app until it also lands in `catalog.json`.
- `books/<slug>.md` — one cleaned text per book, shared by both indexes
- `famous-poems.json` — the reviewed ordering and provenance for Landfall's
  100 individually readable Famous Poems

Served as static files; the app downloads a book once on first open.
All texts are in the public domain. © 2026 NextBase LLC for the tooling.

The Famous Poems shelf uses original English works whose authors died before
1956, preserving the catalog's conservative life-plus-70 rule rather than
relying only on U.S. publication status. Poem transcriptions come from
[PoetryDB](https://poetrydb.org/)'s public-domain corpus; each item keeps its
exact source title, author, editorial rank, byte count, and SHA-256 digest.
