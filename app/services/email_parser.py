import os
import time
import re
from imapclient import IMAPClient
import pyzmail

EMAIL_HOST = os.getenv("EMAIL_USER", "imap.gmx.com")  # or your mail server
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")  # Gmail App Password

def wait_for_confirmation_code(timeout=60):
    """
    Waits for the confirmation email and extracts the code.
    timeout = max seconds to wait.
    """
    end_time = time.time() + timeout

    with IMAPClient(EMAIL_HOST) as server:
        server.login(EMAIL_USER, EMAIL_PASS)
        server.select_folder("INBOX")

        while time.time() < end_time:
            # Search for unread emails
            messages = server.search(['UNSEEN'])
            for msgid, data in server.fetch(messages, ['RFC822']).items():
                email_message = pyzmail.PyzMessage.factory(data[b'RFC822'])
                subject = email_message.get_subject()
                from_email = email_message.get_addresses('from')

                # Check sender
                if not any(addr.lower() == "noreply@frontdesksuite.com" for name, addr in from_email):
                    continue  # skip this email

                # Check subject contains "Bestätigen ... Mail"
                if not re.search(r"Bestätigen.*Mail", subject, re.IGNORECASE):
                    continue  # skip if subject doesn't match

                # Get text content
                if email_message.text_part:
                    body = email_message.text_part.get_payload().decode(email_message.text_part.charset)
                else:
                    body = ""

                # Look for code (e.g., 4-digit number)
                match = re.search(r"\b\d{4}\b", body)
                if match:
                    code = match.group(0)
                    # Mark as seen
                    server.add_flags(msgid, [IMAPClient.SEEN])
                    print(f"[Email] Found confirmation code: {code}")
                    return code

            time.sleep(1)  # check every 1 second

    print("[Email] Timeout: No confirmation email found.")
    return None
