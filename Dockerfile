FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p logs reports data

EXPOSE 1999

CMD ["python", "app.py"]
