import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from astro_mcp.engine import (
    PLANET_NAMES,
    RAASI_NAMES,
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
    assert dasamsa["lagna"]["sign"] == "Gemini"
    planets = {planet["name"]: planet for planet in dasamsa["planets"]}
    assert planets["Sun"]["sign"] == "Taurus"
    assert planets["Moon"]["sign"] == "Aries"
    assert planets["Mars"]["sign"] == "Sagittarius"


def test_varga_d10_nodes_are_opposite():
    result = varga(
        "1995-05-12",
        "07:00",
        latitude=24.4419,
        longitude=82.9817,
        location_name="Obra",
        division=10,
    )
    planets = {planet["name"]: planet for planet in result["planets"]}

    assert result["lagna"]["sign"] == "Leo"
    assert planets["Rahu"]["sign"] == "Capricorn"
    assert planets["Ketu"]["sign"] == "Cancer"
    assert planets["Rahu"]["house"] == 6
    assert planets["Ketu"]["house"] == 12


def test_cyclic_vargas_keep_nodes_opposite():
    for division in (1, 3, 4, 7, 9, 10, 11, 12, 27, 60):
        result = varga(
            "1995-05-12",
            "07:00",
            latitude=24.4419,
            longitude=82.9817,
            location_name="Obra",
            division=division,
        )
        planets = {planet["name"]: planet for planet in result["planets"]}
        rahu = RAASI_NAMES.index(planets["Rahu"]["sign"])
        ketu = RAASI_NAMES.index(planets["Ketu"]["sign"])
        assert (ketu - rahu) % 12 == 6, division


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


def test_refraction_sunrise_is_earlier():
    hindu = panchang("2026-11-20")
    refraction = panchang("2026-11-20", sunrise_convention="refraction")
    bottom_limb = panchang("2026-11-20", sunrise_convention="bottom_limb")
    muhurta_refraction = muhurta(
        "2026-11-20", sunrise_convention="refraction"
    )

    assert hindu["sunrise"].startswith("2026-11-20T06:22")
    assert refraction["sunrise"].startswith("2026-11-20T06:19")
    assert bottom_limb["sunrise"].startswith("2026-11-20T06:20")
    assert refraction["system"]["sunrise_convention"] == (
        "Center of disc with refraction"
    )
    assert bottom_limb["system"]["sunrise_convention"] == (
        "Bottom limb with refraction"
    )
    assert muhurta_refraction["sunrise"] == refraction["sunrise"]
    assert muhurta_refraction["brahma"]["start"].startswith(
        "2026-11-20T04:3"
    )


def test_dst_birth_uses_the_local_offset():
    result = kundli("2026-03-08", "01:30", timezone="America/New_York")

    assert result["datetime"] == "2026-03-08T01:30:00-05:00"


def test_transits_sade_sati_status():
    result = transits(
        "1995-05-12",
        "07:00",
        as_of="2026-11-21",
        latitude=24.4676,
        longitude=82.9933,
        location_name="Obra",
    )

    assert result["natal"]["moon"]["nakshatra"] == "Hasta"
    assert result["sade_sati"]["active"] is False
    assert result["sade_sati"]["saturn_house_from_moon"] == 7
    saturn = next(p for p in result["planets"] if p["name"] == "Saturn")
    assert saturn["sign"] == "Pisces"
    assert saturn["house_from_lagna"] == 11


def test_yogas_and_doshas_are_detected():
    result = yogas(
        "1995-05-12",
        "07:00",
        latitude=24.4676,
        longitude=82.9933,
        location_name="Obra",
    )

    names = {yoga["name"] for yoga in result["yogas"]}
    assert "Sasa Yoga" in names
    assert "Kala Sarpa Dosha" in result["doshas"]
    assert "no Kala Sarpa" in result["doshas"]["Kala Sarpa Dosha"]


def test_yogas_include_raja_yoga_categories():
    from astro_mcp.engine import _neechabhanga_yoga_items

    result = yogas(
        "1995-05-12",
        "07:00",
        latitude=24.45,
        longitude=82.98,
        location_name="Obra",
    )
    raja = [item for item in result["yogas"] if item["category"] == "raja"]

    assert any(item["key"].startswith("raja_yoga_") for item in raja)
    assert any(item["key"] == "harsha_yoga" for item in raja)
    assert result["system"]["categories"]["raja"] >= 2
    chatussagara = next(
        item for item in result["yogas"] if item["key"] == "chatussagara_yoga"
    )
    assert chatussagara["description"] == (
        "All four Kendra houses (1, 4, 7, 10) are occupied by at least "
        "one planet."
    )

    synthetic = [
        ["L", (0, 0.0)],
        [0, (6, 10.0)],
        [1, (0, 0.0)],
        [2, (0, 0.0)],
        [3, (0, 0.0)],
        [4, (0, 0.0)],
        [5, (0, 0.0)],
        [6, (0, 0.0)],
        [7, (0, 0.0)],
        [8, (0, 0.0)],
    ]
    items = _neechabhanga_yoga_items(synthetic)
    assert any("Sun" in item["planets"] for item in items)
    assert all(item["category"] == "raja" for item in items)


def test_matching_ashtakoota():
    result = matching("1995-05-12", "07:00", "1990-01-01", "12:00")

    assert result["boy"]["nakshatra"] == "Hasta"
    assert result["girl"]["nakshatra"] == "Dhanishta"
    assert set(result["scores"]) == {
        "varna",
        "vasiya",
        "gana",
        "tara",
        "yoni",
        "graha_maitri",
        "bhakoot",
        "nadi",
    }
    assert result["total"] == 20.0
    assert result["max"] == 36
    assert result["verdict"] == "recommended"
    assert result["manglik"]["boy"]["effective"] is False
    assert result["manglik"]["girl"]["effective"] is False


def test_matching_navamsa_comparison():
    result = matching(
        "1995-05-12",
        "07:00",
        "1990-01-01",
        "12:00",
        latitude=24.4676,
        longitude=82.9933,
        location_name="Obra",
    )

    assert result["navamsa"]["boy"]["lagna"] == "Cancer"
    assert result["navamsa"]["girl"]["lagna"] == "Capricorn"
    assert result["navamsa"]["lagna_house_from_boy"] == 7
    assert result["navamsa"]["moon_house_from_boy"] == 6
    assert result["navamsa"]["lagna_lord_friendship"] == "neutral"


def test_matching_fixes_tara_and_varna_kutas():
    result = matching(
        "1995-05-12",
        "07:00",
        "1993-03-20",
        "07:05",
        latitude=24.45,
        longitude=82.98,
        location_name="Obra",
        girl_latitude=27.49,
        girl_longitude=77.67,
    )

    assert result["scores"]["varna"] == 1
    assert result["scores"]["tara"] == 3.0
    assert result["total"] == 20.0
    assert result["verdict"] == "recommended"


def test_matching_tara_for_uttara_phalguni():
    for time, expected in (("03:45", 16.0), ("15:45", 27.0)):
        result = matching("1995-05-12", "07:00", "1995-09-24", time)
        assert result["scores"]["tara"] == 3.0
        assert result["scores"]["gana"] == 6
        assert result["total"] == expected


def test_matching_gana_uses_boy_to_girl_direction():
    result = matching(
        "1995-05-12",
        "07:00",
        "1998-03-22",
        "18:58",
        latitude=24.45,
        longitude=82.98,
        location_name="Obra",
        girl_latitude=28.41,
        girl_longitude=77.31,
    )

    assert result["scores"]["gana"] == 6
    assert result["total"] == 25.5


def test_matching_whole_sign_vasiya():
    result = matching(
        "1995-05-12",
        "07:00",
        "1998-03-22",
        "18:58",
        latitude=24.45,
        longitude=82.98,
        location_name="Obra",
        girl_latitude=28.41,
        girl_longitude=77.31,
        vasya_convention="whole_sign",
    )

    assert result["scores"]["vasiya"] == 2.0
    assert result["total"] == 27.0
    assert result["system"]["vasya_convention"] == "whole_sign"


def test_matching_south_indian_porutham():
    result = matching(
        "1995-05-12",
        "07:00",
        "1990-01-01",
        "12:00",
        system="south",
    )

    assert result["system"]["method"] == "South Indian Porutham"
    assert result["total"] == 7
    assert result["max"] == 10
    assert result["extras"]["minimum_porutham"] is False
    assert result["verdict"] == "below traditional minimum"
    assert len(result["scores"]) == 10


def test_matching_accepts_utc_girl_timezone():
    result = matching(
        "1995-05-12",
        "07:00",
        "1990-01-01",
        "12:00",
        girl_timezone=0.0,
    )

    assert result["girl"]["datetime"] == "1990-01-01T12:00:00+00:00"
    assert result["girl"]["nakshatra"] == "Shatabhisha"
    assert result["total"] == 9.5


def test_surya_siddhanta_is_applied_to_matching():
    lahiri = matching("1995-05-12", "07:00", "1990-01-01", "12:00")
    surya = matching(
        "1995-05-12",
        "07:00",
        "1990-01-01",
        "12:00",
        ayanamsa="SURYA_SIDDHANTA",
    )

    assert surya["system"]["ayanamsa"] == "Surya Siddhanta"
    assert surya["boy"]["degree"] != lahiri["boy"]["degree"]
    assert surya["girl"]["nakshatra"] == "Shatabhisha"
    assert surya["total"] == 9.5


def test_yogini_dashas_running_chain():
    result = yogini_dashas(
        "1995-05-12",
        "07:00",
        latitude=24.4676,
        longitude=82.9933,
        location_name="Obra",
        as_of="2026-11-21",
        depth=3,
    )

    assert len(result["mahadashas"]) == 24
    assert [period["level"] for period in result["running"]] == [
        "Mahadasha",
        "Antardasha",
        "Pratyantardasha",
    ]
    assert [period["yogini"] for period in result["running"]] == [
        "Sankata",
        "Sankata",
        "Dhanya",
    ]


def test_chara_dashas_kn_rao():
    result = chara_dashas(
        "1995-05-12",
        "07:00",
        latitude=24.4676,
        longitude=82.9933,
        location_name="Obra",
        as_of="2026-11-21",
        depth=3,
    )

    assert result["system"]["method"] == "KN Rao"
    assert len(result["mahadashas"]) == 12
    assert result["mahadashas"][0]["sign"] == "Taurus"
    assert result["mahadashas"][0]["lord"] == "Venus"
    assert [period["sign"] for period in result["running"]] == [
        "Capricorn",
        "Pisces",
        "Cancer",
    ]


def test_festivals_include_purnimanta_context():
    result = festivals("2026-11-08")
    by_name = {item["name"]: item for item in result["festivals"]}

    assert result["system"]["months"] == "purnimanta"
    assert "Diwali (Deepavali)" in by_name
    assert by_name["Diwali (Deepavali)"]["month"] == "Karttika"
    assert by_name["Diwali (Deepavali)"]["tithi"] == "Amavasya"
    assert by_name["Diwali (Deepavali)"]["paksha"] == "Krishna"


def test_strength_report():
    result = strength_report(
        "1995-05-12",
        "07:00",
        latitude=24.4676,
        longitude=82.9933,
        location_name="Obra",
    )

    assert result["shadbala"]["total"]["Saturn"] == 598.51
    assert result["shadbala"]["strength"]["Saturn"] == 2.0
    assert result["ashtakavarga"]["sarva"]["Aquarius"] == 38
    assert len(result["ashtakavarga"]["bhinnashtakavarga"]) == 8


def test_combust_planets_are_marked():
    result = kundli("1990-01-01", "12:00")
    planets = {planet["name"]: planet for planet in result["planets"]}

    assert planets["Saturn"]["combust"] is True
    assert planets["Sun"]["combust"] is False
    assert planets["Moon"]["combust"] is False


def test_d9_aspects_and_friendship():
    result = varga(
        "1995-05-12",
        "07:00",
        latitude=24.4676,
        longitude=82.9933,
        location_name="Obra",
        division=9,
    )
    planets = {planet["name"]: planet for planet in result["planets"]}

    assert planets["Saturn"]["aspects"] == ["Sun", "Jupiter"]
    assert planets["Sun"]["aspects"] == ["Moon", "Mercury", "Saturn"]
    assert planets["Sun"]["friendship"]["friends"] == [
        "Moon",
        "Mars",
        "Jupiter",
    ]
    assert set(planets["Sun"]["friendship"]) == {
        "friends",
        "neutral",
        "enemies",
    }


def test_kundli_mean_and_true_nodes():
    true = kundli(
        "1993-03-20",
        "07:05",
        latitude=27.49,
        longitude=77.67,
        location_name="Bareilly",
    )
    mean = kundli(
        "1993-03-20",
        "07:05",
        latitude=27.49,
        longitude=77.67,
        location_name="Bareilly",
        node_type="mean",
    )
    true_rahu = next(p for p in true["planets"] if p["name"] == "Rahu")
    mean_rahu = next(p for p in mean["planets"] if p["name"] == "Rahu")

    assert true["system"]["node_type"] == "True node"
    assert mean["system"]["node_type"] == "Mean node"
    assert true_rahu["degree"] == 21.95
    assert mean_rahu["degree"] == 22.52


def test_traditional_planet_models_put_saturn_in_capricorn():
    args = {
        "date": "1993-09-22",
        "time": "05:36",
        "latitude": 24.4419,
        "longitude": 82.9817,
        "location_name": "Obra",
    }
    drik = kundli(**args)
    surya = kundli(**args, planet_model="surya_siddhanta")
    laghava = kundli(**args, planet_model="graha_laghava")

    drik_saturn = next(p for p in drik["planets"] if p["name"] == "Saturn")
    surya_saturn = next(p for p in surya["planets"] if p["name"] == "Saturn")
    laghava_saturn = next(p for p in laghava["planets"] if p["name"] == "Saturn")

    assert drik_saturn["sign"] == "Aquarius"
    assert drik_saturn["house"] == 6
    assert surya["system"]["planet_model"] == "Surya Siddhanta"
    assert surya_saturn["sign"] == "Capricorn"
    assert surya_saturn["house"] == 5
    assert laghava["system"]["planet_model"] == "Graha Laghava"
    assert laghava_saturn["sign"] == "Capricorn"
    assert laghava_saturn["house"] == 5


def test_dashas_follow_the_planet_model():
    args = {
        "date": "1993-09-22",
        "time": "05:36",
        "latitude": 24.4419,
        "longitude": 82.9817,
        "location_name": "Obra",
        "as_of": "2026-11-22",
    }
    drik = dashas(**args)
    surya = dashas(**args, planet_model="surya_siddhanta")

    assert surya["system"]["planet_model"] == "Surya Siddhanta"
    assert surya["balance_at_birth"] != drik["balance_at_birth"]


def test_panchang_planet_model_label():
    result = panchang("2026-11-22", planet_model="surya_siddhanta")

    assert result["system"]["planet_model"] == "Surya Siddhanta"
    assert result["system"]["ayanamsa"] == "Model default"


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
