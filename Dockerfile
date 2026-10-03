FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Por defecto, el microservicio FastAPI. La consola: `python main.py` (ver docker-compose.yml).
CMD ["uvicorn", "betito_bot.api:app", "--host", "0.0.0.0", "--port", "8000"]
