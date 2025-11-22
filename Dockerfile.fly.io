FROM python:3.11-slim

# 1. Install OS dependencies for Playwright Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxrandr2 \
    libxdamage1 \
    libxfixes3 \
    libxext6 \
    libxshmfence1 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libx11-xcb1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Python dependencies
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 3. Install Playwright browsers (Chromium only)
RUN playwright install --with-deps chromium

# 4. Copy project
COPY . /app

# 5. Expose FastAPI port
EXPOSE 8080

# 6. Start app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
