import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from astro_mcp.engine import (
    PLANET_NAMES,
    bhava_chalit,
    dashas,
    kundli,
    muhurta,
    panchang,
    varga,
)


def test_panchang_varanasi_matches_drik_reference():
    # Reference: Drik Panchang, Varanasi, 20 Nov 2026 (sunrise-based day).
    result = panchang("2026-11-20")

    assert result["vara"]["name"] == "Friday"
    assert result["tithi"]["name"] == "Dashami"
    assert result["tithi"]["paksha"] == "Shukla"
    assert result["tithi"]["end"].startswith("2026-11-20T07:1")
    assert result["nakshatra"]["name"] == "Purva Bhadrapada"
    assert result["nakshatra"]["pada"] == 4
    assert result["nakshatra"]["start"].startswith("2026-11-19T06:10")
    start = datetime.fromisoformat(result["nakshatra"]["start"])
    end = datetime.fromisoformat(result["nakshatra"]["end"])
    assert 20 < (end - start).total_seconds() / 3600 < 28
    assert result["yoga"]["name"] == "Harshana"
    assert result["karana"]["name"] == "Gara"
    assert result["sunrise"].startswith("2026-11-20T06:2")
    assert result["sunset"].startswith("2026-11-20T17:0")


def test_kundli_varanasi_reference():
    result = kundli("1990-01-01", "12:00")

    assert result["lagna"] == {
        "sign": "Pisces",
        "degree": 21.45,
        "nakshatra": "Revati",
        "pada": 2,
    }

    planets = {planet["name"]: planet for planet in result["planets"]}
    assert tuple(planets) == PLANET_NAMES
    assert planets["Sun"]["sign"] == "Sagittarius"
    assert planets["Sun"]["house"] == 10
    assert planets["Moon"]["nakshatra"] == "Dhanishta"
    assert planets["Moon"]["pada"] == 4
    assert planets["Mercury"]["house"] == 11
    assert planets["Mercury"]["retrograde"] is True
    assert all(1 <= planet["house"] <= 12 for planet in planets.values())


def test_dashas_varanasi_reference():
    result = dashas("1990-01-01", "12:00", as_of="2026-11-20")

    assert result["balance_at_birth"] == {"years": 0, "months": 1, "days": 7}
    assert len(result["mahadashas"]) == 9
    assert result["mahadashas"][0]["lord"] == "Mars"
    assert [period["lord"] for period in result["running"]] == [
        "Saturn",
        "Saturn",
    ]
    assert result["running"][0]["start"].startswith("2024-02-08")
    assert result["running"][1]["end"].startswith("2027-02-10")


def test_running_antardasha_uses_child_lord():
    # Jupiter mahadasha, Saturn antardasha on 20 Nov 2026.
    result = dashas(
        "1995-05-12",
        "07:00",
        latitude=24.4676,
        longitude=82.9933,
        location_name="Obra",
        as_of="2026-11-20",
    )

    assert [period["lord"] for period in result["running"]] == [
        "Jupiter",
        "Saturn",
    ]
    assert result["running"][1]["start"].startswith("2026-02-17")
    assert result["running"][1]["end"].startswith("2028-09-02")


def test_dashas_rejects_as_of_before_birth():
    with pytest.raises(ValueError):
        dashas("1990-01-01", "12:00", as_of="1989-12-31")


def test_muhurta_varanasi_reference():
    result = muhurta("2026-11-20")

    assert result["rahu_kaalam"]["start"].startswith("2026-11-20T10:23")
    assert result["yamagandam"]["start"].startswith("2026-11-20T14:24")
    assert result["gulika"]["start"].startswith("2026-11-20T07:42")
    assert result["abhijit"]["start"].startswith("2026-11-20T11:22")
    assert result["brahma"]["start"].startswith("2026-11-20T04:36")
    assert len(result["durmuhurtam"]) == 2


def test_ayanamsa_changes_lagna():
    lahiri = kundli("1990-01-01", "12:00")
    raman = kundli("1990-01-01", "12:00", ayanamsa="RAMAN")

    assert raman["system"]["ayanamsa"] == "Raman"
    assert raman["lagna"]["degree"] != lahiri["lagna"]["degree"]


def test_varga_navamsa_and_dasamsa():
    navamsa = varga("1990-01-01", "12:00", division=9)
    assert navamsa["system"]["varga"] == "Navamsa"
    assert navamsa["lagna"]["sign"] == "Capricorn"
    planets = {planet["name"]: planet for planet in navamsa["planets"]}
    assert planets["Sun"]["sign"] == "Virgo"
    assert planets["Moon"]["sign"] == "Scorpio"
    assert planets["Venus"]["sign"] == "Aries"
    assert planets["Rahu"]["house"] == 7

    dasamsa = varga("1990-01-01", "12:00", division=10)
    assert dasamsa["system"]["varga"] == "Dasamsa"
    assert dasamsa["lagna"]["sign"] == "Capricorn"
    planets = {planet["name"]: planet for planet in dasamsa["planets"]}
    assert planets["Sun"]["sign"] == "Taurus"
    assert planets["Moon"]["sign"] == "Libra"
    assert planets["Mars"]["sign"] == "Cancer"


def test_bhava_chalit_sripati_and_kp():
    sripati = bhava_chalit("1990-01-01", "12:00", house_system="sripati")
    assert sripati["system"]["house_system"] == "Sripati"
    assert sripati["houses"][0]["start"] == {
        "sign": "Pisces",
        "degree": 21.45,
    }
    planets = {planet["name"]: planet for planet in sripati["planets"]}
    assert planets["Moon"]["bhava"] == 11
    assert planets["Mercury"]["bhava"] == 10
    assert planets["Ketu"]["bhava"] == 5

    kp = bhava_chalit("1990-01-01", "12:00", house_system="kp")
    assert kp["system"]["house_system"] == "KP (Placidus)"
    planets = {planet["name"]: planet for planet in kp["planets"]}
    assert planets["Venus"]["bhava"] == 11


def test_dasha_depth_includes_pratyantar():
    result = dashas(
        "1995-05-12",
        "07:00",
        latitude=24.4676,
        longitude=82.9933,
        location_name="Obra",
        as_of="2026-11-21",
        depth=3,
    )

    assert [period["level"] for period in result["running"]] == [
        "Mahadasha",
        "Antardasha",
        "Pratyantardasha",
    ]
    assert [period["lord"] for period in result["running"]] == [
        "Jupiter",
        "Saturn",
        "Mercury",
    ]
    assert result["running"][2]["start"].startswith("2026-07-15")
    assert result["running"][2]["end"].startswith("2026-11-24")


def test_import_keeps_stdout_clean():
    src = str(Path(__file__).resolve().parents[1] / "src")
    result = subprocess.run(
        [sys.executable, "-c", "import astro_mcp.engine"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": src},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
