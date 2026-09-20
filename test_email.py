"""
Quick standalone test for tools/mailbox.py — sends yourself one test email
via SMTP + Gmail App Password. Doesn't touch Supabase, the agent pipeline,
or the live server. Run this from the repo root: python3 test_mailbox.py
"""

import os
from tools.mailbox import send_email_smtp, verify_mailbox_credentials

# --- Fill these in before running (or set as env vars) ---
GMAIL_ADDRESS = os.getenv("TEST_GMAIL_ADDRESS", "your.email@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("TEST_GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
SEND_TO = os.getenv("TEST_SEND_TO", GMAIL_ADDRESS)  # defaults to sending to yourself
# -----------------------------------------------------------

def main():
    print(f"Verifying credentials for {GMAIL_ADDRESS}...")
    verify_mailbox_credentials(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    print("Login OK. Sending test email...")

    result = send_email_smtp(
        to_email=SEND_TO,
        subject="Scout mailbox test",
        body="If you're reading this in your inbox, SMTP sending via your own mailbox works.",
        sender_email=GMAIL_ADDRESS,
        app_password=GMAIL_APP_PASSWORD,
    )

    print(result)
    print(f"Check {SEND_TO}'s inbox, and check {GMAIL_ADDRESS}'s Sent folder.")

if __name__ == "__main__":
    main()