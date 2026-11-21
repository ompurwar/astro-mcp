"""MCP server exposing Vedic panchang calculations."""

from __future__ import annotations

import os
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from .engine import (
    DEFAULT_LATITUDE,
    DEFAULT_LOCATION,
    DEFAULT_LONGITUDE,
    DEFAULT_TIMEZONE,
    bhava_chalit,
    chara_dashas,
    dashas,
    festivals,
    kundli,
    matching,
    muhurta,
    panchang,
    strength_report,
    transits,
    varga,
    yogas,
    yogini_dashas,
)

Ayanamsa = Annotated[
    str,
    Field(
        description=(
            "Ayanamsa mode: LAHIRI (default), RAMAN, KP, TRUE_CHITRA, "
            "TRUE_PUSHYA, YUKTESHWAR, FAGAN or SURYA_SIDDHANTA."
        )
    ),
]
SunriseConvention = Annotated[
    str,
    Field(
        description=(
            "Sunrise convention: hindu (default, disc center no refraction), "
            "refraction (center with refraction), or bottom_limb."
        )
    ),
]
AsOfTimezone = Annotated[
    str | float | None,
    Field(
        description=(
            "IANA timezone or fixed UTC offset used for the default as_of "
            "date; defaults to the birth timezone."
        )
    ),
]
CharaMethod = Annotated[
    str,
    Field(
        description=(
            "Chara dasha method: kn_rao (default), pvn_rao, "
            "irangatti_male or irangatti_female."
        )
    ),
]
FestivalCalendar = Annotated[
    str,
    Field(
        description=(
            "Calendar filter: all (default), purnimanta, amanta, solar "
            "or gregorian."
        )
    ),
]

server = MCPServer(
    "astro-mcp",
    version="0.5.1",
    instructions=(
        "Vedic astrology using Drik ganita and a selectable ayanamsa "
        "(Lahiri by default). Panchang, kundli, varga charts, bhava "
        "chalit, Vimshottari, Yogini and Chara dashas, transits with Sade "
        "Sati, yogas and doshas, Shadbala and Ashtakavarga, North and South "
        "Indian guna milan with Manglik and D9 comparison, muhurta and "
        "festivals. Defaults to Varanasi; pass coordinates for another place."
    ),
)


@server.tool()
def get_panchang(
    date: Annotated[str, Field(description="Local date in YYYY-MM-DD format.")],
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    ayanamsa: Ayanamsa = "LAHIRI",
    sunrise_convention: SunriseConvention = "hindu",
) -> dict[str, Any]:
    """Return sunrise, sunset, tithi, nakshatra, yoga, karana and vara for a date.

    Panchang elements are read at local sunrise. The result includes each
    element's start and end time in the requested location's local time.
    """
    return panchang(
        date=date,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        ayanamsa=ayanamsa,
        sunrise_convention=sunrise_convention,
    )


@server.tool()
def get_kundli(
    date: Annotated[str, Field(description="Local birth date in YYYY-MM-DD format.")],
    time: Annotated[
        str, Field(description="Local birth time in 24-hour HH:MM format.")
    ],
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    ayanamsa: Ayanamsa = "LAHIRI",
) -> dict[str, Any]:
    """Return the D1 birth chart for a local date, time and place.

    Includes the lagna and each planet's sign, degree, nakshatra, pada,
    whole-sign house and retrograde state.
    """
    return kundli(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        ayanamsa=ayanamsa,
    )


@server.tool()
def get_dashas(
    date: Annotated[str, Field(description="Local birth date in YYYY-MM-DD format.")],
    time: Annotated[
        str, Field(description="Local birth time in 24-hour HH:MM format.")
    ],
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    as_of: Annotated[
        str | None,
        Field(
            description=(
                "Date in YYYY-MM-DD to evaluate the running dasha; "
                "defaults to today."
            )
        ),
    ] = None,
    as_of_timezone: AsOfTimezone = None,
    depth: Annotated[
        int,
        Field(
            description=(
                "Dasha depth: 1=maha, 2=antar (default), 3=pratyantar, "
                "4=sookshma, 5=prana, 6=deha."
            )
        ),
    ] = 2,
    ayanamsa: Ayanamsa = "LAHIRI",
) -> dict[str, Any]:
    """Return the Vimshottari mahadasha timeline and the running periods.

    Includes the mahadasha balance at birth and the running chain up to
    the requested depth on as_of.
    """
    return dashas(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        as_of=as_of,
        as_of_timezone=as_of_timezone,
        depth=depth,
        ayanamsa=ayanamsa,
    )


@server.tool()
def get_varga(
    date: Annotated[str, Field(description="Local birth date in YYYY-MM-DD format.")],
    time: Annotated[
        str, Field(description="Local birth time in 24-hour HH:MM format.")
    ],
    division: Annotated[
        int,
        Field(
            description=(
                "Varga division: 9=Navamsa (default), 10=Dasamsa, "
                "7=Saptamsa, 12=Dwadamsa, 60=Shastyamsa, etc."
            )
        ),
    ] = 9,
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    ayanamsa: Ayanamsa = "LAHIRI",
) -> dict[str, Any]:
    """Return a divisional (varga) chart such as Navamsa D9 or Dasamsa D10.

    Varga charts show signs and whole-sign houses from the varga lagna.
    """
    return varga(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        division=division,
        ayanamsa=ayanamsa,
    )


