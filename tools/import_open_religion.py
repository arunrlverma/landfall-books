#!/usr/bin/env python3
"""Build Landfall's rights-first open religion collection.

This importer deliberately publishes only workbook Tier-A sources with an
explicit public-domain dedication or CC0 grant.  The broader workbook research
is retained as structured JSON, but B/C/D/X rows never enter ``catalog.json``.

The command is deterministic: identical pinned source trees and ZIP archives
produce identical Markdown, catalog entries, provenance, and checksums.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import unicodedata
import zipfile
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "books"
CATALOG = ROOT / "catalog.json"
RESEARCH = ROOT / "research" / "open-religion"
RIGHTS = ROOT / "rights" / "open-religion.json"
COLLECTION = ROOT / "collections" / "open-religion.json"

OEB_COMMIT = "1965127de5c3c103af3fdbc9288c1abec5f39994"
SUTTACENTRAL_COMMIT = "9783fcb047598d2957c41b6f1c30f5532d0537a7"
RETRIEVED_AT = "2026-08-09"

WEB_EDITIONS = {
    "eng-web": {
        "title": "World English Bible — Ecumenical Edition",
        "slug": "world-english-bible-ecumenical-edition",
        "zip": "eng-web_readaloud.zip",
        "url": "https://ebible.org/find/show.php?id=eng-web",
        "blurb": "A complete modern-English ecumenical Bible edition dedicated to the public domain.",
    },
    "engwebp": {
        "title": "World English Bible — Protestant Edition",
        "slug": "world-english-bible-protestant-edition",
        "zip": "engwebp_readaloud.zip",
        "url": "https://ebible.org/find/show.php?id=engwebp",
        "blurb": "A complete modern-English Protestant Bible edition dedicated to the public domain.",
    },
    "eng-web-c": {
        "title": "World English Bible — Catholic Edition",
        "slug": "world-english-bible-catholic-edition",
        "zip": "eng-web-c_readaloud.zip",
        "url": "https://ebible.org/find/show.php?id=eng-web-c",
        "blurb": "A complete modern-English Catholic Bible edition dedicated to the public domain.",
    },
}

SUTTACENTRAL_EDITIONS = {
    "an": ("Numbered Discourses", "numbered-discourses-suttacentral"),
    "dhp": ("Sayings of the Dhamma", "sayings-of-the-dhamma-suttacentral"),
    "dn": ("Long Discourses", "long-discourses-suttacentral"),
    "iti": ("So It Was Said", "so-it-was-said-suttacentral"),
    "mn": ("Middle Discourses", "middle-discourses-suttacentral"),
    "sn": ("Linked Discourses", "linked-discourses-suttacentral"),
    "snp": ("Anthology of Discourses", "anthology-of-discourses-suttacentral"),
    "thag": ("Verses of the Senior Monks", "verses-of-the-senior-monks-suttacentral"),
    "thig": ("Verses of the Senior Nuns", "verses-of-the-senior-nuns-suttacentral"),
    "ud": ("Heartfelt Sayings", "heartfelt-sayings-suttacentral"),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_text(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def normalized_text_snapshot(data: bytes) -> bytes:
    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    return ("\n".join(line.rstrip() for line in text.splitlines()) + "\n").encode("utf-8")


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def workbook_rows(workbook: dict, sheet: str) -> list[dict]:
    values = workbook[sheet]["values"]
    headers = [str(value) if value is not None else "" for value in values[0]]
    return [
        {headers[index]: value for index, value in enumerate(row) if headers[index]}
        for row in values[1:]
        if any(value is not None for value in row)
    ]


def compact_blank_lines(lines: Iterable[str]) -> str:
    out: list[str] = []
    for raw in lines:
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            if out and out[-1]:
                out.append("")
            continue
        out.append(line)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out) + "\n"


INLINE_USFM = re.compile(r"\\(?:wj|add|nd|pn|qt|bk|it|bd|bdit|em|sc|k|no|sup)\*?")
FOOTNOTE_USFM = re.compile(r"\\(?:f|x)\s.*?\\(?:f|x)\*", re.DOTALL)


def clean_usfm_text(text: str) -> str:
    text = FOOTNOTE_USFM.sub("", text)
    text = INLINE_USFM.sub("", text)
    text = re.sub(r"\\[a-zA-Z0-9]+\*?", "", text)
    return re.sub(r"\s+", " ", text).strip()


def oeb_markdown(path: Path) -> tuple[str, str]:
    title = re.sub(r"^\d+-", "", path.stem)
    lines = [f"# {title}", "by the Open English Bible project", ""]
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            lines.append(" ".join(paragraph))
            lines.append("")
            paragraph.clear()

    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.startswith("\\"):
            cleaned = clean_usfm_text(raw)
            if cleaned:
                paragraph.append(cleaned)
            continue
        marker, _, payload = raw[1:].partition(" ")
        payload = clean_usfm_text(payload)
        marker = marker.rstrip("*")
        if marker in {"id", "ide", "h", "toc1", "toc2", "rem", "periph", "mt", "mt1", "mt2", "mt3"}:
            continue
        if marker == "c":
            flush()
            lines.extend([f"## Chapter {payload}", ""])
        elif marker in {"s", "s2", "ms"} and payload:
            flush()
            lines.extend([f"### {payload}", ""])
        elif marker == "v":
            _, _, verse = payload.partition(" ")
            verse = clean_usfm_text(verse)
            if verse:
                paragraph.append(verse)
        elif marker in {"p", "m", "pi", "nb", "b"}:
            flush()
            if payload:
                paragraph.append(payload)
        elif marker.startswith("q") or marker == "d":
            flush()
            if payload:
                lines.extend([payload, ""])
        elif payload:
            paragraph.append(payload)
    flush()
    return title, compact_blank_lines(lines)


def web_markdown(edition: dict, path: Path) -> str:
    lines = [f"# {edition['title']}", "by Michael Paul Johnson et al.", ""]
    current_book: str | None = None
    with zipfile.ZipFile(path) as archive:
        chapter_files = sorted(
            name for name in archive.namelist()
            if name.endswith("_read.txt") and "_000_000_000_" not in name
        )
        for name in chapter_files:
            raw = archive.read(name).decode("utf-8-sig").replace("\r\n", "\n")
            rows = [row.strip() for row in raw.splitlines() if row.strip()]
            if len(rows) < 3:
                continue
            book = rows[0].rstrip(".")
            chapter = rows[1].rstrip(".")
            if book != current_book:
                lines.extend([f"## {book}", ""])
                current_book = book
            lines.extend([f"### {chapter}", "", " ".join(rows[2:]), ""])
    return compact_blank_lines(lines)


class MainMatterParser(HTMLParser):
    """Extract readable Markdown blocks from a SuttaCentral generated edition."""

    HEADINGS = {f"h{level}": level for level in range(1, 7)}
    BLOCKS = {"p", "blockquote", "li"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.main_depth = 0
        self.skip_depth = 0
        self.block: str | None = None
        self.buffer: list[str] = []
        self.lines: list[str] = []
        self.metadata: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and values.get("name") and values.get("content"):
            self.metadata[str(values["name"])] = str(values["content"])
        if not self.main_depth:
            if tag == "section" and values.get("id") == "mainmatter":
                self.main_depth = 1
            return
        # HTMLParser balances XHTML-style self-closing tags by calling both
        # handlers. Counting every tag therefore keeps the generated editions'
        # nested sections aligned, including their many <br/> verse breaks.
        self.main_depth += 1
        if self.skip_depth:
            self.skip_depth += 1
            return
        if tag in {"nav", "script", "style"}:
            self.skip_depth = 1
            return
        if tag in self.HEADINGS or tag in self.BLOCKS:
            self.flush()
            self.block = tag
        elif tag == "br":
            self.flush(keep_block=True)

    def handle_endtag(self, tag: str) -> None:
        if not self.main_depth:
            return
        if self.skip_depth:
            self.skip_depth -= 1
        elif tag == self.block:
            self.flush()
            self.block = None
        self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.main_depth and not self.skip_depth:
            normalized = re.sub(r"\s+", " ", data)
            if normalized.strip():
                self.buffer.append(normalized)

    def flush(self, keep_block: bool = False) -> None:
        text = re.sub(r"\s+", " ", "".join(self.buffer)).strip()
        self.buffer.clear()
        if not text:
            return
        if self.block in self.HEADINGS:
            level = min(4, max(2, self.HEADINGS[self.block]))
            self.lines.extend([f"{'#' * level} {text}", ""])
        else:
            self.lines.extend([text, ""])
        if not keep_block:
            self.block = None


def suttacentral_markdown(path: Path, title: str) -> tuple[str, dict[str, str]]:
    parser = MainMatterParser()
    parser.feed(path.read_text(encoding="utf-8"))
    author = parser.metadata.get("author", "Bhikkhu Sujato")
    lines = [f"# {title}", f"translated by {author}", "", *parser.lines]
    return compact_blank_lines(lines), parser.metadata


def catalog_entry(slug: str, title: str, author: str, blurb: str, data: bytes) -> dict:
    return {
        "slug": slug,
        "title": title,
        "author": author,
        "category": "religion",
        "blurb": blurb,
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "collection": "open-religion",
    }


def rights_entry(
    entry: dict,
    *,
    tradition: str,
    source_name: str,
    source_url: str,
    source_version: str,
    source_path: str,
    source_sha256: str,
    license_basis: str,
    license_evidence_url: str,
    license_evidence_path: str,
    license_evidence_sha256: str,
    minimum_content_bytes: int,
    attribution: str,
    trademark: str | None = None,
) -> dict:
    return {
        "slug": entry["slug"],
        "title": entry["title"],
        "tradition": tradition,
        "workbookRightsTier": "A",
        "publicationState": "release-candidate",
        "humanReviewRequiredBeforeMerge": True,
        "sourceName": source_name,
        "sourceURL": source_url,
        "sourceVersion": source_version,
        "sourcePath": source_path,
        "sourceRetrievedAt": RETRIEVED_AT,
        "sourceSha256": source_sha256,
        "contentSha256": entry["sha256"],
        "minimumContentBytes": minimum_content_bytes,
        "licenseOrPublicDomainBasis": license_basis,
        "licenseEvidenceURL": license_evidence_url,
        "licenseEvidencePath": license_evidence_path,
        "licenseEvidenceSha256": license_evidence_sha256,
        "approvedTerritories": ["worldwide"],
        "commercialUseAllowed": True,
        "derivativesAllowed": True,
        "allowedCapabilities": [
            "display", "download", "narration", "search", "annotation",
            "simplification", "summarization", "translation",
        ],
        "requiredAttribution": attribution,
        "trademarkConstraint": trademark,
    }


def build(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    workbook = json.loads(args.workbook_json.read_text(encoding="utf-8"))
    research = {
        "tradition-matrix.json": workbook_rows(workbook, "Tradition Matrix"),
        "source-registry.json": workbook_rows(workbook, "Source Registry"),
        "launch-library.json": workbook_rows(workbook, "Launch Library"),
        "gutenberg-discovery.json": workbook_rows(workbook, "PG Discovery"),
        "rights-checklist.json": workbook_rows(workbook, "Rights Checklist"),
        "blocked-sources.json": workbook_rows(workbook, "Blocked Sources"),
    }
    launch_tiers = Counter(str(row.get("Rights tier") or "Unknown") for row in research["launch-library.json"])
    pg_screens = Counter(str(row.get("Rights screen") or "Unknown") for row in research["gutenberg-discovery.json"])
    research["summary.json"] = {
        "sourceWorkbook": "made_landfall_open_religion_library_research.xlsx",
        "sourceWorkbookDate": "2026-08-09",
        "launchLibraryRows": len(research["launch-library.json"]),
        "launchRightsTiers": dict(sorted(launch_tiers.items())),
        "gutenbergDiscoveryRows": len(research["gutenberg-discovery.json"]),
        "gutenbergRightsScreens": dict(sorted(pg_screens.items())),
        "automaticallyImportedRule": "Exact Tier-A source artifacts only",
        "releaseCandidateBooks": 57,
    }

    generated: list[tuple[dict, bytes]] = []
    rights: list[dict] = []
    license_evidence_files: dict[str, bytes] = {
        "rights/evidence/open-english-bible-license.txt": normalized_text_snapshot((args.oeb_source / "LICENSE").read_bytes()),
        "rights/evidence/suttacentral-editions-license.txt": normalized_text_snapshot((args.suttacentral_editions / "LICENSE").read_bytes()),
    }

    usfm_dir = args.oeb_source / "artifacts" / "us-release" / "usfm"
    for source in sorted(usfm_dir.glob("*.usfm")):
        if source.name.startswith("00-"):
            continue
        title, markdown = oeb_markdown(source)
        slug = f"open-english-bible-{slugify(title)}"
        data = markdown.encode("utf-8")
        entry = catalog_entry(
            slug, f"{title} — Open English Bible", "Open English Bible project",
            f"{title} in the current Open English Bible release, an unrestricted modern-English translation.", data,
        )
        generated.append((entry, data))
        rights.append(rights_entry(
            entry,
            tradition="Christianity",
            source_name="Open English Bible",
            source_url="https://github.com/openenglishbible/Open-English-Bible",
            source_version=OEB_COMMIT,
            source_path=f"artifacts/us-release/usfm/{source.name}",
            source_sha256=sha256_path(source),
            license_basis="CC0 1.0 Universal public-domain dedication",
            license_evidence_url="https://github.com/openenglishbible/Open-English-Bible/blob/master/LICENSE",
            license_evidence_path="rights/evidence/open-english-bible-license.txt",
            license_evidence_sha256=sha256_bytes(license_evidence_files["rights/evidence/open-english-bible-license.txt"]),
            minimum_content_bytes=1_000,
            attribution="Open English Bible project; source and version preserved in this ledger.",
        ))

    for edition in WEB_EDITIONS.values():
        source = args.web_zip_dir / edition["zip"]
        with zipfile.ZipFile(source) as archive:
            copyright_evidence = archive.read("copr.htm")
        evidence_path = f"rights/evidence/{edition['slug']}-copyright.html"
        copyright_evidence = normalized_text_snapshot(copyright_evidence)
        license_evidence_files[evidence_path] = copyright_evidence
        data = web_markdown(edition, source).encode("utf-8")
        entry = catalog_entry(
            edition["slug"], edition["title"], "Johnson, Michael Paul; contributors",
            edition["blurb"], data,
        )
        generated.append((entry, data))
        rights.append(rights_entry(
            entry,
            tradition="Christianity",
            source_name="World English Bible",
            source_url=edition["url"],
            source_version="readaloud archive dated 2026-08-07",
            source_path=edition["zip"],
            source_sha256=sha256_path(source),
            license_basis="Public-domain dedication",
            license_evidence_url="https://ebible.org/eng-web/copyright.htm",
            license_evidence_path=evidence_path,
            license_evidence_sha256=sha256_bytes(copyright_evidence),
            minimum_content_bytes=3_000_000,
            attribution="World English Bible; Michael Paul Johnson and contributors.",
            trademark="Modified editions must not be represented as an unmodified World English Bible edition.",
        ))

    for code, (title, slug) in SUTTACENTRAL_EDITIONS.items():
        candidates = list((args.suttacentral_editions / "en" / "sujato" / code / "html").glob("*.html"))
        if len(candidates) != 1:
            raise ValueError(f"expected one generated SuttaCentral HTML edition for {code}, found {len(candidates)}")
        source = candidates[0]
        markdown, metadata = suttacentral_markdown(source, title)
        data = markdown.encode("utf-8")
        description = metadata.get("description") or f"A modern English translation of {title}."
        entry = catalog_entry(slug, title, "Sujato, Bhikkhu (translator)", description, data)
        generated.append((entry, data))
        rights.append(rights_entry(
            entry,
            tradition="Buddhism",
            source_name="SuttaCentral Editions / Bilara Data",
            source_url=f"https://github.com/suttacentral/editions/tree/main/en/sujato/{code}",
            source_version=SUTTACENTRAL_COMMIT,
            source_path=str(source.relative_to(args.suttacentral_editions)),
            source_sha256=sha256_path(source),
            license_basis="CC0 1.0 Universal public-domain dedication",
            license_evidence_url="https://github.com/suttacentral/editions/blob/main/LICENSE",
            license_evidence_path="rights/evidence/suttacentral-editions-license.txt",
            license_evidence_sha256=sha256_bytes(license_evidence_files["rights/evidence/suttacentral-editions-license.txt"]),
            minimum_content_bytes=50_000,
            attribution="Translated by Bhikkhu Sujato; generated by SuttaCentral Editions from published Bilara data.",
        ))

    slugs = [entry["slug"] for entry, _ in generated]
    if len(slugs) != len(set(slugs)):
        raise ValueError("generated slugs are not unique")
    if len(generated) != 57:
        raise ValueError(f"expected 57 release candidates, generated {len(generated)}")

    if args.write:
        RESEARCH.mkdir(parents=True, exist_ok=True)
        (ROOT / "rights").mkdir(exist_ok=True)
        (ROOT / "collections").mkdir(exist_ok=True)
        for relative_path, evidence in license_evidence_files.items():
            target = ROOT / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(evidence)
        for filename, rows in research.items():
            (RESEARCH / filename).write_text(json_text(rows), encoding="utf-8")
        for entry, data in generated:
            (BOOKS / f"{entry['slug']}.md").write_bytes(data)

        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        replacement = {entry["slug"]: entry for entry, _ in generated}
        catalog = [entry for entry in catalog if entry["slug"] not in replacement]
        catalog.extend(entry for entry, _ in generated)
        CATALOG.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

        RIGHTS.write_text(json_text({
            "schemaVersion": 1,
            "generatedAt": RETRIEVED_AT,
            "policy": "Only exact Tier-A source artifacts enter the release-candidate catalog; human review is required before merge.",
            "entries": sorted(rights, key=lambda row: row["slug"]),
        }), encoding="utf-8")
        COLLECTION.write_text(json_text({
            "id": "open-religion",
            "title": "Open Religion Library",
            "generatedAt": RETRIEVED_AT,
            "releaseCandidateCount": len(generated),
            "slugs": sorted(slugs),
        }), encoding="utf-8")
    return [entry for entry, _ in generated], rights


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook-json", type=Path, required=True)
    parser.add_argument("--oeb-source", type=Path, required=True)
    parser.add_argument("--suttacentral-editions", type=Path, required=True)
    parser.add_argument("--web-zip-dir", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    entries, _ = build(args)
    print(f"PASS: generated {len(entries)} rights-verified release candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
