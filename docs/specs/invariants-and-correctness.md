---
title: Invariants and Correctness
status: current spec
audience: implementers
---

# Invariants and Correctness

## 13. Runtime Alphabet

The runtime alphabet contains:

- layout markers
- field markers
- tape-cell markers
- bits `0` and `1`
- active marker variants such as `#ACTIVE_RULE`
- the runtime blank symbol

Cycle-boundary invariants:

```text
no active markers remain
exactly one encoded simulated tape cell carries `#HEAD` across both left and right simulated tape regions
```

## 14. Correctness Targets

### 14.1 Object Compiler

For a source instance `I`:

```text
decode(Compiler.compile(I).to_band_artifact()) = initial semantic UTM state for I
```

### 14.2 Meta-ASM Interpreter

For one interpreter cycle:

```text
if cur_state == halt_state: host halts without a simulated step
elif a matching source rule exists: one Meta-ASM cycle = one source TM step
else: host enters STUCK
```

### 14.3 Lowering

For each Meta-ASM instruction:

```text
lowered transition fragment implements the instruction contract
```

For the full interpreter:

```text
Program.lower(alphabet, ...) preserves Meta-ASM behavior at label boundaries
```

### 14.4 End-to-End

For source machine `M` and configuration `C`:

```text
if C.state == M.halt_state:
  host halts without changing the simulated source tape
elif a matching rule exists at C:
  Encode(C) --object.l1.tm*--> Encode(step_M(C))
else:
  host enters STUCK
```

The run continues until halt, stuck, or fuel exhaustion.
