from analysisdaily.facts.subjectivity import is_emotive, is_factual, strip_emotive


def test_is_factual_true_with_anchor():
    assert is_factual("The Commission fined TechCo 1.8 billion euros on Tuesday.")


def test_is_emotive_detect():
    assert is_emotive("This is a shocking outrage.")


def test_is_factual_rejects_emotive():
    assert not is_factual("This is a shocking outrage for everyone.")


def test_strip_emotive_removes_emotive_sentences():
    text = "The Commission fined TechCo 1.8 billion euros on Tuesday. This is a shocking outrage. The decision followed a four-year investigation."
    cleaned = strip_emotive(text)
    assert "shocking" not in cleaned
    assert "1.8 billion" in cleaned
from analysisdaily.facts.subjectivity import is_clean_fact


def test_is_clean_fact_rejects_exclamation_and_emotive():
    assert not is_clean_fact("We need to know her name ASAP!")
    assert not is_clean_fact("This is a shocking disaster!")
    assert is_clean_fact("The commission fined TechCo 1.8 billion euros.")
