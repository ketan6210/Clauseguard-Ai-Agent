import re

from app.schemas.review import Clause, Evidence, Finding
from app.services.contract_checklists import category_is_present, get_contract_checklist
from app.services.number_parser import (
    extract_duration,
    extract_measurements,
    extract_number_of_days,
    extract_number_of_hours,
    extract_payment_days,
    extract_percentages,
)


def _finding(clause: Clause, title: str, level: str, explanation: str, action: str, evidence: list[Evidence]) -> Finding:
    return Finding(id=f"finding-{clause.id}-{re.sub('[^a-z]+', '-', title.lower()).strip('-')}", clause_id=clause.id, title=title, risk_level=level, confidence=0.5, explanation=explanation, recommended_action=action, contract_excerpt=clause.text[:500], evidence=evidence)


def analyze_clause_risk(clause: Clause, evidence: list[Evidence]) -> list[Finding]:
    text = clause.text.lower()
    findings: list[Finding] = []
    days = extract_number_of_days(text)
    hours = extract_number_of_hours(text)
    if clause.clause_type == "data_breach_notification" and hours and hours > 72:
        findings.append(_finding(clause, "Breach notification exceeds 72 hours", "High", f"The clause permits notification after approximately {hours} hours, exceeding the 72-hour policy.", "Require notification within 72 hours of discovery.", evidence))
    if clause.clause_type == "renewal" and ("automatic" in text or "auto-renew" in text) and days and days > 30:
        findings.append(_finding(clause, "Excessive renewal cancellation notice", "High" if days > 90 else "Medium", f"Cancellation requires {days} days notice; policy permits no more than 30.", "Reduce the non-renewal notice period to 30 days.", evidence))
    if clause.clause_type == "payment_terms":
        payment_days = extract_payment_days(text)
        if payment_days and payment_days > 45:
            findings.append(_finding(clause, "Payment terms exceed Net 45", "Medium", f"Payment is due after {payment_days} days, outside the standard policy.", "Negotiate Net 45 or obtain Finance approval.", evidence))
    if clause.clause_type == "liability":
        months = extract_duration(text, "months")
        if months is not None and months < 12:
            formatted_months = int(months) if months.is_integer() else months
            findings.append(_finding(clause, "Liability cap below policy", "High", f"The liability cap is {formatted_months} month(s) of fees; policy requires at least 12 months.", "Raise the cap to at least 12 months of fees.", evidence))

    if clause.clause_type == "data_deletion":
        retention_days = [
            int(measurement.days)
            for measurement in extract_measurements(text)
            if measurement.unit in {"days", "weeks", "months", "years"}
        ]
        if retention_days and max(retention_days) > 30:
            findings.append(_finding(clause, "Excessive post-termination data retention", "High", f"The clause permits retention for up to {max(retention_days)} days; policy requires deletion or return within 30 days.", "Require complete return or deletion within 30 days, including backups and derived copies.", evidence))

    if clause.clause_type == "ai_training" and any(term in text for term in ("customer data", "prompts", "outputs")):
        findings.append(_finding(clause, "Customer data may be used for AI training", "High", "The provider may use customer content to train or improve models, potentially exposing confidential or personal data.", "Prohibit model training on customer data unless separately and expressly approved.", evidence))

    if clause.clause_type == "data_licensing" and any(term in text for term in ("perpetual", "irrevocable", "sublicensable", "commercialize")):
        findings.append(_finding(clause, "Overly broad customer-data license", "High", "The customer grants broad continuing rights over its data, including rights that may survive the service relationship.", "Limit the license to processing necessary to provide the contracted services during the agreement term.", evidence))

    if clause.clause_type in {"data_sharing", "data_commercialization"} and any(term in text for term in ("data broker", "marketing partner", "advertising", "sell", "commercialize")):
        level = "Critical" if any(term in text for term in ("sell customer data", "commercialize customer data")) else "High"
        findings.append(_finding(clause, "Customer data may be commercialized or broadly shared", level, "The clause permits disclosure or commercial use beyond providing the contracted service.", "Restrict sharing to approved subprocessors under equivalent data-protection obligations.", evidence))

    if clause.clause_type == "feedback_rights" and any(term in text for term in ("perpetual", "irrevocable", "commercialize")):
        findings.append(_finding(clause, "Broad feedback-use rights", "Medium", "The provider receives broad rights to use and commercialize feedback without attribution or compensation, but the clause does not grant rights to Customer Data.", "Limit the license to non-confidential feedback and exclude Customer Data, prompts, and outputs.", evidence))

    if clause.clause_type == "price_changes":
        percentages = extract_percentages(text)
        increase = max(percentages, default=0)
        if increase > 10 or "then-current" in text or "current term" in text:
            findings.append(_finding(clause, "Unilateral price increase", "High", f"The provider may increase fees{' by up to ' + str(increase) + '%' if increase else ''} without a corresponding customer termination right.", "Allow price changes only at renewal with advance notice and a right not to renew.", evidence))

    if clause.clause_type == "unilateral_changes":
        findings.append(_finding(clause, "Unilateral service or policy changes", "Medium", "The provider may change material service or policy terms without meaningful customer consent or remedy.", "Require advance notice and a termination right for materially adverse changes.", evidence))

    if clause.clause_type == "termination_for_convenience" and "provider may" in text:
        level = "High" if "customer may not" in text or "customer may terminate only" in text else "Medium"
        findings.append(_finding(clause, "One-sided termination right", level, "The provider has a convenience termination right that is not equally available to the customer.", "Make convenience termination rights mutual and provide sufficient transition notice.", evidence))

    if clause.clause_type == "termination_cure_period":
        cure_days = max(
            (int(item.days) for item in extract_measurements(text) if item.unit in {"days", "weeks", "months"}),
            default=0,
        )
        if cure_days > 30 or "customer may not terminate for convenience" in text:
            findings.append(_finding(clause, "Restrictive customer termination rights", "High", f"Customer termination is restricted by a cure period of up to {cure_days} days and/or lacks a convenience right.", "Use a 30-day cure period and add a reasonable customer termination-for-convenience right.", evidence))

    no_termination_charge = any(term in text for term in ("no termination charge", "no additional termination charge", "without a termination charge"))
    if clause.clause_type == "early_termination_fee" and not no_termination_charge and any(term in text for term in ("remaining fees", "termination charge", "transition fee")):
        findings.append(_finding(clause, "Excessive early-termination charges", "High", "The customer may owe future fees and additional charges after early termination.", "Limit charges to undisputed fees for services delivered through the termination date.", evidence))

    if clause.clause_type == "indemnification" and "customer will" in text and any(term in text for term in ("indemnify", "defend")):
        findings.append(_finding(clause, "Broad customer indemnification", "High", "The customer indemnity appears broad and may cover claims beyond the customer's direct misconduct.", "Limit indemnity to defined third-party claims caused by the indemnifying party's breach, negligence, or misconduct.", evidence))
    if clause.clause_type == "indemnification" and "provider will" in text and any(term in text for term in ("united states patent", "no obligation", "sole control", "within five")):
        findings.append(_finding(clause, "Narrow provider indemnification", "High", "Provider indemnification is limited by narrow claim types, short notice requirements, broad exclusions, or provider-controlled remedies.", "Expand provider indemnity to cover IP, data, confidentiality, security, and legal-compliance claims with reasonable procedures.", evidence))

    if "customer" in text and "uncapped" in text and any(term in text for term in ("liability", "obligations", "indemnification")):
        findings.append(_finding(clause, "Unequal uncapped customer liability", "High", "Customer exposure is uncapped while provider liability is limited, creating materially asymmetric risk allocation.", "Apply mutual caps and negotiate only narrow, reciprocal exceptions for specified high-risk claims.", evidence))

    if clause.clause_type == "service_levels":
        percentages = extract_percentages(text)
        uptime = max((value for value in percentages if value >= 90), default=None)
        weak_uptime = uptime is not None and uptime < 99.9
        sole_remedy = "sole remedy" in text
        if weak_uptime and sole_remedy:
            findings.append(_finding(clause, "Weak SLA with exclusive service-credit remedy", "Medium", f"Availability is {uptime}% and service credits are the customer's sole remedy.", "Negotiate at least 99.9% monthly uptime plus termination and refund rights for chronic failures.", evidence))
        elif weak_uptime:
            findings.append(_finding(clause, "Weak availability commitment", "Medium", f"The stated availability level is {uptime}%, below the 99.9% review benchmark.", "Negotiate at least 99.9% monthly uptime with meaningful service credits.", evidence))
        elif sole_remedy:
            findings.append(_finding(clause, "Service credits are the sole remedy", "Medium", "The customer's remedies for repeated service failure are restricted to service credits.", "Add termination and refund rights for chronic or severe SLA failures.", evidence))

    if clause.clause_type == "security_controls" and any(term in text for term in ("considers commercially reasonable", "does not warrant compliance", "commercially reasonable")):
        findings.append(_finding(clause, "Weak security-control commitment", "High", "Security obligations are subjective and do not commit to a defined standard or control baseline.", "Require a defined security schedule and recognized control framework.", evidence))

    if clause.clause_type == "subprocessors" and any(term in text for term in ("any country", "without notice", "without consent")):
        findings.append(_finding(clause, "Unrestricted subprocessor use", "Medium", "The provider may use subprocessors broadly without adequate notice, location, or objection protections.", "Require a subprocessor list, advance notice, objection rights, and equivalent contractual safeguards.", evidence))

    if clause.clause_type == "warranty" and any(term in text for term in ("as is", "disclaims all", "no warranty")):
        findings.append(_finding(clause, "Broad warranty disclaimer", "Medium", "The provider broadly disclaims service warranties and performance commitments.", "Add performance, legal compliance, security, and non-infringement warranties.", evidence))

    if clause.clause_type == "restrictive_covenants":
        level = "High" if any(term in text for term in ("non-compete", "non-competition", "competes with")) else "Medium"
        findings.append(_finding(clause, "Restrictive customer covenant", level, "The clause may prevent competitive activity, hiring, benchmarking, or other legitimate customer conduct.", "Remove the restriction or narrowly limit its scope, duration, and affected parties.", evidence))

    if clause.clause_type == "publicity_rights" and any(term in text for term in ("without approval", "customer lists", "press releases")):
        findings.append(_finding(clause, "Publicity rights without customer approval", "Medium", "The provider may publicly use the customer's identity, marks, or relationship without case-by-case approval.", "Require prior written approval for each press release, case study, logo use, or testimonial.", evidence))

    if clause.clause_type in {"arbitration_costs", "dispute_resolution"} and "customer" in text and any(term in text for term in ("advance all arbitration fees", "provider's reasonable legal fees")):
        findings.append(_finding(clause, "One-sided arbitration cost shifting", "High", "The customer must advance arbitration costs and provider legal fees regardless of the final outcome.", "Require each party to bear its own fees and split neutral costs, subject to the arbitrator's final award.", evidence))

    if clause.clause_type == "assignment" and "provider may assign" in text and "customer may not assign" in text:
        findings.append(_finding(clause, "One-sided assignment rights", "Medium", "The provider can assign freely while customer assignment is restricted, including during corporate transactions.", "Make assignment restrictions mutual and permit assignments to affiliates and successors with notice.", evidence))

    return findings


def detect_missing_clauses(contract_type: str, clauses: list[Clause], evidence_by_category: dict[str, list[Evidence]]) -> list[Finding]:
    present = {clause.clause_type for clause in clauses}
    findings = []
    for requirement in get_contract_checklist(contract_type):
        if category_is_present(requirement.category, present):
            continue
        title = f"Missing {requirement.label} clause"
        findings.append(Finding(id=f"finding-missing-{requirement.category}", title=title, risk_level=requirement.risk_level, confidence=0.5, explanation=f"No {requirement.label} clause was detected, but the {contract_type} checklist requires one.", recommended_action="Add approved language or document the reviewer's exception before execution.", contract_excerpt="No matching clause found.", evidence=evidence_by_category.get(requirement.category, [])))
    return findings
