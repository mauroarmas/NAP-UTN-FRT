FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary bcrypt==4.1.3

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .
COPY backend/scripts ./scripts
COPY .env ./../.env

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]