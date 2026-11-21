# astro-mcp

An MCP server for Vedic astrology and panchang calculations, powered by
[PyJHora](https://github.com/naturalstupid/PyJHora) and the Swiss Ephemeris.

## Tools

| Tool | Returns |
| --- | --- |
| `get_panchang` | Sunrise, sunset, vara, tithi, nakshatra, yoga and karana, with start and end times. |
| `get_kundli` | D1 birth chart: lagna and planets with sign, degree, nakshatra, pada, whole-sign house and retrograde state. |
| `get_varga` | Divisional chart such as Navamsa D9 or Dasamsa D10, with each planet's aspects, natural friendships and combust state. |
| `get_bhava_chalit` | Degree-based house cusps (Sripati, KP/Placidus or equal) and each planet's bhava. |
| `get_transits` | Current transits with houses from the natal lagna and Moon, plus Sade Sati status. |
| `get_dashas` | Vimshottari timeline, balance at birth, and the running chain down to pratyantar, sookshma, prana or deha. |
| `get_yogini_dashas` | Yogini dasha timeline and running chain, with Yogini names and ruling planets. |
| `get_chara_dashas` | Chara (Jaimini rasi) dasha with KN Rao, PVN Rao or Irangatti methods. |
| `get_yogas` | Classical yogas and doshas, including Manglik, Kala Sarpa, Pitru and Raja yogas. |
| `get_strength` | Shadbala, Sarvashtakavarga and Bhinnashtakavarga bindus. |
| `get_matching` | North Indian Ashtakoota (36 points) or South Indian Porutham (10 checks), plus Manglik status and a D9 comparison. |
| `get_muhurta` | Abhijit and Brahma muhurta, Rahu kaalam, Yamagandam, Gulika and Durmuhurtam. |
| `get_festivals` | Hindu festivals in a date range, with purnimanta month, tithi and paksha. |

## Defaults

- Location: Varanasi (25.3176 N, 82.9739 E), `Asia/Kolkata`
- Ayanamsa: Lahiri / Chitrapaksha, selectable per request (`RAMAN`, `KP`,
  `TRUE_CHITRA`, `TRUE_PUSHYA`, `YUKTESHWAR`, `FAGAN`, `SURYA_SIDDHANTA`, ...)
- Panchang: Drik ganita, sunrise-based day
- Sunrise: Hindu rising by default; optionally refraction or bottom limb
- Houses: whole sign for D1; Sripati, KP/Placidus or equal for bhava chalit
- Dasha: Vimshottari, Yogini and Chara, running chain to any depth from maha to deha
- Strength: Shadbala and Ashtakavarga
- Matching: North Indian Ashtakoota (36 points) or South Indian Porutham
  (10 checks), with Manglik status and a D9 comparison
- Months and festivals: purnimanta

Place-based tools accept `latitude`, `longitude`, `timezone` (an IANA name or a
fixed UTC offset in hours) and `location_name` to override the defaults. The
chart tools (`get_panchang`, `get_kundli`, `get_varga`, `get_bhava_chalit`,
`get_dashas`, `get_yogini_dashas`, `get_chara_dashas`, `get_transits`,
`get_yogas` and `get_strength`) also accept `ayanamsa`. `get_matching` takes
two birth times
and a timezone; coordinates are only needed for the Manglik and D9 checks, and
`girl_latitude`/`girl_longitude` cover a girl born elsewhere. `system` selects
`north` (Ashtakoota) or `south` (Porutham). The dasha and transit tools also
accept `as_of_timezone` for the default `as_of` date, so "today" can follow
the user's current timezone instead of the birth place's.

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

`get_varga` (D9 by default):

```json
{"date": "1990-01-01", "time": "12:00", "division": 9}
```

`get_bhava_chalit` (Sripati by default):

```json
{"date": "1990-01-01", "time": "12:00", "house_system": "kp"}
```

`get_transits` (defaults `as_of` to today; Sade Sati is included):

```json
{"date": "1995-05-12", "time": "07:00", "as_of": "2026-11-21"}
```

`get_dashas` (defaults `as_of` to today; `depth` 3 adds pratyantar):

```json
{"date": "1990-01-01", "time": "12:00", "as_of": "2026-11-20", "depth": 3}
```

`get_yogas`:

```json
{"date": "1995-05-12", "time": "07:00"}
```

`get_chara_dashas` (`method` also accepts `pvn_rao`, `irangatti_male` or
`irangatti_female`):

```json
{
  "date": "1995-05-12", "time": "07:00",
  "as_of": "2026-11-21", "depth": 3, "method": "kn_rao"
}
```

`get_strength`:

```json
{"date": "1995-05-12", "time": "07:00"}
```

`get_matching` (boy and girl birth details; add `"system": "south"` for
Porutham). Tara uses the classical 3/5/7 inauspicious remainders and Varna
uses the element mapping (water Brahmin, fire Kshatriya, earth Vaishya, air
Shudra):

```json
{
  "boy_date": "1995-05-12", "boy_time": "07:00",
  "girl_date": "1990-01-01", "girl_time": "12:00",
  "system": "north"
}
```

`get_muhurta`:

```json
{"date": "2026-11-20"}
```

`get_festivals` (`calendar` can be `all`, `purnimanta`, `amanta`, `solar` or
`gregorian`; the range is capped at 366 days):

```json
{"start_date": "2026-11-01", "end_date": "2026-11-30", "calendar": "all"}
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
