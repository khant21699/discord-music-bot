FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsodium-dev \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir "discord.py[voice]==2.3.2" "PyNaCl==1.5.0" yt-dlp

COPY . .

CMD ["python", "bot.py"]