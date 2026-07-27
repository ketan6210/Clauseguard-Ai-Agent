from app.schemas.review import DocumentPage
from app.services.clause_classifier import extract_clauses


def test_extracts_hierarchical_clauses_and_removes_pdf_furniture():
    pages = [
        DocumentPage(
            page_number=1,
            text="""
            SAMPLE - NOT LEGALLY BINDING
            Contract ID: CG-100
            Page 1
            MASTER SERVICES AGREEMENT
            This Agreement is entered into between Provider and Customer.
            1. Definitions
            1.1 Customer Data
            Customer Data means information submitted by Customer.
            """,
        ),
        DocumentPage(
            page_number=2,
            text="""
            SAMPLE - NOT LEGALLY BINDING
            Contract ID: CG-100
            Page 2
            CONTENTS
            1. Definitions
            2. Fees and Payment
            3. Term and Renewal
            4. Data Rights
            Schedule A - Order Form
            """,
        ),
        DocumentPage(
            page_number=3,
            text="""
            SAMPLE - NOT LEGALLY BINDING
            Contract ID: CG-100
            Page 3
            2. Fees and Payment
            2.1 Payment Terms
            Invoices are due within sixty (60) days.
            3. Term and Renewal
            3.1 Automatic Renewal
            This Agreement automatically renews unless Customer gives 120 days notice.
            SIGNATURE PAGE
            Provider: __________________
            Customer: __________________
            """,
        ),
    ]

    clauses = extract_clauses(pages)

    assert len(clauses) == 4
    assert clauses[0].text.startswith("MASTER SERVICES AGREEMENT")
    assert clauses[1].text == "1.1 Customer Data Customer Data means information submitted by Customer."
    assert clauses[2].text.startswith("2.1 Payment Terms")
    assert clauses[2].page == 3
    assert clauses[3].text.startswith("3.1 Automatic Renewal")
    assert all("CONTENTS" not in clause.text for clause in clauses)
    assert all("SAMPLE - NOT LEGALLY BINDING" not in clause.text for clause in clauses)
    assert all("SIGNATURE PAGE" not in clause.text for clause in clauses)


def test_heading_without_body_is_not_a_clause():
    pages = [
        DocumentPage(
            page_number=1,
            text="""
            VENDOR AGREEMENT
            5. Termination
            5.1 Termination for Cause
            Either party may terminate for an uncured material breach.
            """,
        )
    ]

    clauses = extract_clauses(pages)

    assert [clause.text for clause in clauses] == [
        "5.1 Termination for Cause Either party may terminate for an uncured material breach."
    ]


def test_single_line_numbered_clauses_remain_separate():
    pages = [
        DocumentPage(
            page_number=1,
            text=(
                "1. Services. Vendor provides analytics services.\n\n"
                "2. Payment Terms. Invoices are payable Net 60.\n\n"
                "3. Termination. Either party may terminate for breach."
            ),
        )
    ]

    clauses = extract_clauses(pages)

    assert len(clauses) == 3
    assert clauses[0].text == "1. Services. Vendor provides analytics services."
    assert clauses[1].clause_type == "payment_terms"
    assert clauses[2].clause_type == "termination"
