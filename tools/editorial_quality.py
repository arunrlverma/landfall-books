#!/usr/bin/env python3
"""Audit and remove high-confidence ebook-production residue.

The cleaner is intentionally conservative: it removes tail-end transcriber
appendices and a small reviewed set of inline notes, never rewrites prose. It
then refreshes catalog byte counts and SHA-256 hashes. Running without
``--write`` is a strict catalog/content quality gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "books"
CATALOG = ROOT / "catalog.json"
OPEN_RELIGION_RIGHTS = ROOT / "rights" / "open-religion.json"

TRANSCRIBER = re.compile(r"transcriber[’']s? notes?", re.I)
RAW_HTML = re.compile(r"</?(?:i|b|em|strong|p|div|span)(?:\s[^>]*)?>", re.I)
INLINE_NOTE = re.compile(r"\s*[\[(](?:_)?transcriber[’']s? note:.*?(?:_)?[\])]", re.I)
END_MARKER = re.compile(r"^\s*(?:#{1,6}\s*)?(?:[_*]\s*)*(?:the end|finis)[.!]?(?:\s*[_*])?\s*$", re.I)

# These editions were individually reviewed: everything after their final end
# marker is publisher advertising, a printer colophon, or a series catalog. The
# allowlist keeps this rule from deleting appendices, glossaries, or endnotes in
# books where postscript material is part of the authored edition.
REVIEWED_TRUNCATE_AFTER_END = {
    "a-little-girl-of-long-ago-or-hannah-ann-a-sequel-to-a-little",
    "a-modern-tomboy-a-story-for-girls",
    "a-village-of-vagabonds",
    "boy-scouts-in-the-canal-zone-or-the-plot-against-uncle-sam",
    "boy-scouts-in-the-north-sea-or-the-mystery-of-a-sub",
    "boy-scouts-on-hudson-bay-or-the-disappearing-fleet",
    "camp-fire-and-wigwam",
    "captain-canot-or-twenty-years-of-an-african-slaver",
    "colonial-born-a-tale-of-the-queensland-bush",
    "dave-darrin-on-mediterranean-service-or-with-dan-dalzell-on-",
    "dave-porter-and-his-rivals-or-the-chums-and-foes-of-oak-hall",
    "fair-harbor",
    "fair-margaret-a-portrait",
    "five-hundred-dollars-or-jacob-marlowe-s-secret",
    "footprints-in-the-forest",
    "from-kingdom-to-colony",
    "from-the-car-behind",
    "glory-of-youth",
    "helen-and-arthur-or-miss-thusa-s-spinning-wheel",
    "in-the-mayor-s-parlour",
    "lillian-s-vow-b-or-the-mystery-of-raleigh-house",
    "odd-numbers-being-further-chronicles-of-shorty-mccabe",
    "sally-of-missouri",
    "shakespeare-ben-jonson-beaumont-and-fletcher",
    "shorty-mccabe-on-the-job",
    "the-belle-of-bowling-green",
    "the-big-bow-mystery",
    "the-boy-scout-treasure-hunters-or-the-lost-treasure-of-buffa",
    "the-car-of-destiny",
    "the-copper-house-b-a-detective-story",
    "the-copper-princess-a-story-of-lake-superior-mines",
    "the-cruise-of-the-nona-b-the-story-of-a-cruise-from-holyhead",
    "the-expedition-to-borneo-of-h-m-s-dido-for-the-suppression-o",
    "the-grammar-school-boys-of-gridley-or-dick-co-start-things-m",
    "the-guarded-heights",
    "the-herapath-property",
    "the-little-colonel-maid-of-honor",
    "the-little-colonel-s-christmas-vacation",
    "the-ocean-wireless-boys-and-the-naval-code",
    "the-opal-serpent",
    "the-range-boss",
    "the-religious-experience-of-the-roman-people-from-the-earlie",
    "the-rover-boys-on-a-hunt-or-the-mysterious-house-in-the-wood",
    "the-rover-boys-on-the-farm-or-last-days-at-putnam-hall",
    "the-servant-s-behaviour-book-b-or-hints-on-manners-and-dress",
    "the-sleeping-beauty",
    "the-sunbridge-girls-at-six-star-ranch",
    "the-young-oarsmen-of-lakeview",
    "uncle-sam-s-boys-as-lieutenants-or-serving-old-glory-as-line",
    "uncle-sam-s-boys-as-sergeants-or-handling-their-first-real-c",
    "uncle-sam-s-boys-in-the-philippines-or-following-the-flag-ag",
    "uncle-sam-s-boys-in-the-ranks-or-two-recruits-in-the-united-",
    "under-the-rebel-s-reign",
}

# Reviewed mid-book production notes. Ranges are 1-based and inclusive, based
# on the immutable source editions in this repository.
REVIEWED_DELETE_RANGES = {
    "a-budget-of-paradoxes-volume-ii": [(2975, 2975)],
    "essays-by-ralph-waldo-emerson": [(376, 376), (391, 391)],
    "facts-about-champagne-and-other-sparkling-wines": [(479, 481)],
    "microcosmography-or-a-piece-of-the-world-discovered-in-essay": [(1713, 1713)],
    "the-life-of-charles-dickens-vol-i-iii-complete": [(2303, 2317)],
    "under-the-rebel-s-reign": [(1431, 1431)],
}

REVIEWED_REPLACEMENTS = {
    "the-teacher-or-moral-influences-employed-in-the-instruction-": {
        "[Transcriber's Note: The footnote marker for the following footnote is missing.] ": "",
    },
}


def clean_lines(slug: str, lines: list[str]) -> list[str]:
    original_count = len(lines)
    hits = [i for i, line in enumerate(lines) if TRANSCRIBER.search(line)]

    # A production appendix in the final ten percent is never part of the
    # authored work. Tail-only truncation avoids guessing about prose.
    if hits and hits[0] / max(1, original_count) >= 0.90:
        lines = lines[: hits[0]]

    if slug in REVIEWED_TRUNCATE_AFTER_END:
        endings = [i for i, line in enumerate(lines) if END_MARKER.match(line)]
        if endings:
            lines = lines[: endings[-1] + 1]

    ranges = REVIEWED_DELETE_RANGES.get(slug, [])
    if ranges:
        removed = {line for start, end in ranges for line in range(start, end + 1)}
        lines = [line for number, line in enumerate(lines, 1) if number not in removed]

    # A handful of explanatory notes were embedded in otherwise valid prose.
    # Remove the bracketed editorial aside and keep the sentence around it.
    lines = [INLINE_NOTE.sub("", line) for line in lines]
    for old, new in REVIEWED_REPLACEMENTS.get(slug, {}).items():
        lines = [line.replace(old, new) for line in lines]

    while lines and not lines[-1].strip():
        lines.pop()
    collapsed: list[str] = []
    for line in lines:
        if not line.strip() and collapsed and not collapsed[-1].strip():
            continue
        collapsed.append(line.rstrip())
    return collapsed


def refresh_catalog(catalog: list[dict]) -> None:
    for entry in catalog:
        path = BOOKS / f"{entry['slug']}.md"
        data = path.read_bytes()
        entry["bytes"] = len(data)
        entry["sha256"] = hashlib.sha256(data).hexdigest()


def audit(catalog: list[dict]) -> list[str]:
    problems: list[str] = []
    expected = {entry["slug"] for entry in catalog}
    actual = {path.stem for path in BOOKS.glob("*.md")}
    for slug in sorted(expected - actual):
        problems.append(f"{slug}: catalog entry has no book")
    for slug in sorted(actual - expected):
        problems.append(f"{slug}: book has no catalog entry")

    for entry in catalog:
        slug = entry["slug"]
        path = BOOKS / f"{slug}.md"
        if not path.exists():
            continue
        data = path.read_bytes()
        text = data.decode("utf-8")
        lines = text.splitlines()
        if not lines or not lines[0].startswith("# "):
            problems.append(f"{slug}: missing Markdown title")
        if len(data) != entry.get("bytes"):
            problems.append(f"{slug}: stale byte count")
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            problems.append(f"{slug}: stale sha256")
        if TRANSCRIBER.search(text):
            problems.append(f"{slug}: transcriber residue")
        if RAW_HTML.search(text):
            problems.append(f"{slug}: raw HTML residue")
        if "\ufffd" in text:
            problems.append(f"{slug}: replacement character")
        if slug in REVIEWED_TRUNCATE_AFTER_END:
            endings = [i for i, line in enumerate(lines) if END_MARKER.match(line)]
            if not endings:
                problems.append(f"{slug}: reviewed end marker is missing")
            elif any(line.strip() for line in lines[endings[-1] + 1 :]):
                problems.append(f"{slug}: publisher material remains after the end")

    if OPEN_RELIGION_RIGHTS.exists():
        rights_payload = json.loads(OPEN_RELIGION_RIGHTS.read_text(encoding="utf-8"))
        rights_entries = rights_payload.get("entries", [])
        by_slug = {entry["slug"]: entry for entry in catalog}
        seen: set[str] = set()
        required = {
            "sourceURL", "sourceVersion", "sourcePath", "sourceRetrievedAt",
            "sourceSha256", "contentSha256", "licenseOrPublicDomainBasis",
            "minimumContentBytes", "licenseEvidenceURL", "requiredAttribution",
        }
        for record in rights_entries:
            slug = record.get("slug", "<missing slug>")
            if slug in seen:
                problems.append(f"{slug}: duplicate open-religion rights record")
            seen.add(slug)
            missing = sorted(field for field in required if not record.get(field))
            if missing:
                problems.append(f"{slug}: incomplete rights record ({', '.join(missing)})")
            tier = record.get("workbookRightsTier")
            if tier not in {"A", "B"}:
                problems.append(f"{slug}: unsupported rights tier")
            if record.get("publicationState") != "release-candidate":
                problems.append(f"{slug}: unexpected publication state")
            if record.get("humanReviewRequiredBeforeMerge") is not True:
                problems.append(f"{slug}: human-review merge gate is missing")
            if tier == "A":
                if record.get("releaseAllowed") is not True:
                    problems.append(f"{slug}: Tier-A release permission is not recorded")
                if record.get("commercialUseAllowed") is not True or record.get("derivativesAllowed") is not True:
                    problems.append(f"{slug}: required commercial/derivative permission is missing")
                if record.get("approvedTerritories") != ["worldwide"]:
                    problems.append(f"{slug}: Tier-A worldwide territory approval is missing")
                evidence_path = ROOT / str(record.get("licenseEvidencePath", ""))
                if not evidence_path.is_file():
                    problems.append(f"{slug}: license evidence snapshot is missing")
                elif hashlib.sha256(evidence_path.read_bytes()).hexdigest() != record.get("licenseEvidenceSha256"):
                    problems.append(f"{slug}: license evidence checksum mismatch")
            elif tier == "B":
                if record.get("releaseAllowed") is not False:
                    problems.append(f"{slug}: Tier-B candidate is not fail-closed")
                if record.get("approvedTerritories") or record.get("commercialUseAllowed") is not None or record.get("derivativesAllowed") is not None:
                    problems.append(f"{slug}: Tier-B candidate claims unapproved rights")
                artifacts = record.get("sourceArtifacts") or []
                if not artifacts or any(not row.get("gutenbergID") or not row.get("sourceURL") or not row.get("sourceSha256") for row in artifacts):
                    problems.append(f"{slug}: Tier-B source-artifact evidence is incomplete")
            catalog_entry = by_slug.get(slug)
            if not catalog_entry:
                problems.append(f"{slug}: rights record has no catalog entry")
            elif record.get("contentSha256") != catalog_entry.get("sha256"):
                problems.append(f"{slug}: rights/content checksum mismatch")
            elif catalog_entry.get("bytes", 0) < record.get("minimumContentBytes", 0):
                problems.append(f"{slug}: generated content is unexpectedly small")
        release_slugs = {entry["slug"] for entry in catalog if entry.get("collection") == "open-religion"}
        if release_slugs != seen:
            problems.append("open-religion: catalog and rights ledger slug sets differ")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    if args.write:
        for entry in catalog:
            path = BOOKS / f"{entry['slug']}.md"
            before = path.read_text(encoding="utf-8")
            after = "\n".join(clean_lines(entry["slug"], before.splitlines())) + "\n"
            if after != before:
                path.write_text(after, encoding="utf-8")
        refresh_catalog(catalog)
        CATALOG.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    problems = audit(catalog)
    if problems:
        print("\n".join(problems))
        return 1
    print(f"PASS: {len(catalog)} books match the catalog and editorial quality gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
