from dataclasses import dataclass
from pathlib import Path

from app.agents.graph import invoke_review
from app.schemas.review import Evidence


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    document: Path
    expected_contract_type: str
    expected_findings: frozenset[str]
    forbidden_findings: frozenset[str] = frozenset()


def score_case(case: EvaluationCase, result: dict) -> dict[str, float | int | bool]:
    all_findings = result["findings"]
    findings_by_title = {finding.title: finding for finding in all_findings}
    actual = set(findings_by_title)
    true_positive = len(actual & case.expected_findings)
    false_positive = len(actual - case.expected_findings)
    false_negative = len(case.expected_findings - actual)
    precision = true_positive / (true_positive + false_positive) if actual else 0.0
    recall = true_positive / len(case.expected_findings) if case.expected_findings else 1.0
    evaluated_titles = actual | case.expected_findings
    squared_errors = []
    for title in evaluated_titles:
        predicted = findings_by_title[title].confidence if title in findings_by_title else 0
        observed = 1 if title in case.expected_findings else 0
        squared_errors.append((predicted - observed) ** 2)
    brier_score = (
        sum(squared_errors) / len(evaluated_titles)
        if evaluated_titles else 0.0
    )
    return {
        "classification_correct": result["contract_type"] == case.expected_contract_type,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "brier_score": round(brier_score, 4),
        "duplicate_rate": round(
            (len(all_findings) - len(findings_by_title)) / len(all_findings),
            4,
        ) if all_findings else 0.0,
        "clause_traceability": round(
            sum(
                finding.clause_id is not None
                or finding.title.lower().startswith("missing ")
                for finding in all_findings
            ) / len(all_findings),
            4,
        ) if all_findings else 1.0,
        "forbidden_findings": len(actual & case.forbidden_findings),
    }


def evaluate_cases(cases: list[EvaluationCase]) -> dict:
    rows = [
        {"name": case.name, **score_case(case, invoke_review(str(case.document)))}
        for case in cases
    ]
    count = len(rows)
    return {
        "cases": rows,
        "classification_accuracy": (
            round(sum(bool(row["classification_correct"]) for row in rows) / count, 4)
            if count else 0.0
        ),
        "mean_precision": (
            round(sum(float(row["precision"]) for row in rows) / count, 4)
            if count else 0.0
        ),
        "mean_recall": (
            round(sum(float(row["recall"]) for row in rows) / count, 4)
            if count else 0.0
        ),
        "mean_brier_score": (
            round(sum(float(row["brier_score"]) for row in rows) / count, 4)
            if count else 0.0
        ),
        "mean_duplicate_rate": (
            round(sum(float(row["duplicate_rate"]) for row in rows) / count, 4)
            if count else 0.0
        ),
        "forbidden_findings": sum(int(row["forbidden_findings"]) for row in rows),
    }


def score_retrieval(
    expected_source_ids: set[str],
    results: list[Evidence],
    k: int = 5,
) -> dict[str, float]:
    ranked_ids = [item.source_id for item in results[:k]]
    hits = expected_source_ids.intersection(ranked_ids)
    recall_at_k = len(hits) / len(expected_source_ids) if expected_source_ids else 1.0
    first_relevant_rank = next(
        (
            index
            for index, source_id in enumerate(ranked_ids, start=1)
            if source_id in expected_source_ids
        ),
        None,
    )
    return {
        f"recall_at_{k}": round(recall_at_k, 4),
        "mrr": round(1 / first_relevant_rank, 4) if first_relevant_rank else 0.0,
    }
