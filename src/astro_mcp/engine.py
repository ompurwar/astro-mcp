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
    from jhora.horoscope.chart import (
        ashtakavarga,
        charts,
        dosha,
        house,
        strength,
        yoga,
    )
    from jhora.horoscope.dhasa.graha import vimsottari, yogini
    from jhora.horoscope.dhasa.raasi import chara
    from jhora.horoscope.match.compatibility import Ashtakoota
    from jhora.panchanga import vratha

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

CHARA_METHODS = {
    "pvn_rao": (const.CHARA_TYPE.PVN_RAO, "Parasara / PVN Rao"),
    "kn_rao": (const.CHARA_TYPE.KN_RAO, "KN Rao"),
    "irangatti_male": (
        const.CHARA_TYPE.IRANGATTI_MALE2,
        "Irangatti (male)",
    ),
    "irangatti_female": (
        const.CHARA_TYPE.IRANGATTI_FEMALE,
        "Irangatti (female)",
    ),
}

FESTIVAL_CALENDARS = {
    "solar": const.CALENDAR_TYPE.SOLAR,
    "amanta": const.CALENDAR_TYPE.LUNAR_AMANTHA,
    "purnimanta": const.CALENDAR_TYPE.LUNAR_PURNIMANTHA,
    "gregorian": const.CALENDAR_TYPE.GREGORIAN,
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


def _friendship(planet_id: int) -> dict[str, list[str]]:
    labels = {3: "friends", 2: "neutral", 1: "enemies"}
    groups: dict[str, list[str]] = {
        "friends": [],
        "neutral": [],
        "enemies": [],
    }
    for other, relation in enumerate(const.planet_relations[planet_id]):
        if other == planet_id:
            continue
        groups[labels[relation]].append(PLANET_NAMES[other])
    return groups


def _manglik_status(
    date: str,
    time: str,
    timezone: str | float,
    latitude: float,
    longitude: float,
    location_name: str,
    ayanamsa: str,
) -> dict[str, Any]:
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    offset = _offset_hours(timezone, day, birth.hour + birth.minute / 60)
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number(
        (birth.year, birth.month, birth.day),
        (birth.hour, birth.minute, birth.second),
    )
    with _use_ayanamsa(ayanamsa):
        positions = charts.rasi_chart(jd, place)
        manglik, exceptions, indices = dosha.manglik(positions)
    return {
        "is_manglik": manglik,
        "cancelled_by_exceptions": bool(manglik and exceptions),
        "effective": bool(manglik and not exceptions),
        "exception_indices": indices,
        "reference": "lagna",
    }


def _navamsa_summary(
    date: str,
    time: str,
    timezone: str | float,
    latitude: float,
    longitude: float,
    location_name: str,
    ayanamsa: str,
) -> dict[str, Any]:
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    offset = _offset_hours(timezone, day, birth.hour + birth.minute / 60)
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number(
        (birth.year, birth.month, birth.day),
        (birth.hour, birth.minute, birth.second),
    )
    with _use_ayanamsa(ayanamsa):
        lagna_rasi, lagna_degree, _, _ = drik.ascendant(jd, place)
        d9_lagna, _ = drik.dasavarga_from_long(
            lagna_rasi * 30 + lagna_degree, 9
        )
        positions = drik.dhasavarga(
            jd, place, divisional_chart_factor=9
        )
    moon_rasi = next(rasi for pid, (rasi, _) in positions if pid == 1)
    venus_rasi = next(rasi for pid, (rasi, _) in positions if pid == 5)
    return {
        "lagna": RAASI_NAMES[d9_lagna],
        "lagna_lord": PLANET_NAMES[const.house_owners[d9_lagna]],
        "moon": RAASI_NAMES[moon_rasi],
        "venus": RAASI_NAMES[venus_rasi],
    }


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
    varga_chart = utils.get_house_planet_list_from_planet_positions(
        [["L", (varga_lagna_rasi, 0.0)]]
        + [[planet_id, (rasi, 0.0)] for planet_id, (rasi, _) in positions]
    )
    aspects = {
        planet_id: [
            PLANET_NAMES[other]
            for other in sorted(
                set(house.aspected_planets_of_the_planet(varga_chart, planet_id))
            )
        ]
        for planet_id, _ in positions
    }
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
            "aspects": aspects[planet_id],
            "friendship": _friendship(planet_id),
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
    system: str = "north",
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    location_name: str = DEFAULT_LOCATION,
    girl_latitude: float | None = None,
    girl_longitude: float | None = None,
) -> dict[str, Any]:
    """Return North or South Indian guna milan for two birth charts."""
    key = system.strip().lower()
    if key not in ("north", "south"):
        raise ValueError("system must be north or south")
    _check_coordinates(latitude, longitude)
    girl_lat = latitude if girl_latitude is None else girl_latitude
    girl_lon = longitude if girl_longitude is None else girl_longitude
    _check_coordinates(girl_lat, girl_lon)

    girl_tz = girl_timezone if girl_timezone is not None else timezone
    boy = _moon_details(boy_date, boy_time, timezone, ayanamsa)
    girl = _moon_details(girl_date, girl_time, girl_tz, ayanamsa)

    ashtakoota = Ashtakoota(
        boy["number"],
        boy["pada"],
        girl["number"],
        girl["pada"],
        method=(
            const.CHART_STYLE.SOUTH_INDIAN_REGULAR
            if key == "south"
            else const.CHART_STYLE.NORTH_INDIAN
        ),
    )
    values = ashtakoota.compatibility_score()

    if key == "south":
        scores = {
            "dina": values[3],
            "gana": values[2],
            "mahendra": values[9],
            "sthree_dheerga": values[12],
            "yoni": values[4],
            "raasi": values[6],
            "raasi_adhipathi": values[5],
            "vasiya": values[1],
            "rajju": values[11],
            "vedha": values[10],
        }
        total = values[8]
        maximum = 10
        minimum_porutham = bool(values[13])
        verdict = (
            "recommended"
            if total >= const.compatibility_minimum_score_south
            and minimum_porutham
            else "below traditional minimum"
        )
        extras = {"minimum_porutham": minimum_porutham}
        method_label = "South Indian Porutham"
        note = (
            "South Indian matching scores 10 poruthams; 6/10 and the "
            "minimum poruthams are the traditional minimum."
        )
    else:
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
        maximum = 36
        verdict = (
            "recommended" if total >= 18 else "below traditional minimum"
        )
        extras = {
            "mahendra": values[9],
            "vedha": values[10],
            "rajju": values[11],
            "shree_dheerga": values[12],
        }
        method_label = "North Indian Ashtakoota"
        note = (
            "18/36 is the traditional minimum; this is not a substitute "
            "for a full chart comparison."
        )

    manglik = {
        "boy": _manglik_status(
            boy_date,
            boy_time,
            timezone,
            latitude,
            longitude,
            location_name,
            ayanamsa,
        ),
        "girl": _manglik_status(
            girl_date,
            girl_time,
            girl_tz,
            girl_lat,
            girl_lon,
            location_name,
            ayanamsa,
        ),
        "note": (
            "Mars from the lagna with BV Raman exceptions applied; the "
            "2nd house is included."
        ),
    }

    boy_navamsa = _navamsa_summary(
        boy_date,
        boy_time,
        timezone,
        latitude,
        longitude,
        location_name,
        ayanamsa,
    )
    girl_navamsa = _navamsa_summary(
        girl_date,
        girl_time,
        girl_tz,
        girl_lat,
        girl_lon,
        location_name,
        ayanamsa,
    )
    boy_lord = PLANET_NAMES.index(boy_navamsa["lagna_lord"])
    girl_lord = PLANET_NAMES.index(girl_navamsa["lagna_lord"])
    relation = const.planet_relations[boy_lord][girl_lord]
    navamsa = {
        "boy": boy_navamsa,
        "girl": girl_navamsa,
        "lagna_house_from_boy": (
            RAASI_NAMES.index(girl_navamsa["lagna"])
            - RAASI_NAMES.index(boy_navamsa["lagna"])
        )
        % 12
        + 1,
        "moon_house_from_boy": (
            RAASI_NAMES.index(girl_navamsa["moon"])
            - RAASI_NAMES.index(boy_navamsa["moon"])
        )
        % 12
        + 1,
        "lagna_lord_friendship": {
            5: "same",
            3: "friend",
            2: "neutral",
            1: "enemy",
        }[relation],
        "note": (
            "Informational D9 comparison, not part of the kuta score. "
            "6/8 and 2/12 lagna or Moon placements are traditionally avoided."
        ),
    }

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
        "max": maximum,
        "verdict": verdict,
        "extras": extras,
        "manglik": manglik,
        "navamsa": navamsa,
        "system": {
            "ayanamsa": boy["ayanamsa"],
            "method": method_label,
        },
        "note": note,
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


