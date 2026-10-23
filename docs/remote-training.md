# Remote V100 training workspace

Validated 2026-10-23 over SSH at `prompter@10.12.0.10`. The dedicated checkout is
`/home/prompter/yt2slp`. SSH uses the existing key without forwarding credentials.
In the restricted local execution environment, `ssh -F /dev/null` bypasses a
system SSH configuration ownership error; normal host SSH configuration was not
edited. No interactive action or extra system RAM is needed for this pilot.

## Inspected hardware and isolated environment

| Item | Measured configuration |
| --- | --- |
| Host | Ubuntu 26.04.1 LTS, x86-64 |
| Training GPU | Tesla PG500-216, compute capability 7.0, 32,768 MiB reported VRAM |
| GPU selection | Physical index 1; GPU UUID `GPU-ce8ddd39-0bf5-1021-dbe2-221ddcb9ece5` |
| Other GPU | GT 1030 at index 0; the Docker helper selects one explicit device |
| NVIDIA driver | 580.178.04 |
| Host memory | About 30 GiB usable RAM plus 8 GiB swap |
| Disk | About 707 GiB free after installation, versus 722 GiB before setup |
| Container | Existing project Debian 13 / GCC 14 image, Python 3.13.5 |
| Optional ML environment | `.docker-state/local/learning-cu126` on host; `/work/.local/learning-cu126` in Docker |
| Framework | PyTorch 2.10.0+cu126, torchvision 0.25.0+cu126, CUDA 12.6, cuDNN 9.10.2 |

The host's Python 3.14, driver and Docker daemon were not replaced. The image
build installs its own tools; ML packages live in a separate ignored virtual
environment. Game rendering/ISO work remains on the Arch workstation for now;
the remote checkout has not built the asset-backed native engine or validated
official Playback. The existing prepared pilot images/labels and public encoder
weights were copied over SSH; no ISO or credentials were transferred.

The CUDA package lock is
[`tools/learning/requirements-cu126.lock`](../tools/learning/requirements-cu126.lock).
Choose this build deliberately: PyTorch documents that some newer CUDA binaries
[drop Volta support](https://dev-discuss.pytorch.org/t/dropping-volta-support-from-cuda-12-8-binaries-for-release-2-11/3290).
Actual GPU execution is the acceptance gate, rather than a package installation
or `torch.cuda.is_available()` result alone.

## Existing containers

At the user's explicit request, the running `llama-v100` container was stopped
and restart policies were set to `no` for it and the already-stopped
`open-webui` and `llama-ollama-1` containers. Their containers/data/configuration
were retained. Prior states are recorded remotely in
`.docker-state/local/remote-setup-v1/previous-containers.txt`.

The V100's reported free memory increased from 8,471 MiB to **32,495 MiB**.
These containers will not restart solely because Docker or the server restarts;
an explicit future `docker compose up` or service command can still start them.
No matching LLM systemd service was found in the inspected system/user unit lists.

## Reproduce setup and GPU validation

Connect from the workstation:

```bash
ssh -F /dev/null -o BatchMode=yes prompter@10.12.0.10
```

On the remote host, from the dedicated checkout:

```bash
cd /home/prompter/yt2slp
bash scripts/docker.sh build
export YT2SLP_GPU=GPU-ce8ddd39-0bf5-1021-dbe2-221ddcb9ece5
bash scripts/docker.sh run uv venv --python python3.13 .local/learning-cu126
bash scripts/docker.sh run uv pip sync \
  --python .local/learning-cu126/bin/python tools/learning/requirements-cu126.lock \
  --index-url https://download.pytorch.org/whl/cu126
bash scripts/docker.sh run uv pip install \
  --python .local/learning-cu126/bin/python --no-deps --editable .
bash scripts/docker.sh run npm ci --prefix tools/slippi-parser --ignore-scripts

bash scripts/docker.sh run mkdir -p .local/remote-check-NEW
bash scripts/docker.sh run .local/learning-cu126/bin/python \
  tools/learning/check_gpu.py --expected-capability 7.0 \
  --output .local/remote-check-NEW/gpu-readiness.json
bash scripts/docker.sh run .local/learning-cu126/bin/python tools/learning/test_baseline.py

bash scripts/docker.sh run env TORCH_HOME=/work/.cache/torch \
  .local/learning-cu126/bin/python tools/learning/train_smoke.py \
  --pairs .local/learning-pilot-v1/pairs/pairs.json \
  --output .local/remote-check-NEW/smoke --steps 100 --device cuda \
  --gpu-memory-fraction 0.5
```

Omit the venv-creation step when reusing an existing environment. Output report
and run directories must be new. `YT2SLP_GPU` accepts a single numeric GPU index
or NVIDIA GPU UUID. Omission keeps the normal CPU-only Docker behavior; `all`
and comma-separated selections are rejected. Explicit `--device cuda` fails
if CUDA is unavailable, with no silent CPU fallback. Feature extraction and
temporal training both run on the selected GPU; evaluation uses minibatches
and retains full clip tensors on CPU to bound GPU usage.

## Measured readiness and limits

Readiness passed real CUDA matrix multiplication, convolution and GRU forward/
backward checks with finite gradients. The installed wheel reports compiled
`sm_70` support. Six optional model tests pass in the remote CUDA environment.
Local Docker validation also passes 365 Python tests, including seven checks for
explicit GPU argument transport; the CPU training regression still passes.
The remote parser suite passes 15 tests. Re-exporting the original supervised
labels and rebuilding the pairs on the server produce byte-identical SHA-256
identities to the workstation artifacts, including pair manifest `e4ba980f…`.

The same 180-image / 150-window provisional training clip completed 100 GPU
optimizer updates with seed 1 and batch size 8:

- Encoder extraction: **2.46 seconds**.
- Temporal training loop: **1.10 seconds** (about 90.5 updates/second).
- PyTorch allocator peak: **174.7 MiB allocated / 204 MiB reserved**, excluding
  CUDA context/driver allocations and other processes.
- Training loss: **10.51475 → 1.83516**; button hold/press/release F1 remains
  **0.374 / 0.048 / 0.043**.

These are a tiny cached-feature pilot's timings, not full-model throughput or
accuracy estimates. CPU/CUDA floating-point outputs need not match exactly; game
timing/math is separate and unchanged. Training still uses provisional image/
post phase, excludes the initial pre-clock compound opening from its images,
and has no held-out evaluation or learned replay output.

Ignored remote evidence is under `.docker-state/local/remote-setup-v1/`:
`image-build.log`, `environment.log`, `gpu-readiness.json`, `smoke.log` and
`smoke/result.json`, plus parser install/test logs and the rebuilt labels/pairs.
Readiness/result JSONs are also retained in the workstation's
ignored directory of the same name. The transferred pilot remains under
`.docker-state/local/learning-pilot-v1/` and `example-reference-v1/video/`.

The current 32 GB system RAM is sufficient for the exercised pilot. Before
scaling whole matches, use bounded/chunked feature loading and measure peak RAM;
more DDR4 is an option if that later workload demonstrates pressure. Hardware
and storage access are now available; image/input timing, pre-clock labels,
event learning and held-out evaluation are the next development work.
