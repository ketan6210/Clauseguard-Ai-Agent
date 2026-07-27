import pytest

from app.services.clause_classifier import classify_clause


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "7.3 AI Training Provider may use Customer Data and prompts to train and fine-tune machine-learning models.",
            "ai_training",
        ),
        (
            "7.2 License to Provider Customer grants a perpetual, irrevocable, transferable, sublicensable license.",
            "data_licensing",
        ),
        (
            "7.4 Data Sharing Provider may share Customer Data with data brokers and marketing partners.",
            "data_sharing",
        ),
        (
            "Provider may commercialize and sell Customer Data to advertising partners.",
            "data_commercialization",
        ),
        (
            "3.4 Price Changes Provider may increase fees by twenty-five percent during the current term.",
            "price_changes",
        ),
        (
            "5.1 Provider may terminate for convenience on ten days notice.",
            "termination_for_convenience",
        ),
        (
            "5.2 Customer may terminate only if Provider fails to cure a material breach within sixty days.",
            "termination_cure_period",
        ),
        (
            "5.3 Early Termination Charge Customer must pay all remaining fees plus a transition fee.",
            "early_termination_fee",
        ),
        (
            "10.1 Service Level Provider targets 99.5% uptime and offers service credits.",
            "service_levels",
        ),
        (
            "Provider may use subprocessors and affiliates in any country.",
            "subprocessors",
        ),
        (
            "14. Restrictive Covenants Customer agrees to a non-compete and non-solicit restriction.",
            "restrictive_covenants",
        ),
    ],
)
def test_specific_clause_categories(text, expected):
    assert classify_clause(text) == expected


def test_ordinary_contract_breach_is_not_security_notification():
    text = (
        "Provider will give thirty days notice of a service modification, but failure "
        "to provide notice will not constitute a breach."
    )

    assert classify_clause(text) == "unilateral_changes"


def test_security_breach_notification_requires_security_context():
    text = "Provider will notify Customer within five days after discovering a data breach."

    assert classify_clause(text) == "data_breach_notification"
