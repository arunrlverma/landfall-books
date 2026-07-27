# landfall-books

The deep shelf behind [Landfall](https://madelandfall.com): ~1,000 public-domain
books, cleaned by the same deterministic pipeline as the app's bundled classics
(Project Gutenberg boilerplate stripped, paragraphs unwrapped, chapter structure
normalized, openings cleaned — zero prose altered), and filtered to a
conservative worldwide rights rule (every author and translator dead 70+ years,
unknowns excluded).

- `catalog.json` — the searchable index the app fetches
- `books/<slug>.md` — one cleaned text per book

Served as static files; the app downloads a book once on first open.
All texts are in the public domain. © 2026 NextBase LLC for the tooling.
