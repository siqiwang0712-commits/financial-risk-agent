from __future__ import annotations

import io
import zipfile

from finrisk.extraction_reference import (
    construct_pre_num_reference,
    load_pre_num_reference_rows,
)
from finrisk.sec_bulk import (
    build_annual_outcome_corpus,
    build_deterioration_labels,
    build_numeric_corpus,
    build_reported_fcf_periods,
    enrich_metrics,
    load_statement_archives,
    readiness_report,
)


def _archive(
    path, year: int, revenue: int, income: int, ocf: int, debt: int, *, include_short_term_debt: bool = True
) -> None:
    adsh = f"0000320193-{str(year + 1)[-2:]}-000001"
    period = f"{year}0930"
    filed = f"{year + 1}1025"
    sub = "adsh\tcik\tname\tform\tperiod\tfy\tfp\tfiled\taccepted\n"
    sub += f"{adsh}\t320193\tAPPLE INC\t10-K\t{period}\t{year}\tFY\t{filed}\t{filed}120000\n"
    values = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": (revenue, 4),
        "NetIncomeLoss": (income, 4), "NetCashProvidedByUsedInOperatingActivities": (ocf, 4),
        "Assets": (1000, 0), "Liabilities": (600, 0), "AssetsCurrent": (300, 0),
        "LiabilitiesCurrent": (250, 0), "CashAndCashEquivalentsAtCarryingValue": (100, 0),
        "StockholdersEquity": (400, 0), "LongTermDebtNoncurrent": (debt, 0),
    }
    if include_short_term_debt:
        values["LongTermDebtCurrent"] = (0, 0)
    num = "adsh\ttag\tversion\tcoreg\tddate\tqtrs\tuom\tvalue\tfootnote\n"
    pre = "adsh\treport\tline\tstmt\tinpth\trfile\ttag\tversion\tplabel\tnegating\n"
    for tag, (value, qtrs) in values.items():
        num += f"{adsh}\t{tag}\tus-gaap/2023\t\t{period}\t{qtrs}\tUSD\t{value}\t\n"
        stmt = "CF" if tag == "NetCashProvidedByUsedInOperatingActivities" else "IS" if qtrs == 4 else "BS"
        pre += f"{adsh}\t1\t1\t{stmt}\t0\tH\t{tag}\tus-gaap/2023\t{tag}\t0\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("sub.txt", sub)
        archive.writestr("num.txt", num)
        archive.writestr("pre.txt", pre)
    path.write_bytes(buffer.getvalue())


