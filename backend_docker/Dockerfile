FROM python:3.11-slim

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser

WORKDIR /app

# Install build deps only where needed
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . /app

# Ensure ownership
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
