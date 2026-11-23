# The toolchain image: the CARLA 0.9.16 server, and a Python 3.10 that has the
# CARLA client and pyotter's one dependency. pyotter itself is not in the image:
# it is imported from the checkout that runs it, so the image changes only when
# CARLA or the client does.
#
# Build from this folder:
#   docker build --platform linux/amd64 -t carla-toolchain .
#
# The client wheel needs glibc 2.31, which this image's Ubuntu 20.04 has and
# CARC Discovery's own system does not. That is why the client runs in here.

ARG BASE=carlasim/carla:0.9.16
FROM ghcr.io/astral-sh/uv:0.6.6 AS uv
FROM ${BASE}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libjpeg-turbo8 libtiff5 libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/otter/python
RUN uv venv --python 3.10 /opt/otter/venv \
    && uv pip install --python /opt/otter/venv/bin/python --no-cache "carla==0.9.16" "PyYAML>=6.0" \
    && /opt/otter/venv/bin/python -c "import carla, yaml" \
    && chmod -R a+rX /opt/otter

COPY --chmod=755 carla-server /usr/local/bin/carla-server
ENV PATH=/opt/otter/venv/bin:$PATH

USER carla
CMD ["carla-server"]
