# syntax=docker/dockerfile:1
FROM debian:13-slim

# Optional public proxy CA for managed cloud builds; never baked into the image.
RUN --mount=type=secret,id=proxy_ca \
    set -eu; \
    if [ -f /run/secrets/proxy_ca ]; then \
      export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca; \
      printf 'Acquire::https::CaInfo "/run/secrets/proxy_ca";\n' > /etc/apt/apt.conf.d/99-build-ca; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates git gcc-14 g++-14 binutils make python3 python3-venv nodejs npm ffmpeg; \
    python3 -m venv /opt/tools; \
    /opt/tools/bin/pip install --no-cache-dir uv==0.12.23; \
    rm -f /etc/apt/apt.conf.d/99-build-ca; \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/work/.venv/bin:/opt/tools/bin:${PATH}" \
    CC=gcc-14 CXX=g++-14 \
    UV_PYTHON=python3.13 UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/work/.cache/uv \
    HOME=/tmp
WORKDIR /work
CMD ["bash", "--noprofile", "--norc"]
