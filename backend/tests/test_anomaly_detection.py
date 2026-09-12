"""
Tests — Anomaly Detection Service
"""

import pytest
import services.anomaly_service as ano


def test_detect_anomalies_returns_dict(db):
    result = ano.detect_anomalies(db)
    assert isinstance(result, dict)


def test_detect_anomalies_required_keys(db):
    result = ano.detect_anomalies(db)
    required = {"total_anomalies", "severity_summary", "anomalies", "disclaimer"}
    assert required.issubset(result.keys())


def test_detect_anomalies_nonzero(db):
    result = ano.detect_anomalies(db)
    assert result["total_anomalies"] > 0, "Should detect at least one anomaly"


def test_anomaly_items_have_required_fields(db):
    result = ano.detect_anomalies(db)
    required_fields = {"type", "entity", "severity", "actual_value", "expected_value",
                       "deviation_pct", "explanation"}
    for a in result["anomalies"]:
        assert required_fields.issubset(a.keys()), f"Missing field in anomaly: {a}"


def test_severity_values_are_valid(db):
    result = ano.detect_anomalies(db)
    valid = {"low", "medium", "high", "critical"}
    for a in result["anomalies"]:
        assert a["severity"] in valid, f"Invalid severity: {a['severity']}"


def test_duplicate_invoice_detected(db):
    """A2: INV-MKT-0312 appears twice — must be flagged."""
    result = ano.detect_anomalies(db)
    dup_anomalies = [
        a for a in result["anomalies"]
        if a["type"] == "duplicate_invoice"
    ]
    assert len(dup_anomalies) > 0, "Duplicate invoice anomaly not detected"
    numbers = [a.get("invoice_number", "") for a in dup_anomalies]
    assert any("0312" in n for n in numbers), "INV-MKT-0312 duplicate not found"


def test_large_payment_detected(db):
    """A1: CloudEdge $47,500 vs avg ~$8,000 — must be flagged."""
    result = ano.detect_anomalies(db)
    large = [a for a in result["anomalies"] if a["type"] == "large_vendor_payment"]
    assert len(large) > 0, "Large vendor payment anomaly not detected"
    # At least one should have actual_value > 40_000
    high_value = [a for a in large if a["actual_value"] > 40_000]
    assert len(high_value) > 0, "CloudEdge $47,500 payment not flagged"


def test_category_spending_anomaly_detected(db):
    """A3: Marketing spike in Jun 2026 — must be flagged."""
    result = ano.detect_anomalies(db)
    cat_anomalies = [
        a for a in result["anomalies"]
        if a["type"] == "category_spending_anomaly"
    ]
    assert len(cat_anomalies) > 0, "No category spending anomaly detected"


def test_vendor_frequency_anomaly_detected(db):
    """A4: DataStream has 5 invoices in Jul 2026 — must be flagged."""
    result = ano.detect_anomalies(db)
    freq = [a for a in result["anomalies"] if a["type"] == "vendor_invoice_frequency_anomaly"]
    assert len(freq) > 0, "Vendor frequency anomaly not detected"


def test_unusual_transaction_amount_detected(db):
    """A5: HR payroll 3× spike — must flag an unusual transaction."""
    result = ano.detect_anomalies(db)
    unusual = [a for a in result["anomalies"] if a["type"] == "unusual_transaction_amount"]
    assert len(unusual) > 0, "Unusual transaction amount not detected"


def test_disclaimer_language(db):
    """Disclaimer must not call anything fraud."""
    result = ano.detect_anomalies(db)
    disclaimer = result.get("disclaimer", "").lower()
    assert "fraud" not in disclaimer, "Disclaimer should not use the word 'fraud'"


def test_explanations_not_empty(db):
    result = ano.detect_anomalies(db)
    for a in result["anomalies"]:
        assert len(a["explanation"]) > 20, f"Explanation too short: {a['explanation']}"


def test_severity_summary_counts_match(db):
    result = ano.detect_anomalies(db)
    summary = result["severity_summary"]
    count_from_list = {}
    for a in result["anomalies"]:
        s = a["severity"]
        count_from_list[s] = count_from_list.get(s, 0) + 1
    for sev, cnt in count_from_list.items():
        assert summary.get(sev, 0) == cnt, f"Severity count mismatch for {sev}"
