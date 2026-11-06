FROM python:3.13-alpine

RUN pip install --no-cache-dir pillow==13.0.0 tzdata

COPY server.py render.py /app/
COPY sprites /app/sprites/

WORKDIR /app
CMD ["python", "-u", "/app/server.py"]
