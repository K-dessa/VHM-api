import pytest

from app.models.response_models import CompanyInfo
from app.services.risk_service import RiskLevel, RiskService


def test_assess_financial_risk_handles_none_employee_count():
    service = RiskService()
    company_info = CompanyInfo(name="Test BV", employee_count=None)

    result = service.assess_financial_risk(company_info, news=None)

    assert result.level == RiskLevel.VERY_LOW
    assert "Employee count not provided" in result.factors
