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
    dashas,
    kundli,
    muhurta,
    panchang,
    varga,
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

server = MCPServer(
    "astro-mcp",
    version="0.2.0",
    instructions=(
        "Vedic panchang calculations using Drik ganita and Lahiri ayanamsa. "
        "Defaults to Varanasi; pass coordinates for another place."
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
