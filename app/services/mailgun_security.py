import hashlib
import hmac
import os
import time


MAX_TIMESTAMP_AGE_SECONDS = 300


def validate_mailgun_config() -> None:
    """Fail fast if Mailgun webhook verification is not configured."""
    if not os.getenv("MAILGUN_WEBHOOK_SIGNING_KEY"):
        raise RuntimeError(
            "MAILGUN_WEBHOOK_SIGNING_KEY must be set in the environment."
        )


def verify_mailgun_signature(
    timestamp: str | None,
    token: str | None,
    signature: str | None,
) -> bool:
    """
    Verify Mailgun's HMAC-SHA256 signature for an inbound HTTP forward.

    Mailgun signs the concatenation of timestamp + token with the account's
    webhook signing key. A short timestamp window also limits replay attempts.
    """
    signing_key = os.getenv("MAILGUN_WEBHOOK_SIGNING_KEY")

    if not signing_key or not timestamp or not token or not signature:
        return False

    try:
        timestamp_value = int(timestamp)
    except (TypeError, ValueError):
        return False

    if abs(time.time() - timestamp_value) > MAX_TIMESTAMP_AGE_SECONDS:
        return False

    expected_signature = hmac.new(
        key=signing_key.encode("utf-8"),
        msg=f"{timestamp}{token}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)
