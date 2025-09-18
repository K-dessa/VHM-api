"""
Risk assessment service for integrated company analysis.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from app.models.response_models import CompanyInfo, NewsAnalysis


class RiskLevel(str, Enum):
    """Risk level enumeration."""

    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class RiskCategory(str, Enum):
    """Risk category enumeration."""

    REPUTATION = "reputation"
    FINANCIAL = "financial"
    OPERATIONAL = "operational"


@dataclass
class RiskScore:
    """Individual risk score with details."""

    category: RiskCategory
    level: RiskLevel
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    factors: List[str]
    recommendations: List[str]


@dataclass
class RiskAssessment:
    """Complete risk assessment result."""

    overall_score: float  # 0.0 to 1.0
    overall_level: RiskLevel
    risk_scores: List[RiskScore]
    key_concerns: List[str]
    recommendations: List[str]
    monitoring_suggestions: List[str]
    assessment_timestamp: datetime


class RiskService:
    """Service for calculating integrated risk assessments."""

    # Weight factors for different risk categories
    WEIGHTS = {
        RiskCategory.REPUTATION: 0.50,
        RiskCategory.FINANCIAL: 0.30,
        RiskCategory.OPERATIONAL: 0.20,
    }

    def __init__(self):
        self.current_date = datetime.now()

    def calculate_overall_risk(
        self,
        company_info: Optional[CompanyInfo],
        legal_findings: Optional[None],
        news_analysis: Optional[NewsAnalysis],
    ) -> RiskAssessment:
        """Calculate comprehensive risk assessment."""

        risk_scores = []

        # Calculate individual risk categories

        reputation_risk = self.assess_reputation_risk(news_analysis)
        risk_scores.append(reputation_risk)

        financial_risk = self.assess_financial_risk(company_info, news_analysis)
        risk_scores.append(financial_risk)

        operational_risk = self.assess_operational_risk(
            {
                "company_info": company_info,
                "news_analysis": news_analysis,
            }
        )
        risk_scores.append(operational_risk)

        # Calculate weighted overall score
        overall_score = sum(
            score.score * self.WEIGHTS[score.category] for score in risk_scores
        )

        overall_level = self._score_to_level(overall_score)

        # Aggregate recommendations and concerns
        key_concerns = []
        recommendations = []
        monitoring_suggestions = []

        for risk_score in risk_scores:
            if risk_score.level in [RiskLevel.HIGH, RiskLevel.VERY_HIGH]:
                key_concerns.extend(risk_score.factors[:2])  # Top 2 factors
            recommendations.extend(
                risk_score.recommendations[:3]
            )  # Top 3 recommendations

        # Add general monitoring suggestions
        monitoring_suggestions = self._generate_monitoring_suggestions(risk_scores)

        return RiskAssessment(
            overall_score=overall_score,
            overall_level=overall_level,
            risk_scores=risk_scores,
            key_concerns=key_concerns[:5],  # Top 5 concerns
            recommendations=recommendations[:10],  # Top 10 recommendations
            monitoring_suggestions=monitoring_suggestions,
            assessment_timestamp=self.current_date,
        )


    def assess_reputation_risk(
        self, news_analysis: Optional[NewsAnalysis]
    ) -> RiskScore:
        """Assess reputation risk based on news analysis."""
        if not news_analysis:
            return RiskScore(
                category=RiskCategory.REPUTATION,
                level=RiskLevel.LOW,
                score=0.2,
                confidence=0.5,
                factors=["Limited news data available"],
                recommendations=[
                    "Monitor news mentions regularly",
                    "Establish media monitoring",
                ],
            )

        factors = []
        score = 0.0

        # Sentiment analysis
        if news_analysis.sentiment_summary:
            negative_ratio = news_analysis.sentiment_summary.get("negative", 0) / 100
            positive_ratio = news_analysis.sentiment_summary.get("positive", 0) / 100

            # Higher negative sentiment increases risk
            score += negative_ratio * 0.7

            # Lower positive sentiment also increases risk
            if positive_ratio < 0.3:
                score += 0.2

            if negative_ratio > 0.4:
                factors.append(f"High negative sentiment: {negative_ratio*100:.0f}%")
            if positive_ratio < 0.2:
                factors.append(f"Low positive sentiment: {positive_ratio*100:.0f}%")

        # Key topics analysis
        if news_analysis.key_topics:
            risk_topics = [
                "bankruptcy",
                "fraud",
                "scandal",
                "investigation",
                "lawsuit",
                "complaint",
                "criticism",
                "controversy",
            ]

            for topic in news_analysis.key_topics[:10]:
                if any(risk_word in topic.lower() for risk_word in risk_topics):
                    score += 0.1
                    factors.append(f"Risk topic mentioned: {topic}")

        # Article volume and recency
        total_articles = len(news_analysis.articles) if news_analysis.articles else 0
        if total_articles > 50:
            factors.append(f"High media attention: {total_articles} articles")
            score += 0.1
        elif total_articles < 5:
            factors.append("Limited media coverage")
            score += 0.15  # Unknown can be risky too

        score = min(score, 1.0)

        recommendations = self._generate_reputation_recommendations(
            news_analysis.sentiment_summary, factors
        )

        return RiskScore(
            category=RiskCategory.REPUTATION,
            level=self._score_to_level(score),
            score=score,
            confidence=0.7,
            factors=factors[:5],
            recommendations=recommendations,
        )

    def assess_financial_risk(
        self, company_info: Optional[CompanyInfo], news: Optional[NewsAnalysis]
    ) -> RiskScore:
        """Assess financial risk based on company data and news."""
        factors = []
        score = 0.0

        if not company_info:
            return RiskScore(
                category=RiskCategory.FINANCIAL,
                level=RiskLevel.MEDIUM,
                score=0.5,
                confidence=0.3,
                factors=["Limited financial data available"],
                recommendations=[
                    "Obtain detailed financial information",
                    "Request recent financial statements",
                ],
            )

        # Company status analysis
        if hasattr(company_info, "status"):
            if "inactive" in str(company_info.status).lower():
                score += 0.8
                factors.append("Company status: inactive")
            elif "suspended" in str(company_info.status).lower():
                score += 0.6
                factors.append("Company status: suspended")

        # Employee count analysis
        if hasattr(company_info, "employee_count"):
            employee_count = company_info.employee_count
            if employee_count is None:
                factors.append("Employee count not provided")
            else:
                if employee_count == 0:
                    score += 0.3
                    factors.append("No employees registered")
                elif 0 < employee_count < 5:
                    score += 0.1
                    factors.append(f"Small team: {employee_count} employees")

        # News-based financial indicators
        if news and news.articles:
            financial_risk_keywords = [
                "financial trouble",
                "bankruptcy",
                "debt",
                "losses",
                "restructuring",
                "layoffs",
                "budget cuts",
            ]

            for article in news.articles[:20]:  # Check recent articles
                # News articles may be dictionaries or pydantic models.
                # Support both structures when extracting text for keyword checks.
                title = (
                    article.get("title", "")
                    if isinstance(article, dict)
                    else getattr(article, "title", "")
                )
                summary = (
                    article.get("summary", "")
                    if isinstance(article, dict)
                    else getattr(article, "summary", "")
                )
                article_text = (title + " " + summary).lower()

                for keyword in financial_risk_keywords:
                    if keyword in article_text:
                        score += 0.15
                        factors.append(f"Financial concern mentioned: {keyword}")
                        break  # One per article

        score = min(score, 1.0)

        recommendations = self._generate_financial_recommendations(factors)

        return RiskScore(
            category=RiskCategory.FINANCIAL,
            level=self._score_to_level(score),
            score=score,
            confidence=0.6,
            factors=factors[:5],
            recommendations=recommendations,
        )

    def assess_operational_risk(self, all_data: Dict[str, Any]) -> RiskScore:
        """Assess operational risk based on all available data."""
        factors = []
        score = 0.0

        company_info = all_data.get("company_info")
        legal_findings = all_data.get("legal_findings")
        news_analysis = all_data.get("news_analysis")

        # Data completeness risk
        missing_data = 0
        if not company_info:
            missing_data += 1
        if not news_analysis:
            missing_data += 0.5

        if missing_data > 0:
            score += missing_data * 0.2
            factors.append(
                f"Incomplete data available ({missing_data:.1f} sources missing)"
            )


        # Industry-specific operational risks
        if company_info and hasattr(company_info, "industry"):
            high_risk_industries = [
                "construction",
                "financial",
                "healthcare",
                "transport",
            ]
            if any(
                industry in str(company_info.industry).lower()
                for industry in high_risk_industries
            ):
                score += 0.1
                factors.append("Operating in high-risk industry")

        # Recent operational changes (from news)
        if news_analysis and news_analysis.key_topics:
            operational_topics = [
                "merger",
                "acquisition",
                "restructuring",
                "management change",
                "relocation",
                "expansion",
            ]

            for topic in news_analysis.key_topics[:10]:
                if any(op_topic in topic.lower() for op_topic in operational_topics):
                    score += 0.05
                    factors.append(f"Recent operational change: {topic}")

        score = min(score, 1.0)

        recommendations = self._generate_operational_recommendations(factors)

        return RiskScore(
            category=RiskCategory.OPERATIONAL,
            level=self._score_to_level(score),
            score=score,
            confidence=0.5,
            factors=factors[:5],
            recommendations=recommendations,
        )

    def _score_to_level(self, score: float) -> RiskLevel:
        """Convert numerical score to risk level."""
        if score >= 0.8:
            return RiskLevel.VERY_HIGH
        elif score >= 0.6:
            return RiskLevel.HIGH
        elif score >= 0.4:
            return RiskLevel.MEDIUM
        elif score >= 0.2:
            return RiskLevel.LOW
        else:
            return RiskLevel.VERY_LOW

    def _get_recency_weight(self, months_ago: float) -> float:
        """Calculate weight based on data recency."""
        if months_ago <= 6:
            return 1.0
        elif months_ago <= 12:
            return 0.8
        else:
            return 0.6

    def _parse_case_date(self, date_str: str) -> Optional[datetime]:
        """Parse case date string to datetime."""
        try:
            # Try different date formats
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        except:
            pass
        return None


    def _generate_reputation_recommendations(
        self, sentiment_summary: Optional[Dict], factors: List[str]
    ) -> List[str]:
        """Generate reputation risk recommendations."""
        recommendations = []

        if sentiment_summary:
            negative_ratio = sentiment_summary.get("negative", 0) / 100
            if negative_ratio > 0.3:
                recommendations.append(
                    "Implement proactive reputation management strategy"
                )
                recommendations.append("Monitor and respond to negative media coverage")

        if any("media attention" in factor for factor in factors):
            recommendations.append("Establish media relations protocol")
            recommendations.append("Prepare crisis communication plan")

        if any("sentiment" in factor for factor in factors):
            recommendations.append("Conduct stakeholder sentiment analysis")
            recommendations.append("Develop positive content strategy")

        recommendations.append("Set up automated media monitoring alerts")

        return recommendations[:5]

    def _generate_financial_recommendations(self, factors: List[str]) -> List[str]:
        """Generate financial risk recommendations."""
        recommendations = []

        if any("inactive" in factor for factor in factors):
            recommendations.append("Verify current business operations status")
            recommendations.append("Obtain recent financial statements")

        if any("employees" in factor for factor in factors):
            recommendations.append("Assess operational capacity and scalability")
            recommendations.append("Verify business continuity plans")

        if any("financial" in factor.lower() for factor in factors):
            recommendations.append("Request detailed financial disclosure")
            recommendations.append("Consider requiring financial guarantees")

        recommendations.append("Monitor financial stability indicators")
        recommendations.append("Set up payment terms protection")

        return recommendations[:5]

    def _generate_operational_recommendations(self, factors: List[str]) -> List[str]:
        """Generate operational risk recommendations."""
        recommendations = []

        if any("data" in factor for factor in factors):
            recommendations.append("Request additional operational documentation")
            recommendations.append("Conduct on-site operational assessment")

        if any("industry" in factor for factor in factors):
            recommendations.append("Apply industry-specific due diligence standards")
            recommendations.append("Monitor industry-specific risk indicators")

        if any("change" in factor for factor in factors):
            recommendations.append("Assess impact of recent operational changes")
            recommendations.append("Monitor transition period stability")

        recommendations.append("Establish operational performance monitoring")
        recommendations.append("Review business continuity procedures")

        return recommendations[:5]

    def _generate_monitoring_suggestions(
        self, risk_scores: List[RiskScore]
    ) -> List[str]:
        """Generate general monitoring suggestions based on risk assessment."""
        suggestions = []

        # High-level monitoring based on overall risk
        high_risk_categories = [
            score.category
            for score in risk_scores
            if score.level in [RiskLevel.HIGH, RiskLevel.VERY_HIGH]
        ]


        if RiskCategory.REPUTATION in high_risk_categories:
            suggestions.append("Daily media mention monitoring")
            suggestions.append("Monthly sentiment analysis review")

        if RiskCategory.FINANCIAL in high_risk_categories:
            suggestions.append("Monthly financial stability check")
            suggestions.append("Quarterly credit rating monitoring")

        if RiskCategory.OPERATIONAL in high_risk_categories:
            suggestions.append("Bi-weekly operational status review")
            suggestions.append("Monthly industry benchmark comparison")

        # General suggestions
        suggestions.extend(
            [
                "Set up automated risk alert thresholds",
                "Schedule quarterly comprehensive risk review",
                "Maintain updated emergency contact procedures",
            ]
        )

        return suggestions[:8]
