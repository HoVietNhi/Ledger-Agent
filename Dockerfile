FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/my_agent

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

CMD ["adk", "api_server", "--host", "0.0.0.0", "--port", "8080", "/app"]