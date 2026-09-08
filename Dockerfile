FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .
COPY abex ./abex

# config.json and .env are mounted at run time so secrets stay out of the image.
VOLUME ["/app/data"]

CMD ["python", "bot.py"]