def test_bulk_import_metrics_labels_and_readiness(tmp_path):
    first, second = tmp_path / "2022q4.zip", tmp_path / "2023q4.zip"
    _archive(first, 2021, 1000, 100, 200, 200)
    _archive(second, 2022, 800, -10, 100, 350)
    submissions, numbers, sources = load_statement_archives([first, second])
    plan = [
        {"observation_id": "aapl-2021", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2021", "split": "train"},
        {"observation_id": "aapl-2022", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2022", "split": "train"},
    ]
    observations, report = build_numeric_corpus(plan, submissions, numbers, sources)
    enrich_metrics(observations)
    labels = build_deterioration_labels(observations)
    assert report["imported"] == 2
    assert observations[0]["split"] == "train"
    assert observations[0]["source_available_time"] >= observations[0]["filed_at"]
    assert observations[0]["source_hash"] == sources[0]["sha256"]
    assert observations[0]["raw_source_hashes"] == [sources[0]["sha256"]]
    assert observations[0]["observation_hash"] != observations[0]["source_hash"]
    assert observations[0]["facts"]["revenue"] == 1000
    assert observations[0]["metrics"]["current_ratio"] == 1.2
    assert labels[0]["financial_deterioration_12m"] == 1
    assert {reason["code"] for reason in labels[0]["reason"]} >= {"REVENUE_DECLINE_10PCT", "POSITIVE_INCOME_TO_LOSS"}
    ready = readiness_report(observations, labels)
    assert ready["NUMERIC_READY"] == "VERIFIED"
    assert ready["LABEL_READY"] == "VERIFIED"
    assert ready["DOCUMENT_READY"] == "INSUFFICIENT_DATA"


def test_bulk_import_does_not_coerce_missing_debt_component_to_zero(tmp_path):
    archive = tmp_path / "2022q4.zip"
    _archive(archive, 2021, 1000, 100, 200, 200, include_short_term_debt=False)
    submissions, numbers, sources = load_statement_archives([archive])
    plan = [{"observation_id": "aapl-2021", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2021", "split": "train"}]
    observations, _ = build_numeric_corpus(plan, submissions, numbers, sources)
    assert observations[0]["facts"]["total_debt"] is None
    assert observations[0]["fact_provenance"]["total_debt"] is None


def test_negative_ocf_does_not_count_as_turning_negative_twice(tmp_path):
    first, second = tmp_path / "2022q4.zip", tmp_path / "2023q4.zip"
    _archive(first, 2021, 1000, -10, -100, 200)
    _archive(second, 2022, 1000, -10, -90, 200)
    submissions, numbers, sources = load_statement_archives([first, second])
    plan = [
        {"observation_id": "aapl-2021", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2021", "split": "train"},
        {"observation_id": "aapl-2022", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2022", "split": "train"},
    ]
    observations, _ = build_numeric_corpus(plan, submissions, numbers, sources)
    labels = build_deterioration_labels(observations)
    first_label = next(row for row in labels if row["observation_id"] == "aapl-2021")
    assert first_label["financial_deterioration_12m"] == 0
    assert first_label["reason"] == []


def test_two_subsequent_reported_fcf_periods_resolve_one_signal_label(tmp_path):
    first, second = tmp_path / "2022q4.zip", tmp_path / "2023q4.zip"
    _archive(first, 2021, 1000, 100, 200, 200)
    _archive(second, 2022, 1000, 100, 140, 200)
    submissions, numbers, sources = load_statement_archives([first, second])
    plan = [
        {"observation_id": "aapl-2021", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2021", "split": "train"},
        {"observation_id": "aapl-2022", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2022", "split": "train"},
    ]
    observations, _ = build_numeric_corpus(plan, submissions, numbers, sources)
    current = observations[0]
    reported = [
        {"ticker": "AAPL", "accession": "q1", "source_available_time": "2023-01-20T00:00:00Z", "free_cash_flow": 10},
        {"ticker": "AAPL", "accession": "q2", "source_available_time": "2023-04-20T00:00:00Z", "free_cash_flow": 5},
    ]
    current["outcome_window_end"] = "2023-10-25T23:59:59Z"
    label = next(row for row in build_deterioration_labels(observations, reported) if row["observation_id"] == "aapl-2021")
    assert label["fcf_two_subsequent_periods"] == "VERIFIED_FALSE"
    assert label["financial_deterioration_12m"] == 0


def test_label_outcomes_are_independent_from_frozen_feature_plan(tmp_path):
    first, second = tmp_path / "2023q4.zip", tmp_path / "2024q4.zip"
    _archive(first, 2022, 1000, 100, 200, 200)
    _archive(second, 2023, 800, -10, 100, 350)
    submissions, numbers, sources = load_statement_archives([first, second])
    plan = [{"observation_id": "aapl-2022", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2022", "split": "test"}]
    observations, _ = build_numeric_corpus(plan, submissions, numbers, sources)
    outcomes = build_annual_outcome_corpus(submissions, numbers, sources)
    labels = build_deterioration_labels(observations, annual_outcomes=outcomes, outcome_data_available_through="2024-12-31T23:59:59Z")
    assert len(observations) == 1
    assert len(outcomes) == 2
    assert labels[0]["label_status"] == "VERIFIED"
    assert labels[0]["financial_deterioration_12m"] == 1


def test_right_censoring_and_true_no_eligible_outcome_are_distinct(tmp_path):
    first, late = tmp_path / "2023q4.zip", tmp_path / "2024q4.zip"
    _archive(first, 2022, 1000, 100, 200, 200)
    _archive(late, 2023, 1000, 100, 200, 200)
    submissions, numbers, sources = load_statement_archives([first, late])
    plan = [{"observation_id": "aapl-2022", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2022", "split": "test"}]
    observations, _ = build_numeric_corpus(plan, submissions, numbers, sources)
    observations[0]["outcome_window_end"] = "2024-01-01T00:00:00Z"
    outcomes = build_annual_outcome_corpus(submissions, numbers, sources)
    no_eligible = build_deterioration_labels(observations, annual_outcomes=outcomes, outcome_data_available_through="2024-12-31T23:59:59Z")
    assert no_eligible[0]["reason"][0]["code"] == "TRUE_NO_ELIGIBLE_OUTCOME"
    censored = build_deterioration_labels(observations, annual_outcomes=[observations[0]], outcome_data_available_through="2023-12-01T00:00:00Z")
    assert censored[0]["reason"][0]["code"] == "RIGHT_CENSORED_DATA_HORIZON"


def test_reported_fcf_requires_matching_period_unit_and_consolidated_rows():
    submission = {
        "adsh": "a", "cik": "320193", "form": "10-Q", "period": "20230331",
        "filed": "20230420", "accepted": "20230420120000",
        "__archive_sha256": "a" * 64, "__archive_name": "2023q2.zip",
    }
    base = {"adsh": "a", "version": "us-gaap/2023", "coreg": "", "ddate": "20230331", "qtrs": "1", "uom": "USD", "segments": ""}
    numbers = [
        {**base, "tag": "NetCashProvidedByUsedInOperatingActivities", "value": "100"},
        {**base, "tag": "PaymentsToAcquirePropertyPlantAndEquipment", "value": "40"},
        {**base, "tag": "PaymentsToAcquirePropertyPlantAndEquipment", "value": "999", "segments": "Segment=A"},
    ]
    periods = build_reported_fcf_periods([submission], numbers)
    assert periods[0]["free_cash_flow"] == 60
    assert periods[0]["fact_provenance"]["capital_expenditure"]["qtrs"] == "1"


def test_productive_assets_is_an_evidence_based_capex_equivalent():
    submission = {
        "adsh": "a", "cik": "831259", "form": "10-Q", "period": "20220331",
        "filed": "20220505", "accepted": "20220505120000",
        "__archive_sha256": "a" * 64, "__archive_name": "2022q2.zip",
    }
    base = {"adsh": "a", "version": "us-gaap/2021", "coreg": "", "ddate": "20220331", "qtrs": "1", "uom": "USD", "segments": ""}
    periods = build_reported_fcf_periods([submission], [
        {**base, "tag": "NetCashProvidedByUsedInOperatingActivities", "value": "1691"},
        {**base, "tag": "PaymentsToAcquireProductiveAssets", "value": "723"},
    ])
    assert periods[0]["free_cash_flow"] == 968
    assert periods[0]["fact_provenance"]["capital_expenditure"]["concept"] == "PaymentsToAcquireProductiveAssets"


def test_bulk_rejects_non_fsds_zip(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("other.txt", "x")
    try:
        load_statement_archives([bad])
    except ValueError as error:
        assert "not an SEC" in str(error)
    else:
        raise AssertionError("invalid archive accepted")


def test_pre_num_reference_is_separate_from_adjudicated_gold(tmp_path):
    path = tmp_path / "2022q4.zip"
    _archive(path, 2021, 1000, 100, 200, 200)
    submissions, numbers, sources = load_statement_archives([path])
    plan = [{"observation_id": "aapl-2021", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2021", "split": "train"}]
    observations, _ = build_numeric_corpus(plan, submissions, numbers, sources)
    pre, reference_num, reference_sources = load_pre_num_reference_rows([path], {observations[0]["accession"]})
    rows, report = construct_pre_num_reference(observations, pre, reference_num, reference_sources)
    revenue = next(row for row in rows if row["field"] == "revenue")
    assert revenue["gold_value"] == 1000
    assert revenue["reference_status"] == "RECONCILED_UNAMBIGUOUS"
    assert revenue["validation_status"] == "MACHINE_AGREEMENT"
    assert revenue["review_status"] == "reference_constructed"
    assert report["agreement_rate"] == 1
    assert report["independent_human_gold_status"] == "NOT_ADJUDICATED"
    assert report["verified_reference_fields"] == 0


def test_bulk_and_reference_exclude_dimensional_facts(tmp_path):
    path = tmp_path / "2022q4.zip"
    _archive(path, 2021, 1000, 100, 200, 200)
    with zipfile.ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    num = entries["num.txt"].decode()
    num = num.replace("\tfootnote\n", "\tfootnote\tsegments\n")
    num = num.replace("\t1000\t\n", "\t1000\t\t\n")
    num += "0000320193-22-000001\tRevenueFromContractWithCustomerExcludingAssessedTax\tus-gaap/2023\t\t20210930\t4\tUSD\t50\t\tGeography=US;\n"
    entries["num.txt"] = num.encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, contents in entries.items():
            archive.writestr(name, contents)
    submissions, numbers, sources = load_statement_archives([path])
    plan = [{"observation_id": "aapl-2021", "ticker": "AAPL", "sector": "Technology", "fiscal_year": "2021", "split": "train"}]
    observations, _ = build_numeric_corpus(plan, submissions, numbers, sources)
    assert observations[0]["facts"]["revenue"] == 1000
    pre, reference_num, reference_sources = load_pre_num_reference_rows([path], {observations[0]["accession"]})
    rows, _ = construct_pre_num_reference(observations, pre, reference_num, reference_sources)
    revenue = next(row for row in rows if row["field"] == "revenue")
    assert revenue["gold_value"] == 1000
    assert revenue["reference_status"] == "RECONCILED_UNAMBIGUOUS"
