FROM python:3.12-slim

# nmap and snmpwalk are called as subprocesses — install the system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
        nmap \
        snmp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY frontend/ ./frontend/

# 8000  — FastAPI / dashboard
# 514   — syslog UDP (requires host networking or NET_BIND_SERVICE cap)
EXPOSE 8000
EXPOSE 5140/udp

CMD ["python3", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
