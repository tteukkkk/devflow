FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -r -u 10001 devflow && mkdir -p /data && chown devflow:devflow /data
USER devflow
EXPOSE 8010
CMD ["uvicorn", "devflow.app:app", "--host", "0.0.0.0", "--port", "8010"]
