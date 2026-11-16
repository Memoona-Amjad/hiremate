from app.tools import find_unsupported_skills, keyword_coverage


def test_keyword_coverage_counts_matches():
    result = keyword_coverage("I use Python and SQL daily with pandas.", ["Python", "SQL", "Docker"])
    assert result["found"] == ["Python", "SQL"]
    assert result["missing"] == ["Docker"]
    assert result["percent"] == 67


def test_keyword_coverage_multiword_and_symbols():
    text = "Ran A/B tests and built machine learning models in C#."
    result = keyword_coverage(text, ["A/B testing", "machine learning", "C#"])
    assert "machine learning" in result["found"]
    assert "C#" in result["found"]


def test_unsupported_skills_flags_invented_ones():
    cv = "Skills: Python, SQL, Power BI"
    flagged = find_unsupported_skills(["Python", "Docker", "Power BI", "AWS"], cv, confirmed=["AWS"])
    assert flagged == ["Docker"]
