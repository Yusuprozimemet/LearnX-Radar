# Reproducible, no-secret build of the static dashboard + podcast feed.
#
#   docker build -t learnx-radar .
#   docker run --rm -v "$PWD/dashboard:/app/dashboard" learnx-radar
#
# This rebuilds dashboard/index.html + podcast.xml from committed JSON state,
# exactly as the GitHub Pages workflow does — no API keys, no network. The full
# daily pipeline (main.py) additionally needs the secrets in .env; this image
# deliberately demonstrates the path that runs from a clean clone alone.
FROM python:3.12-slim

WORKDIR /app

# Deps first so the layer caches across source edits.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Rebuild the dashboard + feed from committed state. No secrets, no network.
CMD ["python", "-m", "dashboard"]