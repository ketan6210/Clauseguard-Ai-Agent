from dataclasses import dataclass


@dataclass(frozen=True)
class ChecklistRequirement:
    category: str
    label: str
    risk_level: str


CONTRACT_CHECKLISTS: dict[str, tuple[ChecklistRequirement, ...]] = {
    "Master Services Agreement": (
        ChecklistRequirement("payment_terms", "payment terms", "High"),
        ChecklistRequirement("renewal", "term and renewal", "Medium"),
        ChecklistRequirement("termination", "termination rights", "High"),
        ChecklistRequirement("confidentiality", "confidentiality", "High"),
        ChecklistRequirement("data_breach_notification", "security-incident notification", "High"),
        ChecklistRequirement("data_deletion", "data deletion", "High"),
        ChecklistRequirement("security_controls", "security controls", "High"),
        ChecklistRequirement("business_continuity", "business continuity and disaster recovery", "Medium"),
        ChecklistRequirement("insurance", "appropriate insurance coverage", "Medium"),
        ChecklistRequirement("data_use_restrictions", "customer-data use restrictions", "High"),
        ChecklistRequirement("intellectual_property", "intellectual-property ownership", "High"),
        ChecklistRequirement("warranty", "warranties", "Medium"),
        ChecklistRequirement("indemnification", "indemnification", "High"),
        ChecklistRequirement("liability", "limitation of liability", "High"),
        ChecklistRequirement("audit_rights", "audit rights", "Medium"),
        ChecklistRequirement("governing_law", "governing law", "Medium"),
        ChecklistRequirement("assignment", "assignment", "Medium"),
    ),
    "Vendor Agreement": (
        ChecklistRequirement("payment_terms", "payment terms", "Medium"),
        ChecklistRequirement("termination", "termination rights", "High"),
        ChecklistRequirement("confidentiality", "confidentiality", "High"),
        ChecklistRequirement("data_breach_notification", "security-incident notification", "High"),
        ChecklistRequirement("data_deletion", "data deletion", "High"),
        ChecklistRequirement("security_controls", "security controls", "High"),
        ChecklistRequirement("business_continuity", "business continuity and disaster recovery", "Medium"),
        ChecklistRequirement("insurance", "appropriate insurance coverage", "Medium"),
        ChecklistRequirement("audit_rights", "audit rights", "Medium"),
        ChecklistRequirement("liability", "limitation of liability", "High"),
    ),
    "Data Processing Agreement": (
        ChecklistRequirement("data_breach_notification", "security-incident notification", "High"),
        ChecklistRequirement("data_deletion", "data deletion", "High"),
        ChecklistRequirement("data_retention", "data-retention limits", "High"),
        ChecklistRequirement("security_controls", "security controls", "High"),
        ChecklistRequirement("audit_rights", "audit rights", "Medium"),
        ChecklistRequirement("subprocessors", "subprocessor controls", "High"),
        ChecklistRequirement("cross_border_transfer", "cross-border transfer safeguards", "High"),
    ),
    "NDA": (
        ChecklistRequirement("confidentiality", "confidentiality obligations", "High"),
        ChecklistRequirement("termination", "term or termination", "Medium"),
        ChecklistRequirement("governing_law", "governing law", "Medium"),
    ),
    "Service Agreement": (
        ChecklistRequirement("payment_terms", "payment terms", "Medium"),
        ChecklistRequirement("termination", "termination rights", "High"),
        ChecklistRequirement("confidentiality", "confidentiality", "High"),
        ChecklistRequirement("warranty", "warranties", "Medium"),
        ChecklistRequirement("liability", "limitation of liability", "High"),
        ChecklistRequirement("governing_law", "governing law", "Medium"),
    ),
}

CATEGORY_EQUIVALENTS = {
    "termination": {
        "termination",
        "termination_for_convenience",
        "termination_cure_period",
        "early_termination_fee",
    },
}


def get_contract_checklist(contract_type: str) -> tuple[ChecklistRequirement, ...]:
    return CONTRACT_CHECKLISTS.get(contract_type, ())


def category_is_present(required_category: str, present_categories: set[str]) -> bool:
    acceptable = CATEGORY_EQUIVALENTS.get(required_category, {required_category})
    return bool(acceptable & present_categories)
