FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     wget     gnupg     unzip     curl     ca-certificates     fonts-liberation     libnss3     libatk-bridge2.0-0     libxss1     libasound2     libgbm1     libgtk-3-0     libx11-xcb1     libxcomposite1     libxdamage1     libxrandr2     xdg-utils     sqlite3     && rm -rf /var/lib/apt/lists/*

RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google.gpg &&     echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main"     > /etc/apt/sources.list.d/google-chrome.list &&     apt-get update && apt-get install -y --no-install-recommends google-chrome-stable &&     rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000 8501

CMD ["bash", "-lc", "echo 'Use docker-compose for api/ui or run python run.py manually inside container' && tail -f /dev/null"]