def chara_dashas(
    date: str,
    time: str,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    as_of: str | None = None,
    as_of_timezone: str | float | None = None,
    depth: int = 2,
    method: str = "kn_rao",
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return the Chara (Jaimini rasi) dasha timeline and running periods."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)
    key = method.strip().lower()
    if key not in CHARA_METHODS:
        raise ValueError(
            f"Unknown method: {method}. Supported: {', '.join(CHARA_METHODS)}"
        )
    if not 1 <= depth <= len(DASHA_LEVELS):
        raise ValueError(f"depth must be between 1 and {len(DASHA_LEVELS)}")

    offset = _offset_hours(timezone, day, birth.hour + birth.minute / 60)
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
    method_value, method_label = CHARA_METHODS[key]

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
        rows = chara.get_dhasa_antardhasa(
            dob,
            tob,
            place,
            dhasa_level_index=1,
            chara_method=method_value,
            return_exact_bounds=True,
        )
        mahadashas = [
            {
                "sign": RAASI_NAMES[sign],
                "lord": PLANET_NAMES[const.house_owners[sign]],
                "start": _tuple_iso(utils.jd_to_gregorian(start), offset),
                "end": _tuple_iso(utils.jd_to_gregorian(end), offset),
                "duration_years": years,
            }
            for (sign,), start, end, years in rows
        ]
        running = [
            {
                "level": DASHA_LEVELS[len(lords) - 1],
                "sign": RAASI_NAMES[lords[-1]],
                "lord": PLANET_NAMES[const.house_owners[lords[-1]]],
                "start": _tuple_iso(start, offset),
                "end": _tuple_iso(end, offset),
            }
            for lords, start, end in chara.get_running_dhasa_for_given_date(
                as_of_jd,
                jd,
                place,
                dhasa_level_index=depth,
                chara_method=method_value,
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
            "dasha": "Chara",
            "method": method_label,
            "ayanamsa": ayanamsa_label,
            "depth": depth,
        },
        "mahadashas": mahadashas,
        "running": running,
    }


def festivals(
    start_date: str,
    end_date: str | None = None,
    latitude: float = DEFAULT_LATITUDE,
    longitude: float = DEFAULT_LONGITUDE,
    timezone: str | float = DEFAULT_TIMEZONE,
    location_name: str = DEFAULT_LOCATION,
    calendar: str = "all",
) -> dict[str, Any]:
    """Return Hindu festivals in a date range with purnimanta month and tithi."""
    start = Date.fromisoformat(start_date)
    end = Date.fromisoformat(end_date) if end_date is not None else start
    if end < start:
        raise ValueError("end_date must not be before start_date")
    if (end - start).days > 366:
        raise ValueError("date range must be 366 days or less")
    _check_coordinates(latitude, longitude)
    key = calendar.strip().lower()
    if key != "all" and key not in FESTIVAL_CALENDARS:
        raise ValueError(
            f"Unknown calendar: {calendar}. Supported: all, "
            f"{', '.join(FESTIVAL_CALENDARS)}"
        )

    offset = _offset_hours(timezone, start)
    place = drik.Place(location_name, latitude, longitude, offset)
    rows_by_day = vratha.get_festivals_between_the_dates(
        drik.Date(start.year, start.month, start.day),
        drik.Date(end.year, end.month, end.day),
        place,
    )

    last_seen: dict[str, Date] = {}
    items = []
    for date_tuple, rows in rows_by_day:
        year, month, day = date_tuple[:3]
        current = Date(year, month, day)
        jd = utils.julian_day_number((year, month, day), (12, 0, 0))
        lunar_month, _, _, adhika, _, _ = drik.vedic_date(
            jd, place, calendar_type=const.CALENDAR_TYPE.LUNAR_PURNIMANTHA
        )
        tithi_number = drik.tithi(jd, place)[0]
        for row in rows:
            row_calendar = int(row["calendar_type"])
            if key == "all":
                if row_calendar == int(FESTIVAL_CALENDARS["gregorian"]):
                    continue
            elif row_calendar != int(FESTIVAL_CALENDARS[key]):
                continue
            name = row["Festival_en"]
            seen = last_seen.get(name)
            if seen is not None and (current - seen).days <= 2:
                continue
            last_seen[name] = current
            items.append(
                {
                    "date": current.isoformat(),
                    "name": name,
                    "calendar": next(
                        (
                            label
                            for label, value in FESTIVAL_CALENDARS.items()
                            if int(value) == row_calendar
                        ),
                        str(row_calendar),
                    ),
                    "month": (
                        ("Adhika " if adhika else "")
                        + utils.MONTH_LIST[lunar_month - 1]
                    ),
                    "tithi": utils.TITHI_LIST[tithi_number - 1],
                    "paksha": (
                        "Shukla" if tithi_number <= 15 else "Krishna"
                    ),
                }
            )

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "location": _location(
            location_name, latitude, longitude, timezone, offset
        ),
        "system": {"months": "purnimanta", "calendar_filter": key},
        "festivals": items,
        "note": (
            "Festival dates are sunrise-based. The same festival within "
            "three days is collapsed to its first occurrence. The all "
            "filter covers solar, amanta and purnimanta; pass gregorian "
            "for civil holidays."
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
