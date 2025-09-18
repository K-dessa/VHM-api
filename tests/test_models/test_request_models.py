from app.models.request_models import CompanyAnalysisRequest, SearchDepth, DateRange


def test_company_name_allows_ampersand():
    req = CompanyAnalysisRequest(
        company_name="B & C International B.V.",
        kvk_nummer="08064339",
        contactpersoon="",
        search_depth=SearchDepth.STANDARD,
        news_date_range=DateRange.LAST_YEAR,
        legal_date_range=DateRange.LAST_3_YEARS
    )
    assert req.company_name == "B & C International B.V."
