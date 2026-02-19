# daily_readings_bot

Fetches the Orthodox Christian scripture readings for a given day and formats them as a single markdown file, ready for social media or personal notes.

## What it does

For each day, the bot:

1. Pulls the list of scripture readings from the OCA (Orthodox Church in America) website
2. Fetches the NKJV text of every reading listed for that day — Epistle, Gospel, Vespers, Hours, and any other type OCA provides
3. Resolves the full name of each feast or saint commemoration
4. Outputs a markdown file with a linked title, a heading per reading that links back to the OCA page, the passage text as a blockquote, and a standard hashtag footer

The Matins Gospel is included on Sundays only, matching standard parish practice. All other reading types are included regardless of day.

## Usage

```bash
python3 bot.py              # today's date
python3 bot.py 2026-01-18   # a specific date (YYYY-MM-DD)
```

Output goes to stdout. Redirect to save:

```bash
python3 bot.py 2026-01-18 > 18.md
```

## Setup

Requires Python 3.9+ and the packages in `requirements.txt`:

```bash
pip install -r requirements.txt
# or on Arch Linux:
sudo pacman -S python-requests python-beautifulsoup4 python-lxml
```

## Output format

```markdown
# [Scripture Readings for Sunday, 18 January 2026 (OCA)](oca.org/readings/daily/2026/01/18)

## [Matins Gospel reading (John 21:1-14)](oca.org/readings/daily/2026/01/18/1)

> After these things Jesus showed Himself again to the disciples…

## [Epistle reading for the 32nd Sunday after Pentecost (1 Timothy 1:15-17)](oca.org/readings/daily/2026/01/18/2)

> This is a faithful saying and worthy of all acceptance…

## [Gospel reading for the 32nd Sunday after Pentecost (Luke 18:35-43)](oca.org/readings/daily/2026/01/18/3)

> Then it happened, as He was coming near Jericho…

#Christian #OrthodoxChristian #Bible #Scripture #Orthodox #Orthostr #Biblestr
```

## How it works

The bot combines two data sources:

### oca.org
The primary source. For each day the bot:
- Scrapes the daily readings index page (`/readings/daily/YYYY/MM/DD`) to get the ordered list of reading links
- Scrapes each individual reading page (`/readings/daily/YYYY/MM/DD/N`) to get:
  - The reading type (`Epistle`, `Gospel`, `Matins Gospel`, `Vespers`, etc.) from the H2 heading
  - The occasion abbreviation (e.g. `Circumcision`, `Saint`, blank for weekday readings)
  - The full passage text (NKJV) from the `<dl class="reading">` element
- Scrapes the `<strong>`-tagged entries in the "Today's commemorated feasts and saints" section to get full feast and saint names (e.g. `Saint Basil the Great, Archbishop of Caesarea in Cappadocia`)

All reading types OCA lists are included in the output — `Epistle`, `Gospel`, `Vespers`, `6th Hour`, and others. `Matins Gospel` is restricted to Sundays, matching standard parish practice.

### orthocal.info API
A secondary source, used to fill in occasion information that OCA's reading pages don't provide inline:
- **Weekday ordinals** — when a reading has no feast occasion, the orthocal `titles` field supplies the liturgical week designation (e.g. `Thursday of the 30th week after Pentecost` → `the 30th Thursday after Pentecost`)
- **Saint abbreviations** — when OCA's reading page lists only `Saint` as the occasion (without specifying which one), the orthocal `readings[].description` field identifies the saint (e.g. `St Basil`), which is then matched against the full OCA commemoration names

## Resources

| Resource | URL | Role |
|---|---|---|
| OCA Scripture Readings | https://www.oca.org/readings/daily | Source of all reading text and URLs |
| orthocal.info API | https://orthocal.info/api/gregorian/YYYY/M/D/ | Liturgical week titles and reading descriptions |
| OCA Feasts and Saints | https://www.oca.org/saints/all-lives | Background on commemorated saints |

## License and content notice

The **code** in this repository is released under the [MIT License](LICENSE).

The **output** produced by the bot contains scripture text from the New King James Version (NKJV), copyright © 1982 by Thomas Nelson. OCA displays this text under a courtesy arrangement with Thomas Nelson; that arrangement does not extend to redistribution of the generated files. The output is intended for personal devotional use.
