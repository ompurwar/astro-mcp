"""Vedic panchang calculations backed by PyJHora."""

from __future__ import annotations

import html
import io
import re
import threading
from contextlib import contextmanager, redirect_stdout
from datetime import date as Date
from datetime import datetime, timedelta, timezone as fixed_timezone
from typing import Any
from zoneinfo import ZoneInfo

from jhora import const, utils
from jhora.panchanga import drik

# PyJHora prints its sys.path edits on import; silence them so stdio stays clean.
with redirect_stdout(io.StringIO()):
    from jhora.horoscope.chart import ashtakavarga, dosha, strength, yoga
    from jhora.horoscope.dhasa.graha import vimsottari, yogini
    from jhora.horoscope.match.compatibility import Ashtakoota

# Lahiri/Chitrapaksha is the standard for Indian calendars and the Kashi panchang.
drik.set_ayanamsa_mode("LAHIRI")

DEFAULT_LATITUDE = 25.3176
DEFAULT_LONGITUDE = 82.9739
DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_LOCATION = "Varanasi"

AYANAMSA_MODES = {
    "LAHIRI": "Lahiri",
    "RAMAN": "Raman",
    "KP": "KP",
    "TRUE_CHITRA": "True Chitra",
    "TRUE_PUSHYA": "True Pushya",
    "TRUE_REVATI": "True Revati",
    "TRUE_MULA": "True Mula",
    "YUKTESHWAR": "Yukteshwar",
    "FAGAN": "Fagan/Bradley",
    "USHASHASHI": "Ushashashi",
    "SURYASIDDHANTA": "Surya Siddhanta",
    "SURYASIDDHANTA_MSUN": "Surya Siddhanta (Mean Sun)",
    "ARYABHATA": "Aryabhata",
    "ARYABHATA_MSUN": "Aryabhata (Mean Sun)",
    "SS_CITRA": "Surya Siddhanta Chitra",
    "SS_REVATI": "Surya Siddhanta Revati",
}

# PyJHora keys omit the underscore in SURYA_SIDDHANTA; accept both spellings.
AYANAMSA_ALIASES = {
    "SURYA_SIDDHANTA": "SURYASIDDHANTA",
    "SURYA_SIDDHANTA_MSUN": "SURYASIDDHANTA_MSUN",
}

VARGA_NAMES = {
    1: "Rasi",
    2: "Hora",
    3: "Drekkana",
    4: "Chaturthamsa",
    5: "Panchamsa",
    6: "Shashthamsa",
    7: "Saptamsa",
    8: "Ashtamsa",
    9: "Navamsa",
    10: "Dasamsa",
    11: "Rudramsa",
    12: "Dwadamsa",
    16: "Shodamsa",
    20: "Vimsamsa",
    24: "Chaturvimsamsa",
    27: "Nakshatramsa",
    30: "Trisamsa",
    40: "Khavedamsa",
    45: "Akshavedamsa",
    60: "Shastyamsa",
}

DASHA_LEVELS = (
    "Mahadasha",
    "Antardasha",
    "Pratyantardasha",
    "Sookshma",
    "Prana",
    "Deha",
)

YOGINI_NAMES = {
    0: "Pingala",
    1: "Mangala",
    2: "Bhramari",
    3: "Bhadrika",
    4: "Dhanya",
    5: "Siddha",
    6: "Ulka",
    7: "Sankata",
}

COMBUSTION_ORBS = {
    1: 12.0,  # Moon
    2: 17.0,  # Mars
    3: 14.0,  # Mercury
    4: 11.0,  # Jupiter
    5: 10.0,  # Venus
    6: 15.0,  # Saturn
}

SUNRISE_CONVENTIONS = {
    "hindu": "Hindu rising (disc center, no refraction)",
    "refraction": "Center of disc with refraction",
    "bottom_limb": "Bottom limb with refraction",
}

_AYANAMSA_LOCK = threading.RLock()


@contextmanager
def _use_ayanamsa(mode: str):
    raw = mode.strip().upper()
    key = AYANAMSA_ALIASES.get(raw, raw)
    if key not in AYANAMSA_MODES:
        raise ValueError(
            f"Unknown ayanamsa: {mode}. Supported: {', '.join(AYANAMSA_MODES)}"
        )
    with _AYANAMSA_LOCK:
        drik.set_ayanamsa_mode(key)
        yield AYANAMSA_MODES[key]


