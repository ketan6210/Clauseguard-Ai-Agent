import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.graph import invoke_review
from app.services.clause_classifier import classify_clause
from app.core.config import settings
from app.db.database import get_db
from app.db.models import FindingValidation, Review, ReviewerDecision
from app.schemas.review import DecisionRequest, DecisionResponse, Finding, QuestionRequest, QuestionResponse, ReviewResponse, ValidationRequest, ValidationResponse
from app.services.llm_service import answer_question
from app.services.contract_store import search_contract_clauses
from app.services.policy_store import hybrid_search, load_policies
from app.services.report_service import create_report_json
from app.services.review_metrics import calculate_review_metrics
from app.services.upload_security import validate_uploaded_document


router = APIRouter(prefix="/reviews", tags=["reviews"])
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def _response(record: Review) -> ReviewResponse:
    findings = [Finding.model_validate(item) for item in json.loads(record.findings_json)]
    return ReviewResponse(
        review_id=record.id,
        filename=record.filename,
        contract_type=record.contract_type,
        summary=record.summary,
        clauses=json.loads(record.clauses_json),
        findings=findings,
        metrics=calculate_review_metrics(findings),
    )


def _get_review(review_id: str, db: Session) -> Review:
    record = db.get(Review, review_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return record


@router.post("/upload", response_model=ReviewResponse, status_code=201)
def upload_review(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Supported types: PDF, DOCX, TXT, and Markdown")
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    review_id = str(uuid.uuid4())
    file_path = upload_dir / f"{review_id}{suffix}"
    try:
        with file_path.open("wb") as destination:
            shutil.copyfileobj(file.file, destination)
        if file_path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("File exceeds the 20 MB limit")
        validate_uploaded_document(file_path, suffix)
        result = invoke_review(str(file_path), review_id)
    except ValueError as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        file.file.close()
    record = Review(id=review_id, filename=filename, contract_type=result["contract_type"], summary=result["summary"], clauses_json=json.dumps([item.model_dump() for item in result["clauses"]]), findings_json=json.dumps([item.model_dump() for item in result["findings"]]))
    db.add(record)
    db.commit()
    return _response(record)


@router.get("/metrics/confidence")
@router.get("/metrics/calibration")
def confidence_metrics(db: Session = Depends(get_db)):
    buckets = {
        "0-59": {"count": 0, "approved": 0, "confidence_total": 0.0},
        "60-79": {"count": 0, "approved": 0, "confidence_total": 0.0},
        "80-100": {"count": 0, "approved": 0, "confidence_total": 0.0},
    }
    validations = db.scalars(select(FindingValidation)).all()
    reviews = {
        review.id: review
        for review in db.scalars(select(Review)).all()
    }
    for validation in validations:
        if validation.label == "uncertain":
            continue
        review = reviews.get(validation.review_id)
        if not review:
            continue
        finding = next(
            (
                item
                for item in json.loads(review.findings_json)
                if item["id"] == validation.finding_id
            ),
            None,
        )
        if not finding:
            continue
        confidence = validation.combined_score
        bucket_name = "0-59" if confidence < 0.6 else "60-79" if confidence < 0.8 else "80-100"
        bucket = buckets[bucket_name]
        bucket["count"] += 1
        bucket["approved"] += validation.label == "valid"
        bucket["confidence_total"] += confidence
    output = {}
    weighted_error = 0.0
    total = sum(bucket["count"] for bucket in buckets.values())
    for name, bucket in buckets.items():
        count = bucket["count"]
        approval_rate = bucket["approved"] / count if count else 0
        average_strength = bucket["confidence_total"] / count if count else 0
        error = abs(average_strength - approval_rate) if count else 0
        weighted_error += error * count
        output[name] = {
            "count": count,
            "approval_rate": round(approval_rate, 4),
            "validity_rate": round(approval_rate, 4),
            "average_match_strength": round(average_strength, 4),
            "calibration_error": round(error, 4),
        }
    return {
        "reviewed_findings": total,
        "expected_calibration_error": round(weighted_error / total, 4) if total else None,
        "buckets": output,
    }


@router.get("/{review_id}", response_model=ReviewResponse)
def get_review(review_id: str, db: Session = Depends(get_db)):
    return _response(_get_review(review_id, db))


@router.post("/{review_id}/ask", response_model=QuestionResponse)
def ask(review_id: str, request: QuestionRequest, db: Session = Depends(get_db)):
    review = _response(_get_review(review_id, db))
    contract_evidence = search_contract_clauses(
        review_id,
        request.question,
        review.clauses,
    )
    question_category = classify_clause(request.question)
    if question_category != "other":
        contract_evidence = [
            item
            for item in contract_evidence
            if item.section.split(" · ", 1)[0] == question_category
        ]
    policy_evidence = hybrid_search(request.question)
    retrieved_categories = {
        item.section.split(" · ", 1)[0] for item in contract_evidence
    }
    if question_category != "other":
        retrieved_categories = {question_category}
    policy_categories = {
        policy["id"]: policy["category"] for policy in load_policies()
    }
    category_matched_policies = [
        item
        for item in policy_evidence
        if policy_categories.get(item.source_id) in retrieved_categories
    ]
    if category_matched_policies:
        policy_evidence = [
            item for item in category_matched_policies
            if item.score >= settings.policy_retrieval_min_score
        ]
    else:
        policy_evidence = []
    return answer_question(request.question, contract_evidence, policy_evidence)


@router.post("/{review_id}/decision", response_model=DecisionResponse)
def decide(review_id: str, request: DecisionRequest, db: Session = Depends(get_db)):
    record = _get_review(review_id, db)
    findings = json.loads(record.findings_json)
    finding = next((item for item in findings if item["id"] == request.finding_id), None)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    finding["status"] = request.decision
    record.findings_json = json.dumps(findings)
    reviewer_decision = db.scalar(
        select(ReviewerDecision).where(
            ReviewerDecision.review_id == review_id,
            ReviewerDecision.finding_id == request.finding_id,
        )
    )
    if reviewer_decision:
        reviewer_decision.decision = request.decision
        reviewer_decision.comment = request.comment
    else:
        reviewer_decision = ReviewerDecision(id=str(uuid.uuid4()), review_id=review_id, finding_id=request.finding_id, decision=request.decision, comment=request.comment)
    db.add(reviewer_decision)
    db.commit()
    return DecisionResponse(finding_id=request.finding_id, status=request.decision)


@router.post("/{review_id}/validation", response_model=ValidationResponse)
def validate_finding(
    review_id: str,
    request: ValidationRequest,
    db: Session = Depends(get_db),
):
    record = _get_review(review_id, db)
    finding = next(
        (
            item
            for item in json.loads(record.findings_json)
            if item["id"] == request.finding_id
        ),
        None,
    )
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    validation = db.scalar(
        select(FindingValidation).where(
            FindingValidation.review_id == review_id,
            FindingValidation.finding_id == request.finding_id,
        )
    )
    if validation:
        validation.label = request.label
        validation.combined_score = float(finding.get("combined_score", finding.get("confidence", 0)))
        validation.pipeline_version = settings.pipeline_version
    else:
        validation = FindingValidation(
            id=str(uuid.uuid4()),
            review_id=review_id,
            finding_id=request.finding_id,
            label=request.label,
            combined_score=float(finding.get("combined_score", finding.get("confidence", 0))),
            pipeline_version=settings.pipeline_version,
        )
    db.add(validation)
    db.commit()
    return ValidationResponse(
        finding_id=request.finding_id,
        label=request.label,
        pipeline_version=settings.pipeline_version,
    )


@router.get("/{review_id}/report")
def report(review_id: str, db: Session = Depends(get_db)):
    return create_report_json(_response(_get_review(review_id, db)))
