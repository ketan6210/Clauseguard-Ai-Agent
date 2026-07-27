import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.graph import invoke_review
from app.core.config import settings
from app.db.database import get_db
from app.db.models import Review, ReviewerDecision
from app.schemas.review import DecisionRequest, DecisionResponse, QuestionRequest, QuestionResponse, ReviewResponse
from app.services.llm_service import answer_question
from app.services.policy_store import hybrid_search
from app.services.report_service import create_report_json


router = APIRouter(prefix="/reviews", tags=["reviews"])
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def _response(record: Review) -> ReviewResponse:
    return ReviewResponse(review_id=record.id, filename=record.filename, contract_type=record.contract_type, summary=record.summary, clauses=json.loads(record.clauses_json), findings=json.loads(record.findings_json))


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
        result = invoke_review(str(file_path))
    except ValueError as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        file.file.close()
    record = Review(id=review_id, filename=filename, contract_type=result["contract_type"], summary=result["summary"], clauses_json=json.dumps([item.model_dump() for item in result["clauses"]]), findings_json=json.dumps([item.model_dump() for item in result["findings"]]))
    db.add(record)
    db.commit()
    return _response(record)


@router.get("/{review_id}", response_model=ReviewResponse)
def get_review(review_id: str, db: Session = Depends(get_db)):
    return _response(_get_review(review_id, db))


@router.post("/{review_id}/ask", response_model=QuestionResponse)
def ask(review_id: str, request: QuestionRequest, db: Session = Depends(get_db)):
    review = _response(_get_review(review_id, db))
    return answer_question(request.question, review.clauses, hybrid_search(request.question))


@router.post("/{review_id}/decision", response_model=DecisionResponse)
def decide(review_id: str, request: DecisionRequest, db: Session = Depends(get_db)):
    record = _get_review(review_id, db)
    findings = json.loads(record.findings_json)
    finding = next((item for item in findings if item["id"] == request.finding_id), None)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    finding["status"] = request.decision
    record.findings_json = json.dumps(findings)
    db.add(ReviewerDecision(id=str(uuid.uuid4()), review_id=review_id, finding_id=request.finding_id, decision=request.decision, comment=request.comment))
    db.commit()
    return DecisionResponse(finding_id=request.finding_id, status=request.decision)


@router.get("/{review_id}/report")
def report(review_id: str, db: Session = Depends(get_db)):
    return create_report_json(_response(_get_review(review_id, db)))