@contextmanager
def _use_sunrise_convention(mode: str):
    key = mode.strip().lower()
    if key not in SUNRISE_CONVENTIONS:
        raise ValueError(
            "sunrise_convention must be hindu, refraction or bottom_limb"
        )
    with _AYANAMSA_LOCK:
        saved = (
            const.RISE_SET_HINDU_RISING,
            const.RISE_SET_USE_REFRACTION,
            const.RISE_SET_USE_DISC_CENTER_FOR_RISING,
        )
        const.RISE_SET_HINDU_RISING = key == "hindu"
        const.RISE_SET_USE_REFRACTION = key != "hindu"
        const.RISE_SET_USE_DISC_CENTER_FOR_RISING = key != "bottom_limb"
        drik.refresh_planet_flags()
        try:
            yield SUNRISE_CONVENTIONS[key]
        finally:
            (
                const.RISE_SET_HINDU_RISING,
                const.RISE_SET_USE_REFRACTION,
                const.RISE_SET_USE_DISC_CENTER_FOR_RISING,
            ) = saved
            drik.refresh_planet_flags()

PLANET_NAMES = (
    "Sun",
    "Moon",
    "Mars",
    "Mercury",
    "Jupiter",
    "Venus",
    "Saturn",
    "Rahu",
    "Ketu",
)
RAASI_NAMES = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)


