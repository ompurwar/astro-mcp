"""Vedic panchang calculations backed by PyJHora."""

from __future__ import annotations

import io
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
    from jhora.horoscope.dhasa.graha import vimsottari

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
    "SURYA_SIDDHANTA": "Surya Siddhanta",
    "SURYA_SIDDHANTA_MSUN": "Surya Siddhanta (Mean Sun)",
    "ARYABHATA": "Aryabhata",
    "ARYABHATA_MSUN": "Aryabhata (Mean Sun)",
    "SS_CITRA": "Surya Siddhanta Chitra",
    "SS_REVATI": "Surya Siddhanta Revati",
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

_AYANAMSA_LOCK = threading.Lock()


@contextmanager
def _use_ayanamsa(mode: str):
    key = mode.strip().upper()
    if key not in AYANAMSA_MODES:
        raise ValueError(
            f"Unknown ayanamsa: {mode}. Supported: {', '.join(AYANAMSA_MODES)}"
        )
    with _AYANAMSA_LOCK:
        drik.set_ayanamsa_mode(key)
        yield AYANAMSA_MODES[key]

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
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return the five limbs of the panchang at sunrise for a date and place."""
    day = Date.fromisoformat(date)
    _check_coordinates(latitude, longitude)

    offset = _offset_hours(timezone, day)
    place = drik.Place(location_name, latitude, longitude, offset)
    jd = utils.julian_day_number((day.year, day.month, day.day), (12, 0, 0))

    with _use_ayanamsa(ayanamsa) as ayanamsa_label:
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

    offset = _offset_hours(timezone, day)
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

    planets = []
    for planet_id, (rasi, degree) in positions:
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

    offset = _offset_hours(timezone, day)
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
        positions = drik.dhasavarga(
            jd, place, divisional_chart_factor=division
        )

    planets = [
        {
            "name": PLANET_NAMES[planet_id],
            "sign": RAASI_NAMES[rasi],
            "house": (rasi - varga_lagna_rasi) % 12 + 1,
            "retrograde": planet_id in retrograde,
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

    offset = _offset_hours(timezone, day)
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
    depth: int = 2,
    ayanamsa: str = "LAHIRI",
) -> dict[str, Any]:
    """Return the Vimshottari mahadasha timeline and running periods."""
    day = Date.fromisoformat(date)
    birth = _birth_datetime(date, time)
    _check_coordinates(latitude, longitude)
    if not 1 <= depth <= len(DASHA_LEVELS):
        raise ValueError(f"depth must be between 1 and {len(DASHA_LEVELS)}")

    offset = _offset_hours(timezone, day)
    place = drik.Place(location_name, latitude, longitude, offset)
    dob = (birth.year, birth.month, birth.day)
    tob = (birth.hour, birth.minute, birth.second)
    jd = utils.julian_day_number(dob, tob)

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
