FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN playwright install --with-deps
COPY . .

EXPOSE 8000
CMD ["bash", "run.sh"]
