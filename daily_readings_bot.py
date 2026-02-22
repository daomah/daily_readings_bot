#!/usr/bin/env python3
"""
daily_saint_bot - Generates daily Orthodox Christian scripture readings
as a formatted markdown file.

Data sources:
  - oca.org           : NKJV reading text, reading types, URL indices,
                        full feast/saint commemoration names
  - orthocal.info API : reading descriptions and day titles (weekday ordinals,
                        saint abbreviations) for occasion matching

Usage:
  python bot.py             # uses today's date
  python bot.py 2026-01-01  # uses a specific YYYY-MM-DD date
"""

import re
import sys
from datetime import date

import requests
from bs4 import BeautifulSoup

BASE_OCA = "https://www.oca.org"
ORTHOCAL_API = "https://orthocal.info/api/gregorian"

LITURGICAL_TYPES = {"Matins Gospel", "Epistle", "Gospel"}
# Reading types that only occur on Sundays (filtered out on weekdays)
SUNDAY_ONLY_TYPES = {"Matins Gospel"}

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

HASHTAGS = "#Christian #OrthodoxChristian #Bible #Scripture #Orthodox #Orthostr #Biblestr"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "daily-saint-bot/1.0"})


def _get(url):
    r = SESSION.get(url, timeout=15)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------------------
# orthocal.info — reading descriptions + day titles
# ---------------------------------------------------------------------------

def get_orthocal(year, month, day):
    """Return orthocal.info JSON for the given date."""
    return _get(f"{ORTHOCAL_API}/{year}/{month}/{day}/").json()


def _norm(ref):
    """
    Normalize a scripture reference for matching.
    Strips 'Composite N - ' prefix, removes non-alphanumeric chars except hyphens.
    Handles both '.' and ':' chapter separators (OCA vs orthocal style).
    """
    ref = re.sub(r"^Composite \d+\s*-\s*", "", ref, flags=re.IGNORECASE)
    return re.sub(r"[^\w-]", "", ref).lower()


def build_orthocal_index(orthocal_data):
    """
    Build a dict mapping normalized scripture ref → orthocal reading dict
    for quick occasion lookup by reference.
    """
    index = {}
    for r in orthocal_data.get("readings", []):
        display = r.get("display", r.get("short_display", ""))
        if display:
            index[_norm(display)] = r
    return index


# ---------------------------------------------------------------------------
# OCA daily page — reading links + commemorations
# ---------------------------------------------------------------------------

