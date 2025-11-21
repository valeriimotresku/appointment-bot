import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os

load_dotenv()

SMTP_HOST = os.getenv('SMTP_HOST')
SMTP_PORT = int(os.getenv('SMTP_PORT'))
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')
EMAIL_FROM = os.getenv('EMAIL_FROM')

def notify_success(to, date):
    msg = MIMEText(f'Appointment booked on: {date}')
    msg['Subject'] = 'Appointment Confirmed'
    msg['From'] = EMAIL_FROM
    msg['To'] = to

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(EMAIL_FROM, [to], msg.as_string())
    print('Email sent successfully!')

