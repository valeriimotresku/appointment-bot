# Appointment Bot


> [!IMPORTANT]
> **Educational use only.** This project is provided solely for learning, research, and personal experimentation with FastAPI, Playwright, schedulers, webhooks, deployment, and browser automation. It is not intended for commercial use, abuse of third-party services, bypassing access controls, evading rate limits, gaining unfair priority, or violating any website's terms of service or applicable law.
>
> If you adapt this project, you are responsible for obtaining any required permission, respecting the target service's rules and technical limits, and ensuring that your use is lawful and does not interfere with other users or the service itself.

A FastAPI + Playwright application that monitors appointment availability on FrontDeskSuite and automatically books matching appointments.

The application runs continuously on a server, keeps one Chromium browser session alive, periodically refreshes the FrontDeskSuite date picker, and confirms bookings through a Mailgun email webhook.

## Features

- FastAPI web application
- APScheduler-based appointment monitoring
- Persistent Playwright / Chromium browser session
- Reuses the same FrontDeskSuite date picker page between checks
- Automatically recovers the browser/session if navigation is lost
- Checks availability once per scheduler cycle
- Supports multiple active `WatchRequest` entries
- Automatically books matching appointments
- Confirmation codes are received through Mailgun webhook
- Mailgun webhook is protected with HMAC-SHA256 signature verification
- Telegram notification after successful booking
- Existing bookings can remain active and continue searching for earlier dates
- HTTP Basic Authentication protects the UI and management API
- Designed to run behind nginx + HTTPS

## Architecture

```text
                         Internet
                            |
                            v
                  https://subdomain.duckdns.org
                            |
                            v
                          nginx
                            |
                            v
                 FastAPI / Uvicorn :8000
                    |           |
                    |           |
                    |           +-------------------+
                    |                               |
                    v                               v
               APScheduler                    Mailgun webhook
                    |                               |
                    v                               |
              FrontDeskClient                       |
                    |                               |
                    v                               |
              Playwright Page                       |
                    |                               |
                    v                               |
                 Chromium                           |
                    |                               |
                    v                               |
             FrontDeskSuite                         |
                    |                               |
                    +---- confirmation email -------+
                                                    |
                                                    v
                                             confirmation code
                                                    |
                                                    v
                                             asyncio Future
                                                    |
                                                    v
                                              Playwright flow
```

## Scheduler

The scheduler periodically checks the first available appointment date.

The browser is not restarted for every check.

Instead, the application:

```text
Start Chromium once
        |
Navigate to date picker once
        |
        v
Scheduler tick
        |
        v
Reload existing date picker
        |
        v
Read first available date
        |
        v
Compare with active WatchRequests
```

This significantly reduces CPU usage, browser startup overhead, and traffic to FrontDeskSuite.

Scheduler configuration is controlled through environment variables:

```env
CHECK_INTERVAL_SECONDS=20
CHECK_JITTER_SECONDS=3
```

Example:

```text
20 second interval
+ up to 3 seconds random jitter
```

The jitter prevents requests from being sent at perfectly fixed intervals.

## Booking behavior

A `WatchRequest` contains a requested date range.

If the currently available date matches the range, the application attempts to book it.

If `booked_datetime` is empty:

```text
matching date
→ book appointment
```

If the request already has a confirmed booking:

```text
new available date < existing booked date
→ book the earlier date

new available date == existing booked date
→ skip

new available date > existing booked date
→ skip
```

Time differences on the same date are currently ignored.

The watcher remains active after a successful booking and can therefore continue searching for an earlier appointment.

`booked_datetime` is updated only after the appointment has been successfully confirmed.

If the confirmation email does not arrive or the booking cannot be confirmed:

```text
booked_datetime is NOT changed
```

## Persistent browser

Playwright Chromium is started once when the FastAPI application starts.

The browser stays alive for the lifetime of the application.

Normal availability checks reuse the same `Page`:

```text
page.reload()
→ read date
```

If the FrontDeskSuite session is lost, the application automatically navigates back to the date picker.

If the browser itself becomes unusable, Chromium is restarted.

An `asyncio.Lock` ensures that only one task manipulates the shared Playwright page at a time.

## Email confirmation flow

FrontDeskSuite sends a confirmation email containing a confirmation code.

Incoming email flow:

```text
FrontDeskSuite
      |
      v
   Mailgun
      |
      v
POST /email/incoming
      |
      v
verify Mailgun signature
      |
      v
parse sender / subject / body
      |
      v
extract confirmation code
      |
      v
deliver code to waiting asyncio Future
      |
      v
Playwright continues booking
```

The confirmation waiter is registered before submitting the FrontDeskSuite form to prevent a race condition where the email arrives before the waiter exists.

## Mailgun webhook security

The Mailgun webhook endpoint is intentionally public:

```text
POST /email/incoming
```

It cannot use the UI Basic Authentication because Mailgun must be able to call it automatically.

Instead, every request is verified using Mailgun's webhook signature.

Mailgun sends:

```text
timestamp
token
signature
```

The application calculates:

```text
HMAC-SHA256(
    signing_key,
    timestamp + token
)
```

