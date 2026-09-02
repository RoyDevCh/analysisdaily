from datetime import date

import pytest
from pydantic import ValidationError

from analysisdaily.models.report import (
    BiasLabel,
    FactStatement,
    QuoteSpan,
    SourceRef,
    StructuredReport,
)


def _good_report() -> StructuredReport:
    return StructuredReport(
        event_id="20260902-tech-antitrust-01",
        date=date(2026, 9, 2),
        category="经济与科技",
        headline="EU fines TechCo 1.8 billion euros for abusing dominant position",
        verified_facts=[
            FactStatement(
                text="The European Commission fined TechCo 1.8 billion euros on Tuesday.",
                quote_spans=[
                    QuoteSpan(source_name="Reuters", url="https://x", quote="The Commission fined TechCo 1.8 billion euros on Tuesday.")
                ],
            )
        ],
        sources=[SourceRef(name="Reuters", url="https://x", bias=BiasLabel.CENTER)],
    )


def test_valid_report_passes():
    r = _good_report()
    assert r.event_id == "20260902-tech-antitrust-01"
    assert r.to_render_dict()["headline"]


def test_headline_forbids_exclamation():
    d = _good_report().model_dump()
    d["headline"] = "TechCo fined!!"
    with pytest.raises(ValidationError):
        StructuredReport(**d)


def test_headline_forbids_emotive_word():
    d = _good_report().model_dump()
    d["headline"] = "This is a shocking scandal"
    with pytest.raises(ValidationError):
        StructuredReport(**d)


def test_empty_verified_facts_rejected():
    d = _good_report().model_dump()
    d["verified_facts"] = []
    with pytest.raises(ValidationError):
        StructuredReport(**d)


def test_fact_without_quote_span_rejected():
    with pytest.raises(ValidationError):
        StructuredReport(
            event_id="20260902-abc-01",
            date=date(2026, 9, 2),
            headline="A neutral headline about a confirmed fact.",
            verified_facts=[FactStatement(text="A neutral fact about a confirmed thing.")],
            sources=[SourceRef(name="Reuters", url="https://x")],
        )


def test_source_weight_ordering():
    assert BiasLabel.CENTER.fact_weight > BiasLabel.LEFT.fact_weight
    assert BiasLabel.CENTER_LEFT.side == "left_leaning"
    assert BiasLabel.CENTER_RIGHT.side == "right_leaning"
