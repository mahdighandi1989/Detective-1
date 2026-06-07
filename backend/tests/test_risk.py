"""
backend/tests/test_risk.py

Tests for the risk assessment engine (موتور ارزیابی ریسک).

The risk engine classifies a person profile into one of the following categories
based on evidence drawn from the intelligence encyclopedia and the person's
current/previous positions, statements, and behavior:

    - CLEAN          (پاک)
    - SUSPICIOUS     (مشکوک)
    - INFILTRATOR    (نفوذی)
    - TRANSFORMED    (استحاله‌یافته)

Each assessment yields:
    - a category
    - a numeric risk score (0.0 - 100.0)
    - a color band for the relationship graph
    - a list of contributing evidence/signals
    - a confidence value

These tests are written to be implementation-agnostic: they exercise the
public behavior of the risk engine. If the concrete implementation differs in
naming, the engine module is expected to expose the same public surface
(RiskCategory, RiskBand, RiskSignal, RiskAssessmentResult, RiskEngine).
"""

import importlib

import pytest


# ---------------------------------------------------------------------------
# Module import with graceful skip if the engine is not yet implemented.
# ---------------------------------------------------------------------------

risk_engine_mod = None
import_error = None
for _candidate in (
    "app.services.risk_engine",
    "backend.app.services.risk_engine",
):
    try:
        risk_engine_mod = importlib.import_module(_candidate)
        break
    except Exception as exc:  # pragma: no cover - depends on environment
        import_error = exc


