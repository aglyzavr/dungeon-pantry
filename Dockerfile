FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY ./app ./app

COPY alembic.ini .
COPY ./alembic ./alembic

EXPOSE 8080

# copy the startup script and make sure it's executable
COPY start.sh .
RUN chmod +x start.sh

# run as a non-root user to limit blast radius of a container escape
RUN useradd -m appuser
USER appuser

# use the script as the container entrypoint so migrations run on boot
CMD ["./start.sh"]
