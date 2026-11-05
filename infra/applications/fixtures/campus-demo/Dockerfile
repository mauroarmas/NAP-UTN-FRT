FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NAP_DEMO_DATA=/data
RUN groupadd --gid 10001 campus && useradd --uid 10001 --gid campus --no-log-init campus \
    && mkdir /app /data && chown campus:campus /app /data
COPY --chown=10001:10001 app.py /app/app.py
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python", "/app/app.py"]