def _check_coordinates(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")


def _offset_hours(tz: str | float, day: Date, hour: float = 12.0) -> float:
    if isinstance(tz, (int, float)):
        return float(tz)
    total_minutes = int(round(hour * 60))
    whole_hour, minute = divmod(total_minutes, 60)
    offset = datetime(
        day.year,
        day.month,
        day.day,
        whole_hour,
        minute,
        tzinfo=ZoneInfo(tz),
    ).utcoffset()
    if offset is None:
        raise ValueError(f"Unknown timezone: {tz}")
    return offset.total_seconds() / 3600


def _iso(day: Date, hours: float, offset: float) -> str:
    """Convert PyJHora local hours-from-midnight to an ISO datetime."""
    tz = fixed_timezone(timedelta(hours=offset))
    midnight = datetime(day.year, day.month, day.day, tzinfo=tz)
    return (midnight + timedelta(hours=hours)).isoformat(timespec="seconds")


def _birth_datetime(date: str, time: str) -> datetime:
    return datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")


def _as_of_date(
    as_of: str | None,
    timezone: str | float,
    offset: float,
    as_of_timezone: str | float | None = None,
) -> Date:
    if as_of is not None:
        return Date.fromisoformat(as_of)
    tz = as_of_timezone if as_of_timezone is not None else timezone
    if isinstance(tz, str):
        return datetime.now(ZoneInfo(tz)).date()
    return datetime.now(
        fixed_timezone(timedelta(hours=float(tz)))
    ).date()


def _clean_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _is_combust(
    planet_id: int,
    full_longitude: float,
    sun_longitude: float,
    retrograde: bool,
) -> bool:
    orb = COMBUSTION_ORBS.get(planet_id)
    if orb is None:
        return False
    if planet_id == 3 and retrograde:
        orb = 12.0
    if planet_id == 5 and retrograde:
        orb = 8.0
    distance = abs((full_longitude - sun_longitude + 180) % 360 - 180)
    return distance <= orb


def _hms_to_hours(value: str) -> float:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours + minutes / 60 + seconds / 3600


def _location(
    name: str, latitude: float, longitude: float, timezone: str | float, offset: float
) -> dict[str, Any]:
    return {
        "name": name,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "offset_hours": offset,
    }


def _nakshatra_start(
    reference_jd: float, number: int, place: drik.Place
) -> tuple[Date, float]:
    """Return the date and local hour when the current nakshatra began.

    PyJHora reports the previous day's end as the start and normalizes it to
    the current day, which collapses start and end onto the same instant.
    Search back to the last day with a different nakshatra; its end is the
    current nakshatra's true start.
    """
    for days in range(1, 4):
        jd = reference_jd - days
        previous = drik.nakshatra(jd, place)
        if previous[0] != number:
            year, month, day, _ = utils.jd_to_gregorian(jd)
            return Date(year, month, day), previous[3]
    raise ValueError("could not locate nakshatra start")


def panchang(
    date: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    ayanamsa: str = "LAHIRI",
    sunrise_convention: str = "hindu",
) -> dict[str, Any]:
    """Return the five limbs of the panchang at sunrise for a date and place."""
    day = Date.fromisoformat(date)
    _check_coordinates(latitude, longitude)

    offset = _offset_hours(timezone, day)
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number((day.year, day.month, day.day), (12, 0, 0))

    with (
        _use_ayanamsa(ayanamsa) as ayanamsa_label,
        _use_sunrise_convention(sunrise_convention) as sunrise_label,
    ):
        sunrise = drik.sunrise(jd, place)
        sunset = drik.sunset(jd, place)
        reference = sunrise[2]  # panchang elements are read at sunrise

        tithi = drik.tithi(reference, place)
        nakshatra = drik.nakshatra(reference, place)
        yoga = drik.yogam(reference, place)
        karana = drik.karana(reference, place)
        vara = drik.civil_weekday(jd)
        nak_start_day, nak_start_hours = _nakshatra_start(
            reference, nakshatra[0], place
        )

    tithi_number = tithi[0]
    return {
        "date": date,
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {
            "panchanga": "Drik",
            "ayanamsa": ayanamsa_label,
            "day_starts": "sunrise",
            "sunrise_convention": sunrise_label,
        },
        "sunrise": _iso(day, sunrise[0], offset),
        "sunset": _iso(day, sunset[0], offset),
        "vara": {"number": vara + 1, "name": utils.DAYS_LIST[vara]},
        "tithi": {
            "number": tithi_number,
            "name": utils.TITHI_LIST[tithi_number - 1],
            "paksha": "Shukla" if tithi_number <= 15 else "Krishna",
            "start": _iso(day, tithi[1], offset),
            "end": _iso(day, tithi[2], offset),
        },
        "nakshatra": {
            "number": nakshatra[0],
            "name": utils.NAKSHATRA_LIST[nakshatra[0] - 1],
            "pada": nakshatra[1],
            "start": _iso(nak_start_day, nak_start_hours, offset),
            "end": _iso(day, nakshatra[3], offset),
        },
        "yoga": {
            "number": yoga[0],
            "name": utils.YOGAM_LIST[yoga[0] - 1],
            "start": _iso(day, yoga[1], offset),
            "end": _iso(day, yoga[2], offset),
        },
        "karana": {
            "number": karana[0],
            "name": utils.KARANA_LIST[karana[0] - 1],
            "start": _iso(day, karana[1], offset),
            "end": _iso(day, karana[2], offset),
        },
    }


def _base_position(full_longitude: float) -> dict[str, Any]:
    rasi = int(full_longitude // 30) % 12
    nakshatra, pada, _ = drik.nakshatra_pada(full_longitude)
    return {
        "sign": RAASI_NAMES[rasi],
        "degree": round(full_longitude - rasi * 30, 2),
        "nakshatra": utils.NAKSHATRA_LIST[nakshatra - 1],
        "pada": pada,
    }


def _position(full_longitude: float, lagna_rasi: int) -> dict[str, Any]:
    return {
        **_base_position(full_longitude),
        "house": (int(full_longitude // 30) - lagna_rasi) % 12 + 1,
    }


def _sign_degree(longitude: float) -> dict[str, Any]:
    longitude %= 360
    return {
        "sign": RAASI_NAMES[int(longitude // 30)],
        "degree": round(longitude % 30, 2),
    }


def _bhava_for_longitude(longitude: float, cusps: list[float]) -> int:
    for index, start in enumerate(cusps):
        span = (cusps[(index + 1) % 12] - start) % 360
        if (longitude - start) % 360 < span:
            return index + 1
    raise ValueError("could not place longitude in a bhava")


def kundli(
    date: str,
    time: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return the birth chart (D1) for a local date, time and place."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)

    offset = _offset_hours(
        timezone, day, birth.hour + birth.minute / 60
    )
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number(
        (birth.year, birth.month, birth.day),
        (birth.hour, birth.minute, birth.second),
    )

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        lagna_rasi, lagna_degree, lagna_nakshatra, lagna_pada = (
            drik.ascendant(jd, place)
        )
        retrograde = set(drik.planets_in_retrograde(jd, place))
        positions = drik.planetary_positions(jd, place)

    sun_full = next(
        rasi * 30 + degree
        for planet_id, (rasi, degree) in positions
        if planet_id == 0
    )
    planets = []
    for planet_id, (rasi, degree) in positions:
        full_longitude = rasi * 30 + degree
        planets.append(
            {
                "name": PLANET_NAMES[planet_id],
                **_position(full_longitude, lagna_rasi),
                "retrograde": planet_id in retrograde,
                "combust": _is_combust(
                    planet_id,
                    full_longitude,
                    sun_full,
                    planet_id in retrograde,
                ),
            }
        )

    tz = fixed_timezone(timedelta(hours=offset))
    return {
        "datetime": birth.replace(tzinfo=tz).isoformat(timespec="seconds"),
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {
            "ayanamsa": ayanamsa_label,
            "houses": "whole sign from lagna",
        },
        "lagna": {
            "sign": RAASI_NAMES[lagna_rasi],
            "degree": round(lagna_degree, 2),
            "nakshatra": utils.NAKSHATRA_LIST[lagna_nakshatra - 1],
            "pada": lagna_pada,
        },
        "planets": planets,
    }


def varga(
    date: str,
    time: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    division: int = 9,
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return a divisional (varga) chart such as Navamsa D9 or Dasamsa D10."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)
    if division not in VARGA_NAMES:
        raise ValueError(
            f"Unsupported division: {division}. Supported: {sorted(VARGA_NAMES)}"
        )

    offset = _offset_hours(
        timezone, day, birth.hour + birth.minute / 60
    )
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number(
        (birth.year, birth.month, birth.day),
        (birth.hour, birth.minute, birth.second),
    )

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        lagna_rasi, lagna_degree, _, _ = drik.ascendant(jd, place)
        varga_lagna_rasi, _ = drik.dasavarga_from_long(
            lagna_rasi * 30 + lagna_degree, division
        )
        retrograde = set(drik.planets_in_retrograde(jd, place))
        d1_positions = drik.planetary_positions(jd, place)
        positions = drik.dhasavarga(
            jd, place, divisional_chart_factor=division
        )

    d1_longitudes = {
        planet_id: rasi * 30 + degree
        for planet_id, (rasi, degree) in d1_positions
    }
    sun_full = d1_longitudes[0]
    planets = [
        {
            "name": PLANET_NAMES[planet_id],
            "sign": RAASI_NAMES[rasi],
            "house": (rasi - varga_lagna_rasi) % 12 + 1,
            "retrograde": planet_id in retrograde,
            "combust": _is_combust(
                planet_id,
                d1_longitudes[planet_id],
                sun_full,
                planet_id in retrograde,
            ),
        }
        for planet_id, (rasi, _) in positions
    ]

    tz = fixed_timezone(timedelta(hours=offset))
    return {
        "datetime": birth.replace(tzinfo=tz).isoformat(timespec="seconds"),
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {
            "ayanamsa": ayanamsa_label,
            "division": division,
            "varga": VARGA_NAMES[division],
        },
        "lagna": {"sign": RAASI_NAMES[varga_lagna_rasi]},
        "planets": planets,
    }


def bhava_chalit(
    date: str,
    time: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    house_system: str = "sripati",
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return the degree-based bhava chalit chart."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)

    system_key = house_system.strip().lower()
    if system_key not in ("sripati", "kp", "placidus", "equal"):
        raise ValueError(
            "house_system must be sripati, kp, placidus or equal"
        )
    labels = {
        "sripati": "Sripati",
        "kp": "KP (Placidus)",
        "placidus": "Placidus",
        "equal": "Equal houses",
    }

    offset = _offset_hours(
        timezone, day, birth.hour + birth.minute / 60
    )
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number(
        (birth.year, birth.month, birth.day),
        (birth.hour, birth.minute, birth.second),
    )

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        lagna_rasi, lagna_degree, lagna_nakshatra, lagna_pada = (
            drik.ascendant(jd, place)
        )
        lagna_full = lagna_rasi * 30 + lagna_degree
        if system_key == "sripati":
            cusps = drik.bhaava_madhya(jd, place, 2)
        elif system_key in ("kp", "placidus"):
            cusps = drik.bhaava_madhya(jd, place, 1)
        else:
            cusps = [(lagna_full + index * 30) % 360 for index in range(12)]
        cusps = [float(cusp) % 360 for cusp in cusps]
        retrograde = set(drik.planets_in_retrograde(jd, place))
        positions = drik.planetary_positions(jd, place)

    sun_full = next(
        rasi * 30 + degree
        for planet_id, (rasi, degree) in positions
        if planet_id == 0
    )
    names_by_house: dict[int, list[str]] = {index: [] for index in range(1, 13)}
    planets = []
    for planet_id, (rasi, degree) in positions:
        full_longitude = rasi * 30 + degree
        bhava = _bhava_for_longitude(full_longitude, cusps)
        names_by_house[bhava].append(PLANET_NAMES[planet_id])
        planets.append(
            {
                "name": PLANET_NAMES[planet_id],
                **_base_position(full_longitude),
                "bhava": bhava,
                "retrograde": planet_id in retrograde,
                "combust": _is_combust(
                    planet_id,
                    full_longitude,
                    sun_full,
                    planet_id in retrograde,
                ),
            }
        )

    houses = []
    for index, start in enumerate(cusps):
        end = cusps[(index + 1) % 12]
        houses.append(
            {
                "house": index + 1,
                "sign": RAASI_NAMES[int(start // 30)],
                "start": _sign_degree(start),
                "end": _sign_degree(end),
                "planets": names_by_house[index + 1],
            }
        )

    tz = fixed_timezone(timedelta(hours=offset))
    return {
        "datetime": birth.replace(tzinfo=tz).isoformat(timespec="seconds"),
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {
            "ayanamsa": ayanamsa_label,
            "house_system": labels[system_key],
        },
        "lagna": {
            "sign": RAASI_NAMES[lagna_rasi],
            "degree": round(lagna_degree, 2),
            "nakshatra": utils.NAKSHATRA_LIST[lagna_nakshatra - 1],
            "pada": lagna_pada,
        },
        "houses": houses,
        "planets": planets,
    }


def _tuple_iso(value: tuple[int, int, int, float], offset: float) -> str:
    year, month, day, hours = value
    return _iso(Date(year, month, day), hours, offset)


def _dasha_period(
    lords: tuple[int, ...], start_jd: float, end_jd: float, offset: float
) -> dict[str, Any]:
    return {
        "lord": PLANET_NAMES[lords[0]],
        "start": _tuple_iso(utils.jd_to_gregorian(start_jd), offset),
        "end": _tuple_iso(utils.jd_to_gregorian(end_jd), offset),
    }


def dashas(
    date: str,
    time: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    as_of: str | None = None,
    as_of_timezone: str | float | None = None,
    depth: int = 2,
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return the Vimshottari mahadasha timeline and running periods."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)
    if not 1 <= depth <= len(DASHA_LEVELS):
        raise ValueError(f"depth must be between 1 and {len(DASHA_LEVELS)}")

    offset = _offset_hours(
        timezone, day, birth.hour + birth.minute / 60
    )
    place = drik.Place(location_name, latitude, longitude, offset)
    dob = (birth.year, birth.month, birth.day)
    tob = (birth.hour, birth.minute, birth.second)
    jd = utils.julian_day_number(dob, tob)

    as_of_day = _as_of_date(as_of, timezone, offset, as_of_timezone)
    if as_of_day < day:
        raise ValueError("as_of must not be before the birth date")

    as_of_jd = utils.julian_day_number(
        (as_of_day.year, as_of_day.month, as_of_day.day), (12, 0, 0)
    )

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        balance, rows = vimsottari.get_dhasa_antardhasa(
            dob,
            tob,
            place,
            dhasa_level_index=const.MAHA_DHASA_DEPTH.MAHA_DHASA_ONLY,
            return_exact_bounds=True,
        )
        mahadashas = [
            _dasha_period(lords, start, end, offset)
            for lords, start, end, _ in rows
        ]
        running = [
            {
                "level": DASHA_LEVELS[len(lords) - 1],
                "lord": PLANET_NAMES[lords[-1]],
                "start": _tuple_iso(start, offset),
                "end": _tuple_iso(end, offset),
            }
            for lords, start, end in vimsottari.get_running_dhasa_for_given_date(
                as_of_jd, jd, place, dhasa_level_index=depth
            )
        ]

    return {
        "datetime": birth.replace(
            tzinfo=fixed_timezone(timedelta(hours=offset))
        ).isoformat(timespec="seconds"),
        "as_of": as_of_day.isoformat(),
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {
            "dasha": "Vimshottari",
            "ayanamsa": ayanamsa_label,
            "depth": depth,
        },
        "balance_at_birth": {
            "years": balance[0],
            "months": balance[1],
            "days": balance[2],
        },
        "mahadashas": mahadashas,
        "running": running,
    }


def muhurta(
    date: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    sunrise_convention: str = "hindu",
) -> dict[str, Any]:
    """Return the day's auspicious and inauspicious time windows."""
    day = Date.fromisoformat(date)
    _check_coordinates(latitude, longitude)

    offset = _offset_hours(timezone, day)
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number((day.year, day.month, day.day), (12, 0, 0))

    def window(start: float, end: float) -> dict[str, str]:
        return {
            "start": _iso(day, start, offset),
            "end": _iso(day, end, offset),
        }

    with _use_sunrise_convention(sunrise_convention) as sunrise_label:
        sunrise = drik.sunrise(jd, place)
        sunset = drik.sunset(jd, place)
        abhijit = drik.abhijit_muhurta(jd, place)
        brahma = drik.brahma_muhurtha(jd, place)
        durmuhurtam = drik.durmuhurtam(jd, place)
        rahu = drik.raahu_kaalam(jd, place)
        yama = drik.yamaganda_kaalam(jd, place)
        gulika = drik.gulikai_kaalam(jd, place)

    return {
        "date": date,
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {"sunrise_convention": sunrise_label},
        "sunrise": _iso(day, sunrise[0], offset),
        "sunset": _iso(day, sunset[0], offset),
        "abhijit": window(
            _hms_to_hours(abhijit[0]), _hms_to_hours(abhijit[1])
        ),
        "brahma": window(*brahma),
        "rahu_kaalam": window(
            _hms_to_hours(rahu[0]), _hms_to_hours(rahu[1])
        ),
        "yamagandam": window(
            _hms_to_hours(yama[0]), _hms_to_hours(yama[1])
        ),
        "gulika": window(
            _hms_to_hours(gulika[0]), _hms_to_hours(gulika[1])
        ),
        "durmuhurtam": [
            window(_hms_to_hours(start), _hms_to_hours(end))
            for start, end in zip(durmuhurtam[::2], durmuhurtam[1::2])
        ],
    }


def _moon_details(
    date: str, time: str, timezone: str | float, ayanamsa: str
) -> dict[str, Any]:
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    offset = _offset_hours(
        timezone, day, birth.hour + birth.minute / 60
    )
    jd = utils.julian_day_number(
        (birth.year, birth.month, birth.day),
        (birth.hour, birth.minute, birth.second),
    )
    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        moon_longitude = drik.sidereal_longitude(
            jd - offset / 24, const._MOON
        )
        nakshatra, pada, _ = drik.nakshatra_pada(moon_longitude)
    tz = fixed_timezone(timedelta(hours=offset))
    return {
        "datetime": birth.replace(tzinfo=tz).isoformat(timespec="seconds"),
        "number": nakshatra,
        **_base_position(moon_longitude),
        "ayanamsa": ayanamsa_label,
    }


def matching(
    boy_date: str,
    boy_time: str,
    girl_date: str,
    girl_time: str,
    timezone: str | float = DEFAULT_TIMEZONE,
    girl_timezone: str | float | None = None,
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return North Indian Ashtakoota guna milan for two birth times."""
    boy = _moon_details(boy_date, boy_time, timezone, ayanamsa)
    girl = _moon_details(
        girl_date,
        girl_time,
        girl_timezone if girl_timezone is not None else timezone,
        ayanamsa,
    )

    ashtakoota = Ashtakoota(
        boy["number"],
        boy["pada"],
        girl["number"],
        girl["pada"],
        method=const.CHART_STYLE.NORTH_INDIAN,
    )
    values = ashtakoota.compatibility_score()
    labels = (
        "varna",
        "vasiya",
        "gana",
        "tara",
        "yoni",
        "graha_maitri",
        "bhakoot",
        "nadi",
    )
    scores = dict(zip(labels, values[:8]))
    total = values[8]

    return {
        "boy": {
            key: boy[key]
            for key in ("datetime", "sign", "degree", "nakshatra", "pada")
        },
        "girl": {
            key: girl[key]
            for key in ("datetime", "sign", "degree", "nakshatra", "pada")
        },
        "scores": scores,
        "total": total,
        "max": 36,
        "verdict": (
            "recommended" if total >= 18 else "below traditional minimum"
        ),
        "extras": {
            "mahendra": values[9],
            "vedha": values[10],
            "rajju": values[11],
            "shree_dheerga": values[12],
        },
        "system": {
            "ayanamsa": boy["ayanamsa"],
            "method": "North Indian Ashtakoota",
        },
        "note": (
            "18/36 is the traditional minimum; this is not a substitute "
            "for a full chart comparison."
        ),
    }


def transits(
    date: str,
    time: str,
    as_of: str | None = None,
    as_of_time: str = "12:00",
    as_of_timezone: str | float | None = None,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return current transits against the natal lagna and Moon."""
    natal_day = Date.fromisoformat(date)
    natal_birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)

    natal_offset = _offset_hours(
        timezone, natal_day, natal_birth.hour + natal_birth.minute / 60
    )
    natal_place = drik.Place(
        location_name, latitude, longitude, natal_offset
    )
    natal_jd = utils.julian_day_number(
        (natal_birth.year, natal_birth.month, natal_birth.day),
        (natal_birth.hour, natal_birth.minute, natal_birth.second),
    )

    target_day = _as_of_date(
        as_of, timezone, natal_offset, as_of_timezone
    )
    if target_day < natal_day:
        raise ValueError("as_of must not be before the birth date")

    target_birth = _birth_datetime(target_day.isoformat(), as_of_time)
    target_offset = _offset_hours(
        as_of_timezone if as_of_timezone is not None else timezone,
        target_day,
        target_birth.hour + target_birth.minute / 60,
    )
    target_place = drik.Place(
        location_name, latitude, longitude, target_offset
    )
    target_jd = utils.julian_day_number(
        (target_birth.year, target_birth.month, target_birth.day),
        (target_birth.hour, target_birth.minute, target_birth.second),
    )

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        natal_lagna = drik.ascendant(natal_jd, natal_place)
        natal_positions = drik.planetary_positions(natal_jd, natal_place)
        target_positions = drik.planetary_positions(target_jd, target_place)
        target_retrograde = set(
            drik.planets_in_retrograde(target_jd, target_place)
        )

    natal_moon = next(
        (rasi, degree)
        for planet_id, (rasi, degree) in natal_positions
        if planet_id == 1
    )
    natal_moon_rasi = natal_moon[0]

    planets = []
    for planet_id, (rasi, degree) in target_positions:
        planets.append(
            {
                "name": PLANET_NAMES[planet_id],
                **_base_position(rasi * 30 + degree),
                "house_from_lagna": (rasi - natal_lagna[0]) % 12 + 1,
                "house_from_moon": (rasi - natal_moon_rasi) % 12 + 1,
                "retrograde": planet_id in target_retrograde,
            }
        )

    saturn = next(planet for planet in planets if planet["name"] == "Saturn")
    saturn_house_from_moon = saturn["house_from_moon"]
    phase = {
        12: "Rising",
        1: "Peak",
        2: "Setting",
    }.get(saturn_house_from_moon)

    natal_tz = fixed_timezone(timedelta(hours=natal_offset))
    target_tz = fixed_timezone(timedelta(hours=target_offset))
    return {
        "natal": {
            "datetime": natal_birth.replace(tzinfo=natal_tz).isoformat(
                timespec="seconds"
            ),
            "lagna": {
                "sign": RAASI_NAMES[natal_lagna[0]],
                "degree": round(natal_lagna[1], 2),
                "nakshatra": utils.NAKSHATRA_LIST[natal_lagna[2] - 1],
                "pada": natal_lagna[3],
            },
            "moon": _base_position(
                natal_moon_rasi * 30 + natal_moon[1]
            ),
        },
        "as_of": target_birth.replace(tzinfo=target_tz).isoformat(
            timespec="seconds"
        ),
        "location": _location(
            location_name, latitude, longitude, timezone, natal_offset
        ),
        "system": {"ayanamsa": ayanamsa_label},
        "planets": planets,
        "sade_sati": {
            "active": phase is not None,
            "phase": phase,
            "saturn_house_from_moon": saturn_house_from_moon,
            "note": (
                "Sade Sati is judged from Saturn's transit over the "
                "12th, 1st or 2nd sign from the natal Moon."
            ),
        },
    }


def yogas(
    date: str,
    time: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    division: int = 1,
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return detected yogas and doshas for a chart."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)
    if division not in VARGA_NAMES:
        raise ValueError(
            f"Unsupported division: {division}. Supported: {sorted(VARGA_NAMES)}"
        )

    offset = _offset_hours(
        timezone, day, birth.hour + birth.minute / 60
    )
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number(
        (birth.year, birth.month, birth.day),
        (birth.hour, birth.minute, birth.second),
    )

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        with redirect_stdout(io.StringIO()):
            yoga_results, count, total = yoga.get_yoga_details(
                jd, place, divisional_chart_factor=division
            )
            dosha_results = dosha.get_dosha_details(jd, place)

    yoga_list = [
        {
            "key": key,
            "chart": details[0],
            "name": details[1],
            "description": details[2],
            "effects": details[3],
        }
        for key, details in yoga_results.items()
    ]
    dosha_list = {
        key: _clean_html(value) for key, value in dosha_results.items()
    }

    tz = fixed_timezone(timedelta(hours=offset))
    return {
        "datetime": birth.replace(tzinfo=tz).isoformat(timespec="seconds"),
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {
            "ayanamsa": ayanamsa_label,
            "division": division,
            "varga": VARGA_NAMES[division],
            "yogas_found": count,
            "yoga_rules_checked": total,
        },
        "yogas": yoga_list,
        "doshas": dosha_list,
        "note": (
            "Classical rule matches; many yogas cancel or modify each other. "
            "This is not a final judgment."
        ),
    }


def yogini_dashas(
    date: str,
    time: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    as_of: str | None = None,
    as_of_timezone: str | float | None = None,
    depth: int = 2,
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return the Yogini dasha timeline and running periods."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)
    if not 1 <= depth <= len(DASHA_LEVELS):
        raise ValueError(f"depth must be between 1 and {len(DASHA_LEVELS)}")

    offset = _offset_hours(
        timezone, day, birth.hour + birth.minute / 60
    )
    place = drik.Place(location_name, latitude, longitude, offset)
    dob = (birth.year, birth.month, birth.day)
    tob = (birth.hour, birth.minute, birth.second)
    jd = utils.julian_day_number(dob, tob)

    as_of_day = _as_of_date(as_of, timezone, offset, as_of_timezone)
    if as_of_day < day:
        raise ValueError("as_of must not be before the birth date")
    as_of_jd = utils.julian_day_number(
        (as_of_day.year, as_of_day.month, as_of_day.day), (12, 0, 0)
    )

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        rows = yogini.get_dhasa_antardhasa(
            dob,
            tob,
            place,
            dhasa_level_index=1,
            return_exact_bounds=True,
        )
        mahadashas = [
            {
                "yogini": YOGINI_NAMES.get(lords[0], "Unknown"),
                "lord": PLANET_NAMES[lords[0]],
                "start": _tuple_iso(
                    utils.jd_to_gregorian(start), offset
                ),
                "end": _tuple_iso(utils.jd_to_gregorian(end), offset),
                "duration_years": years,
            }
            for lords, start, end, years in rows
        ]
        running = [
            {
                "level": DASHA_LEVELS[len(lords) - 1],
                "yogini": YOGINI_NAMES.get(lords[-1], "Unknown"),
                "lord": PLANET_NAMES[lords[-1]],
                "start": _tuple_iso(start, offset),
                "end": _tuple_iso(end, offset),
            }
            for lords, start, end in yogini.get_running_dhasa_for_given_date(
                as_of_jd, jd, place, dhasa_level_index=depth
            )
        ]

    return {
        "datetime": birth.replace(
            tzinfo=fixed_timezone(timedelta(hours=offset))
        ).isoformat(timespec="seconds"),
        "as_of": as_of_day.isoformat(),
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {
            "dasha": "Yogini",
            "ayanamsa": ayanamsa_label,
            "depth": depth,
        },
        "mahadashas": mahadashas,
        "running": running,
        "note": (
            "The timeline starts with the balance of the pre-birth period, "
            "which can begin before the birth date."
        ),
    }


def strength_report(
    date: str,
    time: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return Shadbala and Ashtakavarga bindus."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)

    offset = _offset_hours(
        timezone, day, birth.hour + birth.minute / 60
    )
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number(
        (birth.year, birth.month, birth.day),
        (birth.hour, birth.minute, birth.second),
    )

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        shad = strength.shad_bala(jd, place)
        lagna = drik.ascendant(jd, place)
        positions = drik.planetary_positions(jd, place)
        chart = [""] * 12
        chart[lagna[0]] = "L"
        for planet_id, (rasi, degree) in positions:
            chart[rasi] = (
                chart[rasi] + "/" if chart[rasi] else ""
            ) + str(planet_id)
        bav, sav, _ = ashtakavarga.get_ashtaka_varga(chart)

    planets = PLANET_NAMES[:7]
    components = {
        name: dict(zip(planets, shad[index]))
        for index, name in enumerate(
            ("sthana", "kaala", "dig", "cheshta", "naisargika", "drik")
        )
    }
    bav_names = list(planets) + ["Lagna"]

    tz = fixed_timezone(timedelta(hours=offset))
    return {
        "datetime": birth.replace(tzinfo=tz).isoformat(timespec="seconds"),
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {"ayanamsa": ayanamsa_label},
        "shadbala": {
            "planets": planets,
            "components": components,
            "total": dict(zip(planets, shad[6])),
            "rupas": dict(zip(planets, shad[7])),
            "strength": dict(zip(planets, shad[8])),
        },
        "ashtakavarga": {
            "sarva": dict(zip(RAASI_NAMES, sav)),
            "bhinnashtakavarga": {
                bav_names[index]: dict(zip(RAASI_NAMES, bav[index]))
                for index in range(8)
            },
        },
        "note": (
            "Shadbala totals are in virupas; strength is the ratio to the "
            "required minimum. Ashtakavarga values are bindus."
        ),
    }
