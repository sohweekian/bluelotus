from acms_cop.reports.remediation_reconciliation import build_security_master_exceptions
from acms_cop.reports.cio_order_policy import apply_policy_security_overrides


def test_unknown_sector_or_industry_is_reported_not_auto_approved():
    rows = build_security_master_exceptions({
        "security_master": {
            "ABC": {"sector": "UNKNOWN", "industry": "Software", "classification_source": "moomoo"},
            "XYZ": {"sector": "Technology", "industry": ""},
        }
    })
    assert len(rows) == 2
    assert rows[0]["classification_status"] == "CLASSIFICATION_GAP"
    assert rows[0]["requires_manual_approval"] is True
    assert rows[0]["proposed_sector"] == "MANUAL_RESEARCH_REQUIRED"


def test_gold_support_policy_overrides_aem_and_b_classification_gap():
    dataset = {
        "security_master": {
            "AEM": {"sector": None, "industry": None},
            "B": {"sector": "UNKNOWN", "industry": "UNKNOWN"},
        }
    }
    apply_policy_security_overrides(dataset)
    rows = build_security_master_exceptions(dataset)
    assert rows == []
    assert dataset["security_master"]["AEM"]["sector"] == "Basic Materials"
    assert dataset["security_master"]["AEM"]["industry"] == "Gold"
    assert dataset["security_master"]["B"]["sector"] == "Basic Materials"
    assert dataset["security_master"]["B"]["industry"] == "Gold"


def test_security_master_metadata_is_not_reported_as_exception():
    rows = build_security_master_exceptions({
        "security_master": {
            "_meta": {"ticker_count": 3, "unknown_sector_count": 0},
            "VXX": {"sector": "Multi-Asset", "industry": "Exchange Traded Fund"},
        }
    })
    assert rows == []
