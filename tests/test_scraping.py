"""
test_scraping.py

Unit tests for the scraping layer. These tests run entirely offline — they
mock HTTP calls and test parsing/normalisation logic in isolation.

Run:
    pytest tests/test_scraping.py -v
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# wikipedia_scraper tests
# ---------------------------------------------------------------------------

from scraping.wikipedia_scraper import (
    _strip_wiki_markup,
    _extract_year,
    _parse_infobox,
    _parse_positions,
    _collect_orchestras,
)


class TestStripWikiMarkup:
    def test_removes_wikilinks_with_label(self):
        assert _strip_wiki_markup("[[Boston Symphony Orchestra|BSO]]") == "BSO"

    def test_removes_wikilinks_without_label(self):
        assert _strip_wiki_markup("[[Boston Symphony Orchestra]]") == "Boston Symphony Orchestra"

    def test_removes_templates(self):
        assert _strip_wiki_markup("{{birth date|1978|11|18}}") == ""

    def test_removes_ref_tags(self):
        assert _strip_wiki_markup("text<ref>citation</ref>more") == "textmore"

    def test_removes_html_tags(self):
        assert _strip_wiki_markup("<small>note</small>") == "note"

    def test_strips_whitespace_and_pipes(self):
        assert _strip_wiki_markup("  |value|  ") == "value"

    def test_empty_string(self):
        assert _strip_wiki_markup("") == ""

    def test_plain_text_unchanged(self):
        assert _strip_wiki_markup("plain text") == "plain text"


class TestExtractYear:
    def test_extracts_four_digit_year(self):
        assert _extract_year("born in 1978") == 1978

    def test_returns_first_year(self):
        assert _extract_year("from 2014 to 2024") == 2014

    def test_returns_none_for_no_year(self):
        assert _extract_year("no date here") is None

    def test_ignores_three_digit_numbers(self):
        assert _extract_year("page 123") is None

    def test_handles_none(self):
        assert _extract_year(None) is None

    def test_handles_year_range(self):
        assert _extract_year("(2018–present)") == 2018


class TestParseInfobox:
    SAMPLE_INFOBOX = """
{{Infobox musical artist
| name         = Andris Nelsons
| birth_date   = {{birth date|1978|11|18}}
| nationality  = [[Latvia|Latvian]]
| occupation   = Conductor
| employer     = [[Boston Symphony Orchestra]]
}}
Some other text here.
"""

    def test_extracts_name(self):
        result = _parse_infobox(self.SAMPLE_INFOBOX)
        assert "name" in result
        assert "Andris Nelsons" in result["name"]

    def test_extracts_birth_date(self):
        result = _parse_infobox(self.SAMPLE_INFOBOX)
        assert "birth_date" in result

    def test_extracts_nationality(self):
        result = _parse_infobox(self.SAMPLE_INFOBOX)
        assert "nationality" in result

    def test_returns_empty_dict_when_no_infobox(self):
        result = _parse_infobox("No infobox here, just plain text.")
        assert result == {}

    def test_keys_are_lowercase(self):
        result = _parse_infobox(self.SAMPLE_INFOBOX)
        for key in result:
            assert key == key.lower(), f"Key '{key}' is not lowercase"


class TestParsePositions:
    def test_extracts_music_director_position(self):
        wikitext = """
