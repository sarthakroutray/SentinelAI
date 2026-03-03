import requests
from datetime import datetime

for i in range(12):
    requests.post("http://localhost:8000/logs", json={
    "source": "stress-test",
    "log_level": "INFO",
    "message": f"user session heartbeat {i}",
    "timestamp": datetime.utcnow().isoformat(),
    "ip_address": "192.168.1.100"
})