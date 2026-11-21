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
    dashas,
    kundli,
    muhurta,
    panchang,
)

server = MCPServer(
    "astro-mcp",
    version="0.1.0",
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
) -> dict[str, Any]:
    """Return the D1 birth chart for a local date, time and place.

    Includes the lagna and each planet's sign, degree, nakshatra, pada,
    whole-sign house and retrograde state. Uses Lahiri ayanamsa.
    """
    return kundli(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
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
) -> dict[str, Any]:
    """Return the Vimshottari mahadasha timeline and the running periods.

    Includes the mahadasha balance at birth and the mahadasha/antardasha
    running on as_of. Uses Lahiri ayanamsa.
    """
    return dashas(
        date=date,
        time=time,
        latitude=latitude,
        longitude=longitude,
        timezone=timezone,
        location_name=location_name,
        as_of=as_of,
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