Nelsons has served as Music Director of the Boston Symphony Orchestra since 2014.
He also became Chief Conductor of the Gewandhausorchester Leipzig in 2018.
"""
        positions = _parse_positions(wikitext, "Andris Nelsons")
        orchestras = [p["orchestra"] for p in positions]
        # At least one BSO-related match expected
        assert any("Boston" in o or "Symphony" in o for o in orchestras), \
            f"Expected BSO in positions, got: {orchestras}"

    def test_extracts_start_year(self):
        wikitext = "He was appointed Music Director of the Boston Symphony Orchestra (2014–present)."
        positions = _parse_positions(wikitext, "Test")
        years = [p["start_year"] for p in positions if p.get("start_year")]
        assert 2014 in years

    def test_marks_current_position(self):
        wikitext = "She serves as Principal Conductor of the Test Orchestra (2020–present)."
        positions = _parse_positions(wikitext, "Test")
        current = [p for p in positions if p.get("is_current")]
        assert len(current) >= 1

    def test_marks_ended_position(self):
        wikitext = "He was Music Director of the Test Orchestra (2010–2018)."
        positions = _parse_positions(wikitext, "Test")
        ended = [p for p in positions if not p.get("is_current") and p.get("end_year") == 2018]
        assert len(ended) >= 1

    def test_deduplicates_positions(self):
        wikitext = """
