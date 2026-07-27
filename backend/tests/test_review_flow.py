import os
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_clauseguard.db"
os.environ["UPLOAD_DIR"] = "./test_uploads"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
SAMPLE = Path(__file__).resolve().parents[2] / "sample_documents" / "vendor_agreement.txt"


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_complete_review_flow():
    with SAMPLE.open("rb") as document:
        response = client.post("/reviews/upload", files={"file": (SAMPLE.name, document, "text/plain")})
    assert response.status_code == 201, response.text
    review = response.json()
    assert review["contract_type"] == "Vendor Agreement"
    titles = {finding["title"] for finding in review["findings"]}
    assert "Breach notification exceeds 72 hours" in titles
    assert "Missing data deletion clause" in titles
    assert "Missing audit rights clause" in titles

    finding_id = review["findings"][0]["id"]
    decision = client.post(f"/reviews/{review['review_id']}/decision", json={"finding_id": finding_id, "decision": "approved", "comment": "Confirmed"})
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"

    question = client.post(f"/reviews/{review['review_id']}/ask", json={"question": "What are the breach notification terms?"})
    assert question.status_code == 200
    assert question.json()["citations"]
