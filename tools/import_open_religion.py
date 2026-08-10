#!/usr/bin/env python3
"""Build Landfall's deduplicated, rights-first open religion collection.

The release-candidate collection combines exact Tier-A source artifacts with a
small, reviewed Tier-B Project Gutenberg set. Tier-B candidates remain blocked
from release until a human completes the territory and edition review.

The command is deterministic: identical pinned source trees and reviewed files
produce identical Markdown, catalog entries, provenance, and checksums.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "books"
CATALOG = ROOT / "catalog.json"
RESEARCH = ROOT / "research" / "open-religion"
RIGHTS = ROOT / "rights" / "open-religion.json"
COLLECTION = ROOT / "collections" / "open-religion.json"

SUTTACENTRAL_COMMIT = "9783fcb047598d2957c41b6f1c30f5532d0537a7"
RETRIEVED_AT = "2026-08-09"

SUTTACENTRAL_EDITIONS = {
    "an": ("Numbered Discourses", "numbered-discourses-suttacentral"),
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
        "releaseAllowed": True,
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


def normalized_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"\b(?:the|a|an)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def curated_gutenberg_rights(entry: dict, record: dict) -> dict:
    artifacts = [
        {"gutenbergID": pgid, "sourceURL": url, "sourceSha256": digest}
        for pgid, url, digest in zip(
            record["gutenbergIDs"], record["sourceURLs"], record["sourceSha256s"]
        )
    ]
    return {
        "slug": entry["slug"],
        "title": entry["title"],
        "tradition": "Cross-tradition",
        "workbookRightsTier": "B",
        "publicationState": "release-candidate",
        "releaseAllowed": False,
        "humanReviewRequiredBeforeMerge": True,
        "sourceName": "Project Gutenberg / Gutendex",
        "sourceURL": artifacts[0]["sourceURL"],
        "sourceVersion": "Gutendex live metadata checked 2026-08-09",
        "sourcePath": ", ".join(str(row["gutenbergID"]) for row in artifacts),
        "sourceRetrievedAt": RETRIEVED_AT,
        "sourceSha256": artifacts[0]["sourceSha256"],
        "sourceArtifacts": artifacts,
        "contentSha256": entry["sha256"],
        "minimumContentBytes": 25_000,
        "licenseOrPublicDomainBasis": (
            "Workbook Tier-B conservative life-plus-70 contributor screen and current "
            "Gutendex copyright=false signal; exact edition and release territories require human review."
        ),
        "licenseEvidenceURL": "https://www.gutenberg.org/policy/permission.html",
        "licenseEvidencePath": None,
        "licenseEvidenceSha256": None,
        "approvedTerritories": [],
        "commercialUseAllowed": None,
        "derivativesAllowed": None,
        "allowedCapabilities": [],
        "requiredAttribution": "Project Gutenberg source IDs and immutable source hashes are preserved in this ledger.",
        "trademarkConstraint": "Do not represent modified files as official Project Gutenberg editions.",
    }


def build(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    workbook = json.loads(args.workbook_json.read_text(encoding="utf-8"))
    curated_manifest = json.loads((args.curated_gutenberg_dir / "manifest.json").read_text(encoding="utf-8"))
    research = {
        "tradition-matrix.json": workbook_rows(workbook, "Tradition Matrix"),
        "source-registry.json": workbook_rows(workbook, "Source Registry"),
        "launch-library.json": workbook_rows(workbook, "Launch Library"),
        "gutenberg-discovery.json": workbook_rows(workbook, "PG Discovery"),
        "rights-checklist.json": workbook_rows(workbook, "Rights Checklist"),
        "blocked-sources.json": workbook_rows(workbook, "Blocked Sources"),
        "curated-gutenberg.json": curated_manifest,
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
        "automaticallyImportedRule": "Nine exact Tier-A artifacts plus nineteen reviewed Tier-B Gutenberg candidates; all require human review before merge",
        "releaseCandidateBooks": 28,
    }

    generated: list[tuple[dict, bytes]] = []
    rights: list[dict] = []
    license_evidence_files: dict[str, bytes] = {
        "rights/evidence/suttacentral-editions-license.txt": normalized_text_snapshot((args.suttacentral_editions / "LICENSE").read_bytes()),
    }

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

    for record in curated_manifest:
        source = args.curated_gutenberg_dir / "books" / f"{record['slug']}.md"
        data = source.read_bytes()
        if len(data) != record["bytes"] or sha256_bytes(data) != record["sha256"]:
            raise ValueError(f"{record['slug']}: curated Gutenberg manifest checksum mismatch")
        summary = next(iter(record.get("summaries") or []), "")
        blurb = summary or f"A reviewed public-domain candidate sourced from Project Gutenberg: {record['title']}."
        entry = catalog_entry(record["slug"], record["title"], record["author"], blurb, data)
        entry["category"] = record["category"]
        if len(record["gutenbergIDs"]) == 1:
            entry["gutenbergID"] = record["gutenbergIDs"][0]
        else:
            entry["gutenbergIDs"] = record["gutenbergIDs"]
        generated.append((entry, data))
        rights.append(curated_gutenberg_rights(entry, record))

    slugs = [entry["slug"] for entry, _ in generated]
    if len(slugs) != len(set(slugs)):
        raise ValueError("generated slugs are not unique")
    if len(generated) != 28:
        raise ValueError(f"expected 28 distinct release candidates, generated {len(generated)}")

    previous_collection = json.loads(COLLECTION.read_text(encoding="utf-8")) if COLLECTION.exists() else {"slugs": []}
    previous_slugs = set(previous_collection.get("slugs", []))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    retained = [entry for entry in catalog if entry["slug"] not in previous_slugs]
    bundled = json.loads(args.bundled_manifest.read_text(encoding="utf-8"))
    occupied_titles = {normalized_title(entry["title"]): entry["title"] for entry in [*retained, *bundled]}
    occupied_ids = {
        int(value)
        for entry in [*retained, *bundled]
        for value in ([entry.get("gutenbergID")] if entry.get("gutenbergID") else entry.get("gutenbergIDs", []))
    }
    for entry, _ in generated:
        title_key = normalized_title(entry["title"])
        if title_key in occupied_titles:
            raise ValueError(f"{entry['title']}: duplicates existing title {occupied_titles[title_key]}")
        ids = ([entry.get("gutenbergID")] if entry.get("gutenbergID") else entry.get("gutenbergIDs", []))
        overlap = occupied_ids.intersection(ids)
        if overlap:
            raise ValueError(f"{entry['title']}: duplicates existing Gutenberg ID(s) {sorted(overlap)}")
        occupied_titles[title_key] = entry["title"]
        occupied_ids.update(ids)

    if args.write:
        RESEARCH.mkdir(parents=True, exist_ok=True)
        (ROOT / "rights").mkdir(exist_ok=True)
        (ROOT / "collections").mkdir(exist_ok=True)
        stale_evidence = [
            "rights/evidence/open-english-bible-license.txt",
            "rights/evidence/world-english-bible-catholic-edition-copyright.html",
            "rights/evidence/world-english-bible-ecumenical-edition-copyright.html",
            "rights/evidence/world-english-bible-protestant-edition-copyright.html",
        ]
        for relative_path in stale_evidence:
            target = ROOT / relative_path
            if target.exists():
                target.unlink()
        for relative_path, evidence in license_evidence_files.items():
            target = ROOT / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(evidence)
        for filename, rows in research.items():
            (RESEARCH / filename).write_text(json_text(rows), encoding="utf-8")
        for entry, data in generated:
            (BOOKS / f"{entry['slug']}.md").write_bytes(data)

        replacement = {entry["slug"]: entry for entry, _ in generated}
        stale_slugs = previous_slugs - set(replacement)
        for slug in stale_slugs:
            stale = BOOKS / f"{slug}.md"
            if stale.exists():
                stale.unlink()
        catalog = [entry for entry in catalog if entry["slug"] not in previous_slugs and entry["slug"] not in replacement]
        catalog.extend(entry for entry, _ in generated)
        CATALOG.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

        RIGHTS.write_text(json_text({
            "schemaVersion": 1,
            "generatedAt": RETRIEVED_AT,
            "policy": "Tier-A artifacts and explicitly blocked Tier-B candidates enter this review branch; human rights and editorial review is required before merge, and Tier-B releaseAllowed remains false.",
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
    parser.add_argument("--suttacentral-editions", type=Path, required=True)
    parser.add_argument("--curated-gutenberg-dir", type=Path, required=True)
    parser.add_argument("--bundled-manifest", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    entries, _ = build(args)
    print(f"PASS: generated {len(entries)} guarded release candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
