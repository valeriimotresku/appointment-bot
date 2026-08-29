import re

from starlette.datastructures import FormData


EXPECTED_SENDER_DOMAIN = "frontdesksuite.com"
EXPECTED_SUBJECT_PATTERN = r"Bestätigen.*Mail"


def parse_confirmation_email(
    form: FormData,
) -> tuple[str, str] | None:
    """Parse a verified Mailgun inbound form and extract the confirmation code."""

    sender = str(form.get("sender", ""))
    recipient = str(form.get("recipient", ""))
    subject = str(form.get("subject", ""))
    body = str(form.get("body-plain", ""))

    print(f"[Email] From: {sender}")
    print(f"[Email] To: {recipient}")
    print(f"[Email] Subject: {subject}")

    sender_domain = sender.rsplit("@", 1)[-1].lower()

    if not (
        sender_domain == EXPECTED_SENDER_DOMAIN
        or sender_domain.endswith("." + EXPECTED_SENDER_DOMAIN)
    ):
        print(f"[Email] Ignored sender: {sender}")
        return None

    if not re.search(
        EXPECTED_SUBJECT_PATTERN,
        subject,
        re.IGNORECASE,
    ):
        print("[Email] Ignored: wrong subject")
        return None

    match = re.search(r"\b\d{4}\b", body)

    if not match:
        print("[Email] Confirmation code not found")
        return None

    code = match.group(0)

    print(f"[Email] Found confirmation code: {code}")

    return recipient.lower(), code