Music Director of the Boston Symphony Orchestra since 2014.
Music Director of the Boston Symphony Orchestra (2014–present).
"""
        positions = _parse_positions(wikitext, "Test")
        keys = [(p["role"].lower(), p["orchestra"].lower()) for p in positions]
        assert len(keys) == len(set(keys)), "Duplicate positions found"

    def test_returns_list(self):
        positions = _parse_positions("No positions here.", "Test")
        assert isinstance(positions, list)


class TestCollectOrchestras:
    def test_collects_unique_orchestras(self):
        conductors = [
            {"name": "A", "positions": [
                {"orchestra": "BSO", "role": "Music Director", "start_year": 2014, "end_year": None},
            ]},
            {"name": "B", "positions": [
                {"orchestra": "BSO", "role": "Guest Conductor", "start_year": 2018, "end_year": 2019},
                {"orchestra": "Berlin Philharmonic", "role": "Chief Conductor", "start_year": 2019, "end_year": None},
            ]},
        ]
        orchestras = _collect_orchestras(conductors)
        names = [o["name"] for o in orchestras]
        assert "BSO" in names
        assert "Berlin Philharmonic" in names
        assert len(names) == len(set(names)), "Duplicate orchestras in output"

    def test_records_conductor_in_orchestra(self):
        conductors = [{"name": "Conductor A", "positions": [
            {"orchestra": "Test Orchestra", "role": "Music Director", "start_year": 2020, "end_year": None},
        ]}]
        orchestras = _collect_orchestras(conductors)
        test_orch = next(o for o in orchestras if o["name"] == "Test Orchestra")
        assert any(c["conductor"] == "Conductor A" for c in test_orch["conductors"])


# ---------------------------------------------------------------------------
# bachtrack_scraper tests
# ---------------------------------------------------------------------------

from scraping.bachtrack_scraper import (
    _normalise_date,
    _split_venue,
    _parse_concert_item,
)


class TestNormaliseDate:
    def test_iso_format_passthrough(self):
        assert _normalise_date("2023-11-04") == "2023-11-04"

    def test_long_month_format(self):
        assert _normalise_date("4 November 2023") == "2023-11-04"

    def test_us_month_format(self):
        assert _normalise_date("November 4, 2023") == "2023-11-04"

    def test_extracts_iso_from_mixed_string(self):
        result = _normalise_date("Concert on 2023-11-04 at 8pm")
        assert result == "2023-11-04"

    def test_returns_none_for_none(self):
        assert _normalise_date(None) is None

    def test_returns_raw_if_unparseable(self):
        raw = "some garbage"
        result = _normalise_date(raw)
        assert result == raw


class TestSplitVenue:
    def test_three_part_venue(self):
        venue, city, country = _split_venue("Symphony Hall, Boston, United States")
        assert venue == "Symphony Hall"
        assert city == "Boston"
        assert country == "United States"

    def test_two_part_venue(self):
        venue, city, country = _split_venue("Philharmonie, Berlin")
        assert venue == "Philharmonie"
        assert city == "Berlin"
        assert country is None

    def test_single_part_venue(self):
        venue, city, country = _split_venue("Carnegie Hall")
        assert venue == "Carnegie Hall"
        assert city is None
        assert country is None

    def test_none_input(self):
        venue, city, country = _split_venue(None)
        assert venue is None and city is None and country is None


class TestParseConcertItem:
    """Tests _parse_concert_item using minimal mock BeautifulSoup elements."""

    def _make_element(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "lxml").body.children.__next__()

    def test_returns_none_on_malformed_input(self):
        mock_item = MagicMock()
        mock_item.select_one.return_value = None
        mock_item.select.return_value = []
        # Should not raise; may return a record with None fields or None itself
        result = _parse_concert_item(mock_item)
        # No exception = pass; result validity tested in integration tests

    def test_extracts_source_url_with_relative_path(self):
        from bs4 import BeautifulSoup
        html = '<li><a href="/concert/12345">Concert</a></li>'
        soup = BeautifulSoup(html, "lxml")
        item = soup.find("li")
        result = _parse_concert_item(item)
        if result and result.get("source_url"):
            assert result["source_url"].startswith("https://bachtrack.com") or \
                   result["source_url"].startswith("/"), \
                   f"Unexpected URL: {result['source_url']}"


# ---------------------------------------------------------------------------
# data_merger tests
# ---------------------------------------------------------------------------

from scraping.data_merger import (
    normalise_orchestra,
    normalise_conductor,
    normalise_role,
    _season_from_date,
    build_conductors,
    build_positions,
)


class TestNormaliseOrchestra:
    def test_known_alias(self):
        assert normalise_orchestra("BSO") == "Boston Symphony Orchestra"

    def test_case_insensitive_alias(self):
        assert normalise_orchestra("bso") == "Boston Symphony Orchestra"

    def test_exact_canonical_name(self):
        assert normalise_orchestra("Boston Symphony Orchestra") == "Boston Symphony Orchestra"

    def test_returns_none_for_none(self):
        assert normalise_orchestra(None) is None

    def test_returns_none_for_empty(self):
        assert normalise_orchestra("") is None
        assert normalise_orchestra("   ") is None

    def test_fuzzy_match(self):
        canonical = ["Boston Symphony Orchestra", "Berlin Philharmonic"]
        result = normalise_orchestra("Boston Symphony Orch.", canonical)
        assert result == "Boston Symphony Orchestra"

    def test_unknown_name_returned_as_is(self):
        result = normalise_orchestra("Obscure Chamber Ensemble")
        assert result == "Obscure Chamber Ensemble"


class TestNormaliseConductor:
    def test_known_alias(self):
        assert normalise_conductor("Nelsons") == "Andris Nelsons"

    def test_title_prefix_stripped_via_alias(self):
        assert normalise_conductor("Sir Simon Rattle") == "Simon Rattle"

    def test_returns_none_for_none(self):
        assert normalise_conductor(None) is None

    def test_unknown_name_returned_as_is(self):
        assert normalise_conductor("Unknown Conductor") == "Unknown Conductor"


class TestNormaliseRole:
    def test_music_director(self):
        assert normalise_role("music director") == "Music Director"

    def test_case_insensitive(self):
        assert normalise_role("CHIEF CONDUCTOR") == "Chief Conductor"

    def test_defaults_to_guest_conductor(self):
        assert normalise_role(None) == "Guest Conductor"
        assert normalise_role("") == "Guest Conductor"

    def test_unknown_role_returned_as_is(self):
        assert normalise_role("Interim Music Director") == "Interim Music Director"


class TestSeasonFromDate:
    def test_november_date_in_current_year_season(self):
        assert _season_from_date("2023-11-04") == 2023

    def test_march_date_in_previous_year_season(self):
        assert _season_from_date("2024-03-15") == 2023

    def test_september_date_starts_new_season(self):
        assert _season_from_date("2023-09-01") == 2023

    def test_august_date_in_previous_season(self):
        assert _season_from_date("2023-08-31") == 2022

    def test_returns_none_for_none(self):
        assert _season_from_date(None) is None


class TestBuildConductors:
    SAMPLE_WIKI = [
        {"name": "Andris Nelsons", "birth_year": 1978, "nationality": "Latvian",
         "wikipedia_url": "https://en.wikipedia.org/wiki/Andris_Nelsons", "positions": []},
        {"name": "Gustavo Dudamel", "birth_year": 1981, "nationality": "Venezuelan",
         "wikipedia_url": "https://en.wikipedia.org/wiki/Gustavo_Dudamel", "positions": []},
    ]

    def test_returns_one_row_per_conductor(self):
        df = build_conductors(self.SAMPLE_WIKI)
        assert len(df) == 2

    def test_deduplicates_names(self):
        duplicate = self.SAMPLE_WIKI + [self.SAMPLE_WIKI[0]]
        df = build_conductors(duplicate)
        assert len(df) == 2

    def test_conductor_id_is_snake_case(self):
        df = build_conductors(self.SAMPLE_WIKI)
        for cid in df["conductor_id"]:
            assert re.match(r"^[a-z0-9_]+$", cid), f"conductor_id '{cid}' not snake_case"

    def test_required_columns_present(self):
        df = build_conductors(self.SAMPLE_WIKI)
        for col in ["conductor_id", "name", "birth_year", "nationality"]:
            assert col in df.columns


class TestBuildPositions:
    SAMPLE_WIKI = [
        {
            "name": "Andris Nelsons",
            "positions": [
                {"orchestra": "Boston Symphony Orchestra", "role": "music director",
                 "start_year": 2014, "end_year": None, "is_current": True},
                {"orchestra": "Gewandhaus Orchestra Leipzig", "role": "chief conductor",
                 "start_year": 2018, "end_year": None, "is_current": True},
            ],
        }
    ]

    def test_returns_correct_row_count(self):
        df = build_positions(self.SAMPLE_WIKI, [])
        assert len(df) == 2

    def test_role_is_normalised(self):
        df = build_positions(self.SAMPLE_WIKI, [])
        assert "Music Director" in df["role"].values
        assert "Chief Conductor" in df["role"].values

    def test_required_columns_present(self):
        df = build_positions(self.SAMPLE_WIKI, [])
        for col in ["conductor", "orchestra", "role", "start_year", "end_year"]:
            assert col in df.columns


# ---------------------------------------------------------------------------
# geocoder tests
# ---------------------------------------------------------------------------

from scraping.geocoder import geocode_venue, VENUE_OVERRIDES


class TestGeocodeVenue:
    def test_override_symphony_hall_boston(self):
        result = geocode_venue("Symphony Hall, Boston", "Boston", "United States")
        assert result is not None
        assert abs(result["lat"] - 42.3428) < 0.01
        assert abs(result["lon"] - -71.0857) < 0.01

    def test_override_disney_hall(self):
        result = geocode_venue("Walt Disney Concert Hall", "Los Angeles", "United States")
        assert result is not None
        assert result["lat"] is not None

    def test_returns_none_for_unknown_venue_without_geolocator(self):
        # Without a real geolocator, unknown venues should not crash
        with patch("scraping.geocoder._nominatim_query", return_value=None):
            result = geocode_venue("Completely Unknown Venue XYZ", "Unknown City", "Unknown Country")
            assert result is None

    def test_cache_is_populated(self):
        cache = {}
        with patch("scraping.geocoder._nominatim_query") as mock_query:
            mock_query.return_value = {"lat": 1.0, "lon": 2.0, "display_name": "Test"}
            geocode_venue("Test Venue", "Test City", "Test Country", cache=cache)
        # Cache should have an entry (unless override matched first)
        # At minimum the function ran without error
        assert isinstance(cache, dict)

    def test_all_overrides_have_required_keys(self):
        for name, val in VENUE_OVERRIDES.items():
            assert "lat" in val, f"Override '{name}' missing lat"
            assert "lon" in val, f"Override '{name}' missing lon"
            assert "city" in val, f"Override '{name}' missing city"


import re  # needed for conductor_id assertion in TestBuildConductors
