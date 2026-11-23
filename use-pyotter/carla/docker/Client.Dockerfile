# The pyotter client: Python, the CARLA client library, and pyotter. Build from the repo root:
#   docker build -f use-pyotter/carla/docker/Client.Dockerfile -t otter-client .
FROM python:3.10-slim

RUN pip install --no-cache-dir carla==0.9.16
WORKDIR /otter
COPY pyproject.toml ./
COPY pyotter ./pyotter
RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "pyotter"]
