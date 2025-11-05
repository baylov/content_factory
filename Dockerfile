# Use slim Python base for smaller image
FROM python:3.11-slim

# Set non-root user for security
RUN groupadd -r upbot && useradd -r -g upbot upbot

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome for HTML fallback mode
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs && \
    touch last_notice.txt && \
    chmod +x main.py

# Set ownership to non-root user
RUN chown -R upbot:upbot /app

# Switch to non-root user
USER upbot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "
import requests
try:
    r = requests.get('https://api-manager.upbit.com/v1/notices?page=1&per_page=1', timeout=5)
    exit(0 if r.status_code == 200 else 1)
except:
    exit(1)
" || \
    python3 -c "
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
try:
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    driver.get('https://upbit.com/service_center/notice')
    driver.quit()
    exit(0)
except:
    exit(1)
"

# Default command (API mode by default)
CMD ["python", "main.py", "--api"]

# Labels for metadata
LABEL maintainer="your-email@example.com"
LABEL version="3.1.0"
LABEL description="Upbit Notice Bot - Automated monitoring with API-first approach and auto-fallback"