@server.tool()
def get_bhava_chalit(
    date: Annotated[str, Field(description="Local birth date in YYYY-MM-DD format.")],
    time: Annotated[
        str, Field(description="Local birth time in 24-hour HH:MM format.")
    ],
    house_system: Annotated[
        str,
        Field(
            description=(
                "House system: sripati (default), kp/placidus, or equal."
            )
        ),
    ] = "sripati",
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    ayanamsa: Ayanamsa = "LAHIRI",
) -> dict[str, Any]:
    """Return the degree-based bhava chalit chart.

    Includes the 12 house cusps and each planet's bhava placement.
    """
    return bhava_chalit(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        house_system=house_system,
        ayanamsa=ayanamsa,
    )


@server.tool()
def get_transits(
    date: Annotated[str, Field(description="Natal date in YYYY-MM-DD format.")],
    time: Annotated[
        str, Field(description="Natal time in 24-hour HH:MM format.")
    ],
    as_of: Annotated[
        str | None,
        Field(description="Transit date in YYYY-MM-DD; defaults to today."),
    ] = None,
    as_of_time: Annotated[
        str, Field(description="Transit time in 24-hour HH:MM format.")
    ] = "12:00",
    as_of_timezone: AsOfTimezone = None,
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    ayanamsa: Ayanamsa = "LAHIRI",
) -> dict[str, Any]:
    """Return current transits against the natal lagna and Moon.

    Includes each planet's house from the natal lagna and natal Moon, and
    the current Sade Sati status from Saturn's transit.
    """
    return transits(
        date=date,
        time=time,
        as_of=as_of,
        as_of_time=as_of_time,
        as_of_timezone=as_of_timezone,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        ayanamsa=ayanamsa,
    )


@server.tool()
def get_yogas(
    date: Annotated[str, Field(description="Local birth date in YYYY-MM-DD format.")],
    time: Annotated[
        str, Field(description="Local birth time in 24-hour HH:MM format.")
    ],
    division: Annotated[
        int,
        Field(description="Varga division for yoga checks: 1=Rasi (default), 9=Navamsa, etc."),
    ] = 1,
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    ayanamsa: Ayanamsa = "LAHIRI",
) -> dict[str, Any]:
    """Return classical yogas and doshas detected in a chart.

    Includes Manglik, Kala Sarpa, Pitru, Guru Chandala and other doshas,
    plus the matched yoga rules and their traditional effects.
    """
    return yogas(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        division=division,
        ayanamsa=ayanamsa,
    )


@server.tool()
def get_yogini_dashas(
    date: Annotated[str, Field(description="Local birth date in YYYY-MM-DD format.")],
    time: Annotated[
        str, Field(description="Local birth time in 24-hour HH:MM format.")
    ],
    as_of: Annotated[
        str | None,
        Field(
            description=(
                "Date in YYYY-MM-DD to evaluate the running dasha; "
                "defaults to today."
            )
        ),
    ] = None,
    as_of_timezone: AsOfTimezone = None,
    depth: Annotated[
        int,
        Field(
            description=(
                "Dasha depth: 1=maha, 2=antar (default), 3=pratyantar, "
                "4=sookshma, 5=prana, 6=deha."
            )
        ),
    ] = 2,
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    ayanamsa: Ayanamsa = "LAHIRI",
) -> dict[str, Any]:
    """Return the Yogini dasha timeline and running periods.

    Includes both the Yogini name and its ruling planet at each level.
    """
    return yogini_dashas(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        as_of=as_of,
        as_of_timezone=as_of_timezone,
        depth=depth,
        ayanamsa=ayanamsa,
    )


@server.tool()
def get_chara_dashas(
    date: Annotated[str, Field(description="Local birth date in YYYY-MM-DD format.")],
    time: Annotated[
        str, Field(description="Local birth time in 24-hour HH:MM format.")
    ],
    as_of: Annotated[
        str | None,
        Field(
            description=(
                "Date in YYYY-MM-DD to evaluate the running dasha; "
                "defaults to today."
            )
        ),
    ] = None,
    as_of_timezone: AsOfTimezone = None,
    depth: Annotated[
        int,
        Field(
            description=(
                "Dasha depth: 1=maha, 2=antar (default), 3=pratyantar, "
                "4=sookshma, 5=prana, 6=deha."
            )
        ),
    ] = 2,
    method: CharaMethod = "kn_rao",
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    ayanamsa: Ayanamsa = "LAHIRI",
) -> dict[str, Any]:
    """Return the Chara (Jaimini rasi) dasha timeline and running periods.

    Each period is a rasi and its sign lord. Choose KN Rao, PVN Rao or the
    Irangatti male/female method.
    """
    return chara_dashas(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        as_of=as_of,
        as_of_timezone=as_of_timezone,
        depth=depth,
        method=method,
        ayanamsa=ayanamsa,
    )


