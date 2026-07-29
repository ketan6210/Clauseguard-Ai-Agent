import json
from pathlib import Path

from app.services.evaluation import EvaluationCase, evaluate_cases


def main() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / "evaluation" / "cases.json"
    cases = []
    for item in json.loads(manifest_path.read_text(encoding="utf-8")):
        cases.append(
            EvaluationCase(
                name=item["name"],
                document=(manifest_path.parent / item["document"]).resolve(),
                expected_contract_type=item["expected_contract_type"],
                expected_findings=frozenset(item["expected_findings"]),
                forbidden_findings=frozenset(item.get("forbidden_findings", [])),
            )
        )
    print(json.dumps(evaluate_cases(cases), indent=2))


if __name__ == "__main__":
    main()
