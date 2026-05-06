---
title: C Runners
description: Experimental C runner generators and performance-oriented raw execution tools.
status: experimental
audience: engineer
---

# C Runners

These tools are the existing C runner and generator programs in `tools/`.

They are experimental performance tools used to study raw execution throughput
and runner behavior. They are not the canonical execution path.

## Generators

- `tools/generate_l1_raw_guest_data.py`
- `tools/generate_l2_meta_asm_data.py`
- `tools/generate_raw_tm_runner_data.py`
- `tools/generate_raw_tm_c.py`

## Runners

- `tools/l1_raw_guest_runner.c`
- `tools/l2_meta_asm_runner.c`
- `tools/raw_tm_runner.c`

The generator scripts build header data for the C runners or emit
self-contained C sources for specific artifact shapes.

The runner variants correspond to the measurements discussed in
[L2 Bootstrap Results](../results/l2-bootstrap.md).

For the reproducible command sequence that feeds these experiments, see the
[L2 Incrementer Runbook](../runbooks/l2-incrementer.md).

