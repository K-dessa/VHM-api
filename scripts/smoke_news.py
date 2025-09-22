import os
import sys
import json
import httpx


def main():
    base_url = os.environ.get("BASE_URL", "http://localhost:8000")
    api_key = os.environ.get("API_KEY", "test-api-key-12345678901234567890")
    url = f"{base_url}/analyze-company"
    payload = {"company_name": "Tomassen Duck-To B.V.", "search_depth": "standard"}

    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, headers=headers, json=payload)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
        data = r.json()

    # Check news_analysis shape: may be None, but if timeboxed used, meta/evidence present
    meta = data.get("meta")
    news = data.get("news_analysis")
    assert meta is None or meta.get("data_completeness") in ("complete", "partial_timeout"), "Invalid data_completeness"

    # When partial, ensure risk not default low if any negative present
    if meta and meta.get("data_completeness") == "partial_timeout":
        negatives = int(meta.get("negatives", 0))
        risk_level = (data.get("risk_assessment") or {}).get("overall_risk_level")
        if negatives >= 1:
            assert risk_level != "low", "Risk should not be 'low' when partial with negatives"

    # Ensure news_analysis is array or object; we tolerate None but prefer array when partials exist
    if news is not None:
        # legacy NewsAnalysis object
        assert isinstance(news, dict), "news_analysis should be an object when present"

    print("Smoke OK")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"Assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(2)

