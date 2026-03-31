FROM python:3.12-slim

WORKDIR /sentinel

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create a non-root user to run the application (CIS Docker Benchmark)
RUN groupadd -r sentinel && useradd -r -g sentinel -u 1001 sentinel

# Install dependencies as root (before switching user)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/

# Hand ownership to the sentinel user
RUN chown -R sentinel:sentinel /sentinel

# Drop privileges
USER sentinel

EXPOSE 8000

# --workers 2: process-level parallelism for concurrent requests
# --loop uvloop: faster async event loop (installed via uvicorn[standard])
# --limit-max-requests 10000: worker recycling to prevent memory leaks
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--limit-max-requests", "10000"]