def _clean_ligatures(text):
    """Replace archaic ligatures with standard ASCII equivalents."""
    replacements = {
        "æ": "ae", "Æ": "Ae", "œ": "oe", "Œ": "Oe",
        "ć": "c",  "č": "c",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _expand_titles(text):
    """Expand abbreviated ecclesiastical titles."""
    text = re.sub(r"\bSt\.\s+", "Saint ", text)
    text = re.sub(r"\bVen\.\s+", "Venerable ", text)
    return text


def get_oca_daily(year, month, day):
    """
    Scrape the OCA daily readings page and return:
      - links: sorted list of (url_index, link_text)
      - commemorations: list of cleaned commemoration strings
    """
    url = f"{BASE_OCA}/readings/daily/{year}/{month:02d}/{day:02d}"
    soup = BeautifulSoup(_get(url).text, "lxml")

    # ── Reading links ──
    pattern = re.compile(rf"/readings/daily/{year}/{month:02d}/{day:02d}/(\d+)$")
    links = []
    seen = set()
    for a in soup.find_all("a", href=pattern):
        m = pattern.search(a["href"])
        if m:
            idx = int(m.group(1))
            if idx not in seen:
                seen.add(idx)
                links.append((idx, a.get_text(strip=True)))
    links.sort()

    # ── Commemorations ──
    # Located in the <p> after <h3>Today's commemorated feasts and saints</h3>.
    # Main feast/saint names are wrapped in <strong> tags; plain text between
    # them is supplementary info (years, minor saints) that we ignore.
    commemorations = []
    feast_h3 = soup.find("h3", string=re.compile(r"today.s commemorated", re.IGNORECASE))
    if feast_h3:
        p = feast_h3.find_next_sibling("p")
        if p:
            for strong in p.find_all("strong"):
                entry = strong.get_text(" ", strip=True)
                entry = re.sub(r"\s*\(\d{4}\)\s*$", "", entry).strip()
                entry = _clean_ligatures(entry)
                entry = _expand_titles(entry)
                if entry:
                    commemorations.append(entry)

    return links, commemorations


# ---------------------------------------------------------------------------
# OCA individual reading page — type, occasion, verse text
# ---------------------------------------------------------------------------

def get_oca_reading_page(year, month, day, index):
    """
    Fetch one OCA individual reading page and return:
      (scripture_ref, reading_type, occasion_abbrev, verse_text)

    The OCA H2 heading looks like:
      "Colossians 2:8-12 (Epistle, Circumcision)"
      "John 21:1-14 (Matins Gospel)"
      "Hebrews 7:26-8:2 (Epistle, Saint)"
      "Hebrews 10:35-11:7 (Epistle)"

    verse_text is joined from all <dd> elements in <dl class="reading">.
    Returns (None, None, None, None) on parse failure.
    """
    url = f"{BASE_OCA}/readings/daily/{year}/{month:02d}/{day:02d}/{index}"
    soup = BeautifulSoup(_get(url).text, "lxml")

    # The reading-specific H2 is the one that contains "(…)"
    heading = None
    for h2 in soup.find_all("h2"):
        text = h2.get_text(" ", strip=True)
        if "(" in text and ")" in text:
            heading = text
            break

    if not heading:
        return None, None, None, None

    ref = re.split(r"\s*\(", heading, maxsplit=1)[0].strip()

    paren_m = re.search(r"\(([^)]+)\)", heading)
    reading_type = None
    occasion_abbrev = None
    if paren_m:
        parts = [p.strip() for p in paren_m.group(1).split(",", 1)]
        raw_type = parts[0] if parts else None
        occasion_abbrev = parts[1] if len(parts) > 1 else None
        # Normalize "10th  Matins Gospel" → "Matins Gospel".
        # Only strip the ordinal when what follows is "Matins Gospel";
        # preserve it for types like "6th Hour", "3rd Hour", "9th Hour".
        if raw_type:
            reading_type = re.sub(r"^\d+\w+\s+(?=Matins Gospel)", "", raw_type).strip()

    dl = soup.find("dl", class_="reading")
    verse_parts = []
    if dl:
        for dd in dl.find_all("dd"):
            text = dd.get_text(" ", strip=True)
            if text:
                verse_parts.append(text)
    verse_text = " ".join(verse_parts) or None

    return ref, reading_type, occasion_abbrev, verse_text


# ---------------------------------------------------------------------------
# Occasion expansion — combining OCA commemorations + orthocal data
# ---------------------------------------------------------------------------

def _search_commemorations(key, commemorations):
    """
    Find the first commemoration entry that contains *key* as a whole word.
    Returns the full commemoration string or None.
    """
    if not key or not commemorations:
        return None
    pattern = re.compile(r"\b" + re.escape(key) + r"\b", re.IGNORECASE)
    for entry in commemorations:
        if pattern.search(entry):
            return entry
    return None


def build_occasion(
    occasion_abbrev,
    oca_ref,
    commemorations,
    orthocal_index,
    day_titles,
):
    """
    Build a full, human-readable occasion string.

    Strategy:
    1. Weekday ordinals (start with a digit) → prefix "the "
    2. Named feast/saint abbreviation (e.g. "Circumcision") →
       match in OCA commemorations, then orthocal feasts/saints
    3. Generic "Saint" → resolve via orthocal description for this reading,
       then match resolved key in OCA commemorations
    4. Empty occasion → look up orthocal description for this reading,
       or fall back to day title from orthocal (e.g. "30th Thursday after Pentecost")
    """
    # Normalize whitespace (OCA sometimes has "1st  reading" with double space)
    if occasion_abbrev:
        occasion_abbrev = re.sub(r"\s+", " ", occasion_abbrev).strip()

    # Discard bare positional labels like "1st reading", "2nd reading"
    if occasion_abbrev and re.fullmatch(r"\d+\w*\s+reading", occasion_abbrev, re.IGNORECASE):
        occasion_abbrev = ""

    # ── 1. Weekday ordinal ──
    if occasion_abbrev and re.match(r"\d", occasion_abbrev):
        return f"the {occasion_abbrev}"

    # ── 2. Named feast / saint (non-generic) ──
    if occasion_abbrev and occasion_abbrev.lower() not in ("saint", "the", ""):
        # Strip title prefixes to get the key word(s)
        key = re.sub(r"^(St\.?|Ven\.?|Holy|The)\s+", "", occasion_abbrev, flags=re.IGNORECASE).strip()
        match = _search_commemorations(key, commemorations)
        if match:
            # Normalize leading "The " → "the " (reads better after "reading for ")
            match = re.sub(r"^The\s+", "the ", match)
            # For saint commemorations (Repose of…, Martyrdom of…, etc.),
            # add "the " prefix so it reads "reading for the Repose of…"
            if not match.startswith("the ") and not re.match(r"^Saint\b", match, re.IGNORECASE):
                match = "the " + match
            return match
        return occasion_abbrev

    # ── 3 & 4. Generic "Saint" or empty — resolve via orthocal ──
    orthocal_desc = None
    if oca_ref:
        entry = orthocal_index.get(_norm(oca_ref))
        if entry:
            orthocal_desc = entry.get("description", "").strip()

    if orthocal_desc:
        # Weekday ordinal from orthocal
        if re.match(r"\d", orthocal_desc):
            return f"the {orthocal_desc}"
        # Saint abbreviation from orthocal — try to expand via OCA commemorations
        key = re.sub(r"^(St\.?|Ven\.?|Holy|The)\s+", "", orthocal_desc, flags=re.IGNORECASE).strip()
        match = _search_commemorations(key, commemorations)
        if match:
            match = re.sub(r"^The\s+", "the ", match)
            if not match.startswith("the ") and not re.match(r"^Saint\b", match, re.IGNORECASE):
                match = "the " + match
            return match
        return orthocal_desc

    # Final fallback: derive from day title ("Thursday of the 30th week after Pentecost")
    if day_titles:
        title = day_titles[0]
        m = re.match(r"(\w+) of the (\d+\w+) week after (.+)", title, re.IGNORECASE)
        if m:
            weekday, ordinal, feast = m.group(1), m.group(2), m.group(3)
            return f"the {ordinal} {weekday} after {feast}"
        if re.match(r"\d", title):
            return f"the {title}"
        return title

    return ""


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------

def format_markdown(today, readings, commemorations, orthocal_index, day_titles):
    weekday = WEEKDAYS[today.weekday()]
    month_name = MONTHS[today.month - 1]

    date_path = f"{today.year}/{today.month:02d}/{today.day:02d}"
    oca_daily_url = f"oca.org/readings/daily/{date_path}"
    title_date = f"{weekday}, {today.day:02d} {month_name} {today.year}"

    lines = [
        f"# [Scripture Readings for {title_date} (OCA)]({oca_daily_url})",
        "",
    ]

    is_sunday = today.weekday() == 6

    # Include all reading types; Matins Gospel is Sunday-only
    included = [
        r for r in readings
        if r["type"]
        and not (r["type"] in SUNDAY_ONLY_TYPES and not is_sunday)
    ]

    if not included:
        lines += [
            "*No readings found for this date.*",
            "",
        ]
    else:
        for r in included:
            reading_url = f"oca.org/readings/daily/{date_path}/{r['index']}"

            # Matins Gospel heading has no occasion — it's self-explanatory
            if r["type"] == "Matins Gospel":
                heading = f"Matins Gospel reading ({r['ref']})"
            else:
                occasion = build_occasion(
                    r["occasion"],
                    r["ref"],
                    commemorations,
                    orthocal_index,
                    day_titles,
                )
                if occasion:
                    heading = f"{r['type']} reading for {occasion} ({r['ref']})"
                else:
                    heading = f"{r['type']} reading ({r['ref']})"

            lines.append(f"## [{heading}]({reading_url})")
            lines.append("")

            if r["text"]:
                lines.append(f"> {r['text']}")
                lines.append("")

    lines.append(HASHTAGS)
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) > 1:
        try:
            today = date.fromisoformat(sys.argv[1])
        except ValueError:
            print(f"Error: invalid date '{sys.argv[1]}'. Expected YYYY-MM-DD.", file=sys.stderr)
            sys.exit(1)
    else:
        today = date.today()

    year, month, day = today.year, today.month, today.day
    print(f"Fetching readings for {today} …", file=sys.stderr)

    # ── orthocal.info: descriptions + day titles ──
    try:
        orthocal_data = get_orthocal(year, month, day)
        orthocal_index = build_orthocal_index(orthocal_data)
        day_titles = orthocal_data.get("titles", [])
    except requests.RequestException as e:
        print(f"Warning: could not fetch orthocal data ({e}).", file=sys.stderr)
        orthocal_index, day_titles = {}, []

    # ── OCA daily page: reading links + commemorations ──
    try:
        oca_links, commemorations = get_oca_daily(year, month, day)
    except requests.RequestException as e:
        print(f"Error fetching OCA daily page: {e}", file=sys.stderr)
        sys.exit(1)

    if not oca_links:
        print("Warning: no reading links found on OCA for this date.", file=sys.stderr)

    # ── Fetch each individual OCA reading page ──
    readings = []
    for idx, link_text in oca_links:
        print(f"  Reading {idx}: {link_text} …", file=sys.stderr)
        try:
            ref, rtype, occasion, verse_text = get_oca_reading_page(year, month, day, idx)
        except requests.RequestException as e:
            print(f"  Warning: could not fetch reading {idx}: {e}", file=sys.stderr)
            continue
        readings.append({
            "index": idx,
            "ref": ref or link_text,
            "type": rtype or "",
            "occasion": occasion or "",
            "text": verse_text or "",
        })

    markdown = format_markdown(today, readings, commemorations, orthocal_index, day_titles)
    print(markdown)


if __name__ == "__main__":
    main()