@server.tool()
def get_strength(
    date: Annotated[str, Field(description="Local birth date in YYYY-MM-DD format.")],
    time: Annotated[
        str, Field(description="Local birth time in 24-hour HH:MM format.")
    ],
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    ayanamsa: Ayanamsa = "LAHIRI",
) -> dict[str, Any]:
    """Return Shadbala and Ashtakavarga bindus.

    Shadbala totals are in virupas; strength is the ratio to the required
    minimum. Ashtakavarga returns Sarvashtakavarga and Bhinnashtakavarga.
    """
    return strength_report(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        ayanamsa=ayanamsa,
    )


@server.tool()
def get_matching(
    boy_date: Annotated[
        str, Field(description="Boy's birth date in YYYY-MM-DD format.")
    ],
    boy_time: Annotated[
        str, Field(description="Boy's birth time in 24-hour HH:MM format.")
    ],
    girl_date: Annotated[
        str, Field(description="Girl's birth date in YYYY-MM-DD format.")
    ],
    girl_time: Annotated[
        str, Field(description="Girl's birth time in 24-hour HH:MM format.")
    ],
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "Boy's IANA timezone or fixed UTC offset; also used for the "
                "girl unless girl_timezone is set."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    girl_timezone: Annotated[
        str | float | None,
        Field(description="Girl's timezone, if different from the boy's."),
    ] = None,
    ayanamsa: Ayanamsa = "LAHIRI",
    system: Annotated[
        str,
        Field(
            description=(
                "Matching system: north (Ashtakoota, 36 points) or "
                "south (Porutham, 10 checks)."
            )
        ),
    ] = "north",
    latitude: Annotated[
        float, Field(description="Boy's latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Boy's longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    girl_latitude: Annotated[
        float | None,
        Field(description="Girl's latitude, if different from the boy's."),
    ] = None,
    girl_longitude: Annotated[
        float | None,
        Field(description="Girl's longitude, if different from the boy's."),
    ] = None,
) -> dict[str, Any]:
    """Return guna milan for two birth charts, with Manglik status.

    North Indian Ashtakoota scores out of 36; South Indian Porutham checks
    10 poruthams with a 6/10 minimum. Manglik is computed from Mars' house
    from the lagna with BV Raman exceptions applied.
    """
    return matching(
        boy_date=boy_date,
        boy_time=boy_time,
        girl_date=girl_date,
        girl_time=girl_time,
        timezone=timezone,
        girl_timezone=girl_timezone,
        ayanamsa=ayanamsa,
        system=system,
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        girl_latitude=girl_latitude,
        girl_longitude=girl_longitude,
    )


@server.tool()
def get_muhurta(
    date: Annotated[str, Field(description="Local date in YYYY-MM-DD format.")],
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    sunrise_convention: SunriseConvention = "hindu",
) -> dict[str, Any]:
    """Return the day's auspicious and inauspicious time windows.

    Includes Abhijit and Brahma muhurta, Rahu kaalam, Yamagandam, Gulika
    and Durmuhurtam. Windows are in the requested location's local time.
    """
    return muhurta(
        date=date,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        sunrise_convention=sunrise_convention,
    )


@server.tool()
def get_festivals(
    start_date: Annotated[
        str, Field(description="Start date in YYYY-MM-DD format.")
    ],
    end_date: Annotated[
        str | None,
        Field(description="End date in YYYY-MM-DD; defaults to start_date."),
    ] = None,
    latitude: Annotated[
        float, Field(description="Latitude in degrees; north is positive.")
    ] = DEFAULT_LATITUDE,
    longitude: Annotated[
        float, Field(description="Longitude in degrees; east is positive.")
    ] = DEFAULT_LONGITUDE,
    timezone: Annotated[
        str | float,
        Field(
            description=(
                "IANA timezone name (e.g. Asia/Kolkata) or a fixed UTC offset "
                "in hours (e.g. 5.5)."
            )
        ),
    ] = DEFAULT_TIMEZONE,
    location_name: Annotated[
        str, Field(description="Display name for the location.")
    ] = DEFAULT_LOCATION,
    calendar: FestivalCalendar = "all",
) -> dict[str, Any]:
    """Return Hindu festivals in a date range.

    Each item includes the purnimanta month, tithi and paksha, plus the
    calendar the festival entry came from. The range is capped at 366 days.
    """
    return festivals(
        start_date=start_date,
        end_date=end_date,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        calendar=calendar,
    )


def main() -> None:
    port = os.environ.get("PORT")
    if port:
        server.run(
            "streamable-http",
            host="0.0.0.0",
            port=int(port),
            streamable_http_path="/mcp",
            stateless_http=True,
            json_response=True,
            transport_security=TransportSecuritySettings(
                enable_dns_rebinding_protection=False
            ),
        )
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
