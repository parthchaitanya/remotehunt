from app.pipeline.scam import detect

LEGIT = """Acme is hiring a remote Junior Python Developer to help build our data platform. You'll work with
FastAPI, PostgreSQL and AWS, pair with senior engineers, and ship features weekly. We offer a competitive salary,
learning budget and flexible hours. Apply through our careers page. We never charge candidates any fee."""


def codes(r):
    return {f["code"] for f in r.flags}


def test_legit_posting_is_low_risk():
    r = detect("Junior Python Developer", "Acme", LEGIT)
    assert r.level == "low"
    assert r.score < 25
    assert "upfront_payment" not in codes(r)  # "never charge ... any fee" is negated


def test_registration_fee_and_telegram_is_high():
    desc = ("Work from home data entry job! Earn $500 per day. No experience required. Pay a small registration "
            "fee of Rs 999 to get started. Contact our HR on Telegram for the interview.") * 2
    r = detect("Online Data Entry Operator", "Global Jobs", desc)
    assert r.level == "high"
    assert {"upfront_payment", "messaging_app_contact", "unrealistic_pay", "vague_task_job"} <= codes(r)
    assert r.score >= 50


def test_negated_fee_not_flagged():
    desc = "There is no registration fee at any stage of our process. " + LEGIT
    assert "upfront_payment" not in codes(detect("Data Analyst", "Acme", desc))


def test_personal_email_and_sensitive_info():
    desc = ("Send your CV to hr.recruit.team@gmail.com. Selected candidates must provide bank account details "
            "and Aadhaar card copy before the interview. ") + LEGIT
    r = detect("Python Developer", "Acme", desc)
    assert {"personal_email_contact", "sensitive_info_request"} <= codes(r)
    assert r.level in ("medium", "high")


def test_crypto_and_check_payment():
    r = detect("Payment Processor", "X", "You will deposit the cheque we send and forward funds via gift cards. " * 3)
    assert "check_or_crypto_payment" in codes(r)


def test_missing_company_and_thin_description():
    r = detect("Developer", "", "Great job, apply now")
    assert {"missing_company", "thin_description"} <= codes(r)


def test_alert_emails_not_penalised_for_short_text():
    r = detect("Data Analyst", "Acme", "", source="gmail_alerts")
    assert "thin_description" not in codes(r)
    assert r.level == "low"


def test_telegram_as_product_is_not_contact_flag():
    desc = "Build Telegram bots and integrations in Python for our messaging platform customers. " + LEGIT
    assert "messaging_app_contact" not in codes(detect("Python Developer", "BotCo", desc))


def test_score_is_capped():
    desc = ("pay a registration fee; contact on whatsapp to interview; earn $900 per day; gift cards; "
            "network marketing; guaranteed job; bit.ly/abc; send your bank account details; data entry") * 3
    assert detect("x", "", desc).score == 100
