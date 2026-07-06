FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY control_plane ./control_plane

EXPOSE 7000

CMD ["python", "-m", "control_plane.main"]
