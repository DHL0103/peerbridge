FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-libmysqlclient-dev build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    Django==4.2.30 \
    djangorestframework==3.16.1 \
    djangorestframework-simplejwt==5.5.1 \
    drf-spectacular==0.27.2 \
    django-cors-headers==4.9.0 \
    mysqlclient==2.2.4 \
    python-dotenv==1.2.1

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000"]
