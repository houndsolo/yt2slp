#!/usr/bin/env bash
# Bind source but isolate compiler caches, venv and outputs from host builds.
set -euo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
image="yt2slp-dev:gcc14"
action="${1:-shell}"
if [ "$#" -gt 0 ]; then shift; fi
case "$action" in
  build)
    # Keep Buildx state writable in managed workspaces without replacing Docker
    # configuration or registry credentials.
    export BUILDX_CONFIG="${BUILDX_CONFIG:-$root/.docker-state/buildx}"
    build_args=()
    if [ -n "${CODEX_PROXY_CERT:-}" ]; then
      build_args+=(--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt)
    fi
    # Only docker/ is sent as context; never send the ISO or the project build tree.
    exec docker build "${build_args[@]}" -t "$image" "$root/docker"
    ;;
  setup|shell|run) ;;
  *) echo "usage: bash scripts/docker.sh {build|setup|shell|run COMMAND...}" >&2; exit 2 ;;
esac
mkdir -p .docker-state/{venv,build,cache,local}
args=(run --rm --init --user "$(id -u):$(id -g)"
  --mount "type=bind,src=$root,dst=/work"
  --mount "type=bind,src=$root/.docker-state/venv,dst=/work/.venv"
  --mount "type=bind,src=$root/.docker-state/build,dst=/work/build"
  --mount "type=bind,src=$root/.docker-state/cache,dst=/work/.cache"
  --mount "type=bind,src=$root/.docker-state/local,dst=/work/.local"
  -e "YT2SLP_JOBS=${YT2SLP_JOBS:-4}")
if [ -n "${YT2SLP_GPU:-}" ]; then
  if [[ ! "$YT2SLP_GPU" =~ ^[0-9]+$ && ! "$YT2SLP_GPU" =~ ^GPU-[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]]; then
    echo "yt2slp: YT2SLP_GPU must select one numeric GPU index or NVIDIA GPU UUID" >&2; exit 2
  fi
  args+=(--gpus "device=$YT2SLP_GPU" -e NVIDIA_DRIVER_CAPABILITIES=compute,utility)
fi
if [ -n "${YT2SLP_ISO:-}" ]; then
  if [ ! -f "$YT2SLP_ISO" ]; then
    echo "yt2slp: YT2SLP_ISO must name an existing host file" >&2; exit 1
  fi
  iso=$(realpath "$YT2SLP_ISO")
  args+=(--mount "type=bind,src=$iso,dst=/assets/melee.iso,readonly" -e YT2SLP_ISO=/assets/melee.iso)
fi
if [ -n "${CODEX_PROXY_CERT:-}" ]; then
  args+=(--mount type=bind,src=/etc/ssl/certs/ca-certificates.crt,dst=/run/proxy-ca.pem,readonly
    -e SSL_CERT_FILE=/run/proxy-ca.pem -e GIT_SSL_CAINFO=/run/proxy-ca.pem)
fi
case "$action" in
  setup) command=(bash -c 'bash scripts/setup.sh && bash scripts/build_game.sh') ;;
  shell)
    args+=(-i)
    if [ -t 0 ]; then args+=(-t); fi
    command=(bash --noprofile --norc)
    ;;
  run)
    if [ "$#" -eq 0 ]; then echo "run requires a command" >&2; exit 2; fi
    command=("$@")
    ;;
esac
exec docker "${args[@]}" "$image" "${command[@]}"
