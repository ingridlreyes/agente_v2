FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY governance_studio ./governance_studio
RUN python -m pip install --no-cache-dir '.[azure]' && useradd --create-home studio && mkdir /data && chown studio:studio /data
USER studio
ENV GS_MODE=azure GS_HOST=0.0.0.0 GS_PORT=8080 GS_DATA_DIR=/data
EXPOSE 8080
CMD ["python", "-m", "governance_studio", "serve"]
