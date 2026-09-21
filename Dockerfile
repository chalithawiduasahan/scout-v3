# ---- Stage 1: Build the React Frontend ----
FROM node:18-alpine AS frontend-builder
WORKDIR /app/project
COPY project/package*.json ./
RUN npm install
COPY project/ ./
RUN npm run build

# ---- Stage 2: Official Playwright Python Image ----
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

WORKDIR /app

# Pin the browsers path explicitly so the build step and the running
# container both agree on where Chromium lives — this is what was
# missing before, causing "Executable doesn't exist" at runtime even
# though the build step appeared to succeed.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Copy and install Python backend dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure Playwright browser binaries are active (--with-deps also makes
# sure the OS-level libraries Chromium needs are present)
RUN playwright install --with-deps chromium

# Copy the rest of the root backend code files
COPY . .

# Copy the compiled React frontend build output from project/dist into /app/static
COPY --from=frontend-builder /app/project/dist /app/static

EXPOSE 8000

CMD playwright install chromium && uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}