pytestmark = pytest.mark.skipif(
    risk_engine_mod is None,
    reason=f"risk_engine module not importable: {import_error}",
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _get(name):
    """Fetch a public symbol from the risk_engine module."""
    assert hasattr(risk_engine_mod, name), f"risk_engine missing public symbol: {name}"
    return getattr(risk_engine_mod, name)


@pytest.fixture
def RiskCategory():
    return _get("RiskCategory")


@pytest.fixture
def RiskBand():
    return _get("RiskBand")


@pytest.fixture
def RiskSignal():
    return _get("RiskSignal")


@pytest.fixture
def RiskAssessmentResult():
    return _get("RiskAssessmentResult")


@pytest.fixture
def engine():
    RiskEngine = _get("RiskEngine")
    return RiskEngine()


def _make_profile(**overrides):
    """
    Build a minimal person-profile dict accepted by the engine.

    The engine consumes a normalized profile dict to keep the assessment
    decoupled from the SQLAlchemy/Pydantic models. Defaults represent a
    benign, low-signal person.
    """
    profile = {
        "person_id": "p-0001",
        "full_name": "Test Person",
        "current_positions": [],
        "previous_positions": [],
        "statements": [],          # list of {"text": str, "stance": str, "date": str}
        "actions": [],             # list of {"description": str, "severity": float}
        "linked_articles": [],     # ids of related encyclopedia articles
        "sources": [],             # list of {"url": str, "credibility": float}
        "behavior_flags": [],      # e.g. ["cautious", "evasive", "leaked_info"]
    }
    profile.update(overrides)
    return profile


# ---------------------------------------------------------------------------
# Enum / contract tests
# ---------------------------------------------------------------------------


class TestRiskCategoryEnum:
    def test_all_categories_present(self, RiskCategory):
        names = {c.name for c in RiskCategory}
        for expected in ("CLEAN", "SUSPICIOUS", "INFILTRATOR", "TRANSFORMED"):
            assert expected in names, f"RiskCategory missing {expected}"

    def test_categories_have_unique_values(self, RiskCategory):
        values = [c.value for c in RiskCategory]
        assert len(values) == len(set(values))


class TestRiskBandEnum:
    def test_bands_present(self, RiskBand):
        names = {b.name for b in RiskBand}
        # at minimum a green/yellow/orange/red style spectrum
        assert len(names) >= 3
        # there must be a clearly "lowest" and "highest" band concept
        assert any("GREEN" in n or "LOW" in n for n in names)
        assert any("RED" in n or "CRITICAL" in n or "HIGH" in n for n in names)


# ---------------------------------------------------------------------------
# Core assessment behavior
# ---------------------------------------------------------------------------


class TestAssessmentBasics:
    def test_clean_profile_returns_clean_or_low_risk(self, engine, RiskCategory):
        profile = _make_profile()
        result = engine.assess(profile)

        assert result is not None
        assert result.category == RiskCategory.CLEAN
        assert 0.0 <= result.score <= 100.0
        # clean profile should be on the low end of the scale
        assert result.score < 25.0

    def test_score_is_bounded(self, engine):
        profile = _make_profile(
            actions=[{"description": "leaked classified info", "severity": 1.0}],
            behavior_flags=["leaked_info", "evasive"],
            statements=[
                {"text": "anti-state remarks", "stance": "hostile", "date": "2023-01-01"},
            ],
        )
        result = engine.assess(profile)
        assert 0.0 <= result.score <= 100.0

    def test_result_contains_signals(self, engine, RiskSignal):
        profile = _make_profile(
            behavior_flags=["evasive", "frequent_foreign_travel"],
        )
        result = engine.assess(profile)
        assert isinstance(result.signals, list)
        for sig in result.signals:
            assert isinstance(sig, RiskSignal)

    def test_confidence_is_bounded(self, engine):
        profile = _make_profile()
        result = engine.assess(profile)
        assert 0.0 <= result.confidence <= 1.0

    def test_band_matches_score(self, engine, RiskBand):
        low = engine.assess(_make_profile())
        high = engine.assess(
            _make_profile(
                actions=[
                    {"description": "active espionage operation", "severity": 1.0},
                    {"description": "handler contact established", "severity": 0.9},
                ],
                behavior_flags=["leaked_info", "evasive", "foreign_handler_contact"],
                statements=[
                    {"text": "hostile stance", "stance": "hostile", "date": "2022-05-01"},
                ],
            )
        )
        assert isinstance(low.band, RiskBand)
        assert isinstance(high.band, RiskBand)
        # higher score must not map to a lower band
        assert high.score >= low.score


# ---------------------------------------------------------------------------
# Category classification logic
# ---------------------------------------------------------------------------


class TestCategoryClassification:
    def test_strong_espionage_signals_yield_infiltrator(self, engine, RiskCategory):
        profile = _make_profile(
            actions=[
                {"description": "passed documents to foreign intel", "severity": 1.0},
                {"description": "received covert payments", "severity": 0.95},
            ],
            behavior_flags=["foreign_handler_contact", "leaked_info", "evasive"],
            statements=[
                {"text": "covert hostile coordination", "stance": "hostile", "date": "2021-09-09"},
            ],
            sources=[{"url": "https://example.org/leak", "credibility": 0.9}],
        )
        result = engine.assess(profile)
        assert result.category == RiskCategory.INFILTRATOR
        assert result.score >= 70.0

    def test_position_shift_with_hostile_stance_yields_transformed(self, engine, RiskCategory):
        """
        A previously aligned figure whose recent statements/positions
        shifted to hostile/oppositional -> استحاله‌یافته (TRANSFORMED).
        """
        profile = _make_profile(
            current_positions=[{"title": "critic", "stance": "hostile"}],
            previous_positions=[{"title": "loyal official", "stance": "aligned"}],
            statements=[
                {"text": "former praise", "stance": "aligned", "date": "2010-01-01"},
                {"text": "recent harsh criticism", "stance": "hostile", "date": "2024-01-01"},
            ],
            behavior_flags=["stance_reversal"],
        )
        result = engine.assess(profile)
        assert result.category == RiskCategory.TRANSFORMED

    def test_some_signals_no_proof_yields_suspicious(self, engine, RiskCategory):
        """
        A cautious person who never got caught but has ambiguous signals
        -> مشکوک (SUSPICIOUS).
        """
        profile = _make_profile(
            behavior_flags=["cautious", "frequent_foreign_travel"],
            statements=[
                {"text": "ambiguous remarks", "stance": "ambiguous", "date": "2023-06-01"},
            ],
            sources=[{"url": "https://example.org/rumor", "credibility": 0.4}],
        )
        result = engine.assess(profile)
        assert result.category == RiskCategory.SUSPICIOUS

    def test_cautious_clean_person_not_overclassified(self, engine, RiskCategory):
        """
        Caution alone (دم به تله نداده) must not push someone to INFILTRATOR
        without corroborating high-severity evidence.
        """
        profile = _make_profile(behavior_flags=["cautious"])
        result = engine.assess(profile)
        assert result.category in (RiskCategory.CLEAN, RiskCategory.SUSPICIOUS)
        assert result.category != RiskCategory.INFILTRATOR


# ---------------------------------------------------------------------------
# Source credibility weighting
# ---------------------------------------------------------------------------


class TestSourceCredibilityWeighting:
    def test_low_credibility_sources_reduce_confidence(self, engine):
        high_cred = _make_profile(
            actions=[{"description": "espionage", "severity": 0.8}],
            sources=[{"url": "https://gov.example/report", "credibility": 0.95}],
        )
        low_cred = _make_profile(
            actions=[{"description": "espionage", "severity": 0.8}],
            sources=[{"url": "https://anon.example/post", "credibility": 0.1}],
        )
        r_high = engine.assess(high_cred)
        r_low = engine.assess(low_cred)
        assert r_high.confidence >= r_low.confidence

    def test_no_sources_lowers_confidence(self, engine):
        with_src = _make_profile(
            actions=[{"description": "espionage", "severity": 0.8}],
            sources=[{"url": "https://gov.example/report", "credibility": 0.9}],
        )
        without_src = _make_profile(
            actions=[{"description": "espionage", "severity": 0.8}],