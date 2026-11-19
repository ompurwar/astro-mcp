"""Vedic panchang calculations backed by PyJHora."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from datetime import date as Date
from datetime import datetime, timedelta, timezone as fixed_timezone
from typing import Any
from zoneinfo import ZoneInfo

from jhora import const, utils
from jhora.panchanga import drik

# PyJHora prints its sys.path edits on import; silence them so stdio stays clean.
with redirect_stdout(io.StringIO()):
    from jhora.horoscope.dhasa.graha import vimsottari

# Lahiri/Chitrapaksha is the standard for Indian calendars and the Kashi panchang.
drik.set_ayanamsa_mode("LAHIRI")

DEFAULT_LATITUDE = 25.3176
DEFAULT_LONGITUDE = 82.9739
DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_LOCATION = "Varanasi"

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


def _offset_hours(tz: str | float, day: Date) -> float:
    if isinstance(tz, (int, float)):
        return float(tz)
    offset = datetime(
        day.year, day.month, day.day, 12, tzinfo=ZoneInfo(tz)
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
) -> dict[str, Any]:
    """Return the five limbs of the panchang at sunrise for a date and place."""
    day = Date.fromisoformat(date)
    _check_coordinates(latitude, longitude)

    offset = _offset_hours(timezone, day)
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number((day.year, day.month, day.day), (12, 0, 0))

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
            "ayanamsa": "Lahiri",
            "day_starts": "sunrise",
            "sunrise_convention": "Hindu rising (disc center, no refraction)",
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


def _position(full_longitude: float, lagna_rasi: int) -> dict[str, Any]:
    rasi = int(full_longitude // 30)
    nakshatra, pada, _ = drik.nakshatra_pada(full_longitude)
    return {
        "sign": RAASI_NAMES[rasi],
        "degree": round(full_longitude - rasi * 30, 2),
        "nakshatra": utils.NAKSHATRA_LIST[nakshatra - 1],
        "pada": pada,
        "house": (rasi - lagna_rasi) % 12 + 1,
    }


def kundli(
    date: str,
    time: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
) -> dict[str, Any]:
    """Return the birth chart (D1) for a local date, time and place."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)

    offset = _offset_hours(timezone, day)
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number(
        (birth.year, birth.month, birth.day),
        (birth.hour, birth.minute, birth.second),
    )

    lagna_rasi, lagna_degree, lagna_nakshatra, lagna_pada = drik.ascendant(
        jd, place
    )
    retrograde = set(drik.planets_in_retrograde(jd, place))

    planets = []
    for planet_id, (rasi, degree) in drik.planetary_positions(jd, place):
        position = _position(rasi * 30 + degree, lagna_rasi)
        planets.append(
            {
                "name": PLANET_NAMES[planet_id],
                **position,
                "retrograde": planet_id in retrograde,
            }
        )

    tz = fixed_timezone(timedelta(hours=offset))
    return {
        "datetime": birth.replace(tzinfo=tz).isoformat(timespec="seconds"),
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {
            "ayanamsa": "Lahiri",
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
) -> dict[str, Any]:
    """Return the Vimshottari mahadasha timeline and running periods."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)

    offset = _offset_hours(timezone, day)
    place = drik.Place(location_name, latitude, longitude, offset)
    dob = (birth.year, birth.month, birth.day)
    tob = (birth.hour, birth.minute, birth.second)
    jd = utils.julian_day_number(dob, tob)

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

    if as_of is not None:
        as_of_day = Date.fromisoformat(as_of)
    elif isinstance(timezone, str):
        as_of_day = datetime.now(ZoneInfo(timezone)).date()
    else:
        as_of_day = datetime.now(
            fixed_timezone(timedelta(hours=offset))
        ).date()
    if as_of_day < day:
        raise ValueError("as_of must not be before the birth date")

    as_of_jd = utils.julian_day_number(
        (as_of_day.year, as_of_day.month, as_of_day.day), (12, 0, 0)
    )
    running = [
        {
            "level": "Mahadasha" if len(lords) == 1 else "Antardasha",
            "lord": PLANET_NAMES[lords[-1]],
            "start": _tuple_iso(start, offset),
            "end": _tuple_iso(end, offset),
        }
        for lords, start, end in vimsottari.get_running_dhasa_for_given_date(
            as_of_jd, jd, place, dhasa_level_index=2
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
        "system": {"dasha": "Vimshottari"},
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

    abhijit = drik.abhijit_muhurta(jd, place)
    durmuhurtam = drik.durmuhurtam(jd, place)
    rahu = drik.raahu_kaalam(jd, place)
    yama = drik.yamaganda_kaalam(jd, place)
    gulika = drik.gulikai_kaalam(jd, place)
    return {
        "date": date,
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "sunrise": _iso(day, drik.sunrise(jd, place)[0], offset),
        "sunset": _iso(day, drik.sunset(jd, place)[0], offset),
        "abhijit": window(
            _hms_to_hours(abhijit[0]), _hms_to_hours(abhijit[1])
        ),
        "brahma": window(*drik.brahma_muhurtha(jd, place)),
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
