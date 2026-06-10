FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
ENV REVOLUT_DATA_DIR=/data
EXPOSE 8081
CMD ["python", "-m", "src.cli", "web", "--host", "0.0.0.0", "--port", "8081"]
