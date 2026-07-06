FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY echo_agent/agent.py ./agent.py

EXPOSE 9000-9999

CMD ["python", "agent.py"]
