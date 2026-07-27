import re

from app.schemas.review import Clause, Evidence, QuestionResponse


STOPWORDS = {"what", "which", "does", "this", "that", "with", "from", "about", "contract", "agreement", "have", "are", "the", "and", "for"}


def answer_question(question: str, clauses: list[Clause], evidence: list[Evidence]) -> QuestionResponse:
    terms = {word for word in re.findall(r"[a-z0-9]+", question.lower()) if len(word) > 2 and word not in STOPWORDS}
    ranked = sorted(clauses, key=lambda clause: len(terms & set(re.findall(r"[a-z0-9]+", clause.text.lower()))), reverse=True)
    matches = [clause for clause in ranked[:3] if terms & set(re.findall(r"[a-z0-9]+", clause.text.lower()))]
    if not matches:
        answer = "I could not find a clearly relevant clause in this document. A human reviewer should verify the source contract."
    else:
        excerpts = " ".join(f"Page {item.page}: {item.text}" for item in matches)
        answer = f"Based on the most relevant contract language: {excerpts[:1200]}"
    return QuestionResponse(answer=answer, citations=evidence[:5])


def generate_finding_explanation(clause, evidence, rule_result) -> str:
    return rule_result or "The clause differs from the retrieved company policy and requires human review."
