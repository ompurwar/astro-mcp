# astro-mcp

An MCP server for Vedic astrology and panchang calculations, powered by
[PyJHora](https://github.com/naturalstupid/PyJHora) and the Swiss Ephemeris.

## Tools

| Tool | Returns |
| --- | --- |
| `get_panchang` | Sunrise, sunset, vara, tithi, nakshatra, yoga and karana, with start and end times. |
| `get_kundli` | D1 birth chart: lagna and planets with sign, degree, nakshatra, pada, whole-sign house and retrograde state. |
| `get_dashas` | Vimshottari mahadasha timeline, the balance at birth, and the mahadasha/antardasha running on a date. |
| `get_muhurta` | Abhijit and Brahma muhurta, Rahu kaalam, Yamagandam, Gulika and Durmuhurtam. |

## Defaults

- Location: Varanasi (25.3176 N, 82.9739 E), `Asia/Kolkata`
- Ayanamsa: Lahiri / Chitrapaksha
- Panchang: Drik ganita, sunrise-based day
- Sunrise: Hindu rising convention (disc center, no refraction)
- Houses: whole sign from lagna
- Months and festivals (when added): purnimanta

Every tool accepts `latitude`, `longitude`, `timezone` (an IANA name or a fixed
UTC offset in hours) and `location_name` to override the defaults.

## Install

Requires Python 3.12 or newer.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -e .
```

With `uv`:

```sh
uv venv --python 3.12
uv pip install -e .
```

The server speaks MCP over stdio:

```sh
.venv/bin/astro-mcp
```

Set `PORT` to serve streamable HTTP instead:

```sh
PORT=8080 .venv/bin/astro-mcp
```

The MCP endpoint is `http://localhost:8080/mcp`. The included `Dockerfile` is
set up for Cloud Run, which provides `PORT` automatically.

## Configure

Point any MCP client at the installed executable:

```json
{
  "mcpServers": {
    "astro-mcp": {
      "command": "/absolute/path/to/astro-mcp/.venv/bin/astro-mcp"
    }
  }
}
```

## Examples

`get_panchang`:

```json
{"date": "2026-11-20"}
```

```json
{
  "sunrise": "2026-11-20T06:22:30+05:30",
  "tithi": {
    "name": "Dashami",
    "paksha": "Shukla",
    "start": "2026-11-19T07:31:30+05:30",
    "end": "2026-11-20T07:16:50+05:30"
  },
  "nakshatra": {
    "name": "Purva Bhadrapada",
    "pada": 4,
    "start": "2026-11-19T06:10:35+05:30",
    "end": "2026-11-20T06:56:46+05:30"
  }
}
```

`get_kundli`:

```json
{"date": "1990-01-01", "time": "12:00"}
```

`get_dashas` (defaults `as_of` to today):

```json
{"date": "1990-01-01", "time": "12:00", "as_of": "2026-11-20"}
```

`get_muhurta`:

```json
{"date": "2026-11-20"}
```

Birth times use 24-hour `HH:MM`. Dates use `YYYY-MM-DD`.

## Test

```sh
.venv/bin/pytest
```

## License and attribution

AGPL-3.0-or-later. See [LICENSE](LICENSE).

This server calls PyJHora (AGPL-3.0) and Swiss Ephemeris through pyswisseph
(AGPL-3.0, or a commercial license from Astrodienst). If you run a modified
version as a network service, AGPL section 13 requires you to offer the
corresponding source to its users.

Astrology output is for cultural and informational purposes. It is not medical,
legal or financial advice.