and compares it to the supplied signature using a constant-time comparison.

Requests are rejected if:

- the signature is invalid
- required Mailgun fields are missing
- the timestamp is too old
- the webhook signing key is not configured

The maximum accepted timestamp age is currently 5 minutes.

This protects the public endpoint from arbitrary forged requests.

## UI authentication

The UI and management endpoints are protected using HTTP Basic Authentication.

Protected endpoints include:

```text
/
/watch/*
/status/*
```

Static files remain public.

The Mailgun webhook remains publicly reachable but is protected by Mailgun signature verification.

Swagger/OpenAPI endpoints are disabled on the deployed application.

## Environment variables

Create a `.env` file in the project root.

Example:

```env
# Scheduler
CHECK_INTERVAL_SECONDS=20
CHECK_JITTER_SECONDS=3

# Admin UI
ADMIN_USERNAME=valerii
ADMIN_PASSWORD=use-a-long-random-password

# Mailgun webhook security
MAILGUN_WEBHOOK_SIGNING_KEY=your-mailgun-webhook-signing-key

# Telegram
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-chat-id

# Database
DATABASE_URL=sqlite:///./app.db
```

`DATABASE_URL` is optional if the application already defaults to SQLite.

Never commit `.env` to Git.

Make sure `.env` is included in `.gitignore`.

## Installation

Clone the repository:

```bash
git clone git@github.com:valeriimotresku/appointment-bot.git
cd appointment-bot
```

Create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Install Chromium and Playwright system dependencies:

```bash
python -m playwright install --with-deps chromium
```

## Running locally

Activate the virtual environment:

```powershell
.\venv\Scripts\Activate.ps1
```

Run:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On Windows, avoid `--reload` when testing the persistent Playwright browser.

Playwright requires an asyncio event loop capable of launching subprocesses, and Uvicorn reload mode can cause problems with the Windows event loop implementation.

## Production server

The application is deployed on Ubuntu and runs as a systemd service.

Example service:

```ini
[Unit]
Description=Appointment Bot FastAPI Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/termin-appointment-app
EnvironmentFile=/home/ubuntu/termin-appointment-app/.env

ExecStart=/home/ubuntu/termin-appointment-app/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Reload systemd after changing the service:

```bash
sudo systemctl daemon-reload
```

Enable automatic startup:

```bash
sudo systemctl enable appointment-bot
```

Restart:

```bash
sudo systemctl restart appointment-bot
```

Check status:

```bash
sudo systemctl status appointment-bot
```

## Live logs

Follow application logs:

```bash
journalctl -u appointment-bot -n 100 -f
```

Exit live logs with:

```text
Ctrl+C
```

Show recent logs without following:

```bash
journalctl -u appointment-bot -n 100 --no-pager
```

## nginx

nginx acts as a reverse proxy.

Example:

```nginx
server {
    server_name terminbot.duckdns.org;

    location / {
        proxy_pass http://127.0.0.1:8000;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

HTTPS is provided using Let's Encrypt / Certbot.

Production URL:

```text
https://terminbot.duckdns.org
```

Mailgun webhook:

```text
https://terminbot.duckdns.org/email/incoming
```

## Firewall

Publicly exposed ports:

```text
22   SSH
80   HTTP / Let's Encrypt
443  HTTPS
```

Uvicorn listens only on:

```text
127.0.0.1:8000
```

Port `8000` should not be publicly exposed.

## Deployment

The normal deployment flow is:

```text
local changes
    |
git commit
    |
git push
    |
Oracle server
    |
git pull
    |
pip install -r requirements.txt
    |
restart systemd service
```

Example server commands:

```bash
cd ~/termin-appointment-app
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart appointment-bot
sudo systemctl status appointment-bot --no-pager
```

## Resource usage

The application is designed to reuse a single Chromium instance.

Typical server resource usage observed with FastAPI + scheduler + persistent Chromium is relatively small compared with a 4 GB VM.

Use:

```bash
htop
```

or:

```bash
systemd-cgtop
```

to monitor resource usage.

For systemd-specific statistics:

```bash
systemctl show appointment-bot \
    -p MemoryCurrent \
    -p MemoryPeak \
    -p CPUUsageNSec
```


## Educational use and responsibility

This repository is an educational demonstration of browser automation and backend integration. It is intended to illustrate concepts such as Playwright automation, asynchronous workflows, webhook verification, scheduling, authentication, and server deployment.

The code is not provided as a general-purpose appointment-grabbing service and should not be used to circumvent booking rules, access restrictions, rate limits, anti-bot measures, or other safeguards. Before running it against any third-party service, review that service's terms and obtain permission where required.

The author assumes no responsibility for misuse of the software or for consequences resulting from use that violates third-party rules or applicable law.

## Security notes

Do not commit:

```text
.env
SSH private keys
Mailgun keys
Telegram tokens
SMTP credentials
API keys
```

The UI is protected with Basic Auth over HTTPS.

The Mailgun endpoint is protected through HMAC signature verification.

All public traffic should go through nginx over HTTPS.

The internal Uvicorn port should remain bound to localhost only.
