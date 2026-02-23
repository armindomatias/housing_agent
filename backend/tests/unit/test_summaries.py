"""
Unit tests for template-based summary generation in agents/summaries.py.
"""
import pytest
from app.agents.summaries import (
    _fmt_euros,
    _fmt_euros_short,
    _fmt_range,
    _fmt_range_short,
    _condition_label,
    _get_priority_rooms,
    generate_analysis_chat_summary,
    generate_portfolio_index_line,
    generate_profile_section_summary,
    generate_master_profile_summary,
)


class TestFormatHelpers:
    def test_fmt_euros_thousands(self):
        assert _fmt_euros(180000) == "180.000€"

    def test_fmt_euros_small(self):
        assert _fmt_euros(500) == "500€"

    def test_fmt_euros_short_k(self):
        assert _fmt_euros_short(180000) == "180k€"

    def test_fmt_euros_short_millions(self):
        result = _fmt_euros_short(1_200_000)
        assert "M€" in result

    def test_fmt_range_both(self):
        result = _fmt_range(15000, 25000)
        assert "15.000€" in result
        assert "25.000€" in result

    def test_fmt_range_min_only(self):
        result = _fmt_range(10000, None)
        assert "10.000€" in result
        assert "partir de" in result

    def test_fmt_range_neither(self):
        result = _fmt_range(None, None)
        assert "não calculado" in result

    def test_fmt_range_short(self):
        result = _fmt_range_short(15000, 25000)
        assert "15-25k€" == result

    def test_condition_label_known(self):
        assert _condition_label("poor") == "Mau"
        assert _condition_label("excellent") == "Excelente"
        assert _condition_label("fair") == "Razoável"
        assert _condition_label("good") == "Bom"
        assert _condition_label("needs_full_renovation") == "Remodelação total"


class TestAnalysisChatSummary:
    def test_generates_with_full_data(self):
        result_data = {
            "price": 185000,
            "area_m2": 75,
            "price_per_m2": 2466,
            "overall_condition": "fair",
            "confidence_score": 0.72,
            "total_min": 15000,
            "total_max": 25000,
            "room_estimates": [
                {"room_label": "Cozinha", "room_type": "cozinha", "condition": "poor", "cost_min": 5000, "cost_max": 8000},
                {"room_label": "WC", "room_type": "casa_de_banho", "condition": "fair", "cost_min": 3000, "cost_max": 5000},
            ],
        }
        summary = generate_analysis_chat_summary(result_data)
        assert "185.000€" in summary
        assert "75m²" in summary
        assert "15.000€" in summary
        assert "Cozinha" in summary

    def test_generates_with_minimal_data(self):
        result = generate_analysis_chat_summary({})
        assert result == "Análise concluída"

    def test_confidence_displayed_as_percentage(self):
        result_data = {"confidence_score": 0.72, "total_min": 10000, "total_max": 20000}
        summary = generate_analysis_chat_summary(result_data)
        assert "72%" in summary

    def test_priority_rooms_limited(self):
        # Only top 3 rooms shown (out of 5 supplied)
        rooms = [
            {"room_label": f"Q{i}", "condition": "poor", "cost_min": 1000*i, "cost_max": 2000*i}
            for i in range(1, 6)
        ]
        result_data = {"room_estimates": rooms}
        summary = generate_analysis_chat_summary(result_data)
        priority_lines = [l for l in summary.splitlines() if "Prioridades" in l]
        if priority_lines:
            line = priority_lines[0]
            # Count how many room labels (Q1–Q5) appear in the line
            rooms_shown = sum(f"Q{i}" in line for i in range(1, 6))
            assert rooms_shown <= 3


class TestPortfolioIndexLine:
    def test_full_data(self):
        prop = {"num_rooms": 2, "location": "Lisboa, Alfama", "price": 180000}
        analysis = {"total_min": 15000, "total_max": 25000}
        result = generate_portfolio_index_line(prop, analysis)
        assert "T2" in result
        # The implementation uses the first segment of the location string
        assert "Lisboa" in result
        assert "180k€" in result
        assert "reno" in result

    def test_no_analysis(self):
        prop = {"num_rooms": 3, "location": "Porto", "price": 220000}
        result = generate_portfolio_index_line(prop)
        assert "T3" in result
        assert "Porto" in result
        assert "220k€" in result

    def test_empty_data(self):
        result = generate_portfolio_index_line({})
        assert result == "Imóvel sem dados"


class TestProfileSectionSummary:
    def test_fiscal_with_data(self):
        data = {"tax_regime": "IRS", "first_time_buyer": True}
        result = generate_profile_section_summary("fiscal", data)
        assert "IRS" in result
        assert "1ª habitação" in result

    def test_budget_with_range(self):
        data = {"budget_min": 150000, "budget_max": 250000}
        result = generate_profile_section_summary("budget", data)
        assert "Orçamento" in result

    def test_renovation_with_diy(self):
        data = {"finish_level": "médio", "diy_skills": ["painting", "flooring_tile"]}
        result = generate_profile_section_summary("renovation", data)
        assert "médio" in result
        assert "2 skill(s)" in result

    def test_empty_data(self):
        result = generate_profile_section_summary("fiscal", {})
        assert result == "Não preenchido"


class TestMasterProfileSummary:
    def test_with_full_profile(self):
        profile = {
            "display_name": "João Silva",
            "region": "Lisboa",
            "sections_completed": ["fiscal", "budget", "renovation"],
        }
        result = generate_master_profile_summary(profile)
        assert "João Silva" in result
        assert "Lisboa" in result
        assert "3/5" in result

    def test_with_empty_profile(self):
        result = generate_master_profile_summary({})
        assert "Utilizador" in result
