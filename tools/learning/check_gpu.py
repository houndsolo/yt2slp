"""Require real CUDA forward/backward execution, including cuDNN convolution/GRU."""
import argparse
import json
from pathlib import Path

import torch
from torch import nn


def check_gpu(expected_capability=None):
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable; readiness requires actual GPU execution')
    capability = torch.cuda.get_device_capability(0)
    if expected_capability and capability != expected_capability:
        raise RuntimeError(f'wrong GPU selected: expected {expected_capability}, got {capability}')
    torch.cuda.set_per_process_memory_fraction(.2)
    torch.manual_seed(1)
    torch.cuda.reset_peak_memory_stats()
    matrix = torch.randn(512, 512, device='cuda', requires_grad=True)
    product = matrix @ matrix.T
    product.square().mean().backward()
    convolution = nn.Conv2d(3, 16, 3).cuda()
    conv_output = convolution(torch.randn(2, 3, 64, 64, device='cuda'))
    conv_output.square().mean().backward()
    recurrent = nn.GRU(32, 32, batch_first=True, bidirectional=True).cuda()
    recurrent_output, _ = recurrent(torch.randn(2, 31, 32, device='cuda'))
    recurrent_output.square().mean().backward()
    torch.cuda.synchronize()
    for tensor in (product, matrix.grad, conv_output, recurrent_output,
                   *(p.grad for p in convolution.parameters()), *(p.grad for p in recurrent.parameters())):
        if tensor is None or not torch.isfinite(tensor).all():
            raise RuntimeError('missing/non-finite CUDA result or gradient')
    properties = torch.cuda.get_device_properties(0)
    return {'schema': 1, 'kind': 'cuda-execution-readiness', 'passed': True,
        'torch_version': torch.__version__, 'cuda_version': torch.version.cuda,
        'cudnn_version': torch.backends.cudnn.version(), 'gpu_name': properties.name,
        'capability': list(capability), 'total_memory_bytes': properties.total_memory,
        'compiled_architectures': torch.cuda.get_arch_list(),
        'checks': ['matrix forward/backward', 'convolution forward/backward', 'GRU forward/backward'],
        'peak_cuda_reserved_bytes': torch.cuda.max_memory_reserved()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-capability', help='optional MAJOR.MINOR, e.g. 7.0 for Volta')
    args = parser.parse_args()
    capability = tuple(map(int, args.expected_capability.split('.'))) if args.expected_capability else None
    if args.output.exists():
        parser.error('new report path required')
    result = check_gpu(capability)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
