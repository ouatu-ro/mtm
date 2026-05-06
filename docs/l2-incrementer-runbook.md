# L2 Incrementer Runbook

This note captures the concrete path from `examples/incrementer_tm.py` to L2,
plus the current size and runtime expectations for proving `1011 -> 1100`.

## Build L1 and L2 Artifacts

```bash
out=/tmp/mtm-incrementer-l2
rm -rf "$out"

uv run mtm l1 examples/incrementer_tm.py \
  --out-dir "$out" \
  --stem incrementer

uv run mtm l2 \
  "$out/incrementer.l1.tm" \
  "$out/incrementer.l1.utm.band" \
  --out-dir "$out" \
  --stem incrementer
```

Expected artifacts:

```text
incrementer.mtm.source
incrementer.l1.tm
incrementer.l1.utm.band
incrementer.l2.tm
incrementer.l2.utm.band
```

## Validate L1

The L1 raw UTM currently completes the incrementer:

```bash
uv run mtm run \
  "$out/incrementer.l1.tm" \
  "$out/incrementer.l1.utm.band" \
  --max-steps 1000000
```

Measured result:

```text
FINAL STATUS: halted
FINAL STATE: U_HALT
STEPS: 35600
FINAL TAPE: 1 1 0 0 _ _ _ _
```

So L1 proves the source input `1011____` becomes `1100____`.

## What L2 Represents

L2 is not a second copy of the source incrementer. It is the universal machine
interpreting the L1 raw machine.

```text
source incrementer
  -> L1 UTM artifacts
  -> L1 raw transition program plus L1 raw runtime tape
  -> encoded as the guest program and guest tape inside L2
```

For the current incrementer:

```text
L1 raw transitions          8,590
L1 raw steps to halt       35,600

L2 encoded rules            8,590
L2 raw transitions         33,039
L2 band tokens            362,442
L2 .utm.band size       2,520,040 bytes
L2 .tm size             4,645,570 bytes

MetaASM blocks                 13
MetaASM static instructions    33
```

The 33 MetaASM instructions are the static universal interpreter. At L2 they
loop over the 8,590 encoded L1 raw transitions for every simulated L1 raw step.

## MetaASM Runtime Estimate

The current MetaASM host can now run L2 with a simulated head on either side of
the split tape. A bounded run no longer fails on the initial negative head.

A trace-derived estimate for the full L2 incrementer is:

```text
simulated L1 raw steps              35,600
estimated L2 MetaASM instructions  634,438,903
average MetaASM instructions/step       17,821
```

Measured host speed on the current L2 band:

```text
100,000 MetaASM instructions ~= 14.25 seconds
```

That gives a rough full-run estimate:

```text
634,438,903 / 100,000 * 14.25s ~= 90,000s ~= 25 hours
```

This is a ballpark estimate, not a promise. The host still performs honest rule
lookup over the large encoded L1 raw transition table.

## Real L2 Raw TM Estimate

The emitted L2 raw TM is much more expensive. The expensive benchmark currently
shows:

```bash
uv run python benchmarks/raw_transition_optimization.py \
  --expensive \
  --l2-source-steps 1
```

Measured baseline:

```text
1 lowered MetaASM instruction ~= 2,245,707 raw L2 steps
```

Combining that with the MetaASM instruction estimate:

```text
634,438,903 * 2,245,707 ~= 1.4e15 raw L2 steps
```

At the current Python raw runner speed, this is not a practical local run. It
is on the order of decades, not hours. The real L2 TM is the semantic artifact;
the MetaASM host is the practical way to try to close the full `1011 -> 1100`
end-to-end check without new optimization work.

## Fast L1 Raw Guest C Check

For a quick check of the guest computation encoded by L2, generate a C data
header from the L1 artifacts and compile the fixed-array runner:

```bash
uv run python tools/generate_l1_raw_guest_data.py \
  "$out/incrementer.l1.tm" \
  "$out/incrementer.l1.utm.band" \
  -o "$out/l1_raw_guest_data.h"

cc -O3 -std=c11 \
  -I "$out" \
  tools/l1_raw_guest_runner.c \
  -o "$out/l1_raw_guest_runner"

"$out/l1_raw_guest_runner"
```

Current measured output:

```text
status=halted steps=35600 raw_head=-135
```

The dumped nonnegative raw band begins with the encoded cells for `1 1 0 0`.
This is intentionally not the full L2 proof: it runs the L1 raw guest directly
in C. It is useful as a fast sanity check before spending time on the L2
MetaASM path.

## Fast L2 MetaASM C Check

To run the actual L2 band through the universal MetaASM algorithm using fixed C
arrays, generate a header from the L2 band and compile the runner:

```bash
uv run python tools/generate_l2_meta_asm_data.py \
  "$out/incrementer.l2.utm.band" \
  -o "$out/l2_meta_asm_data.h"

cc -O3 -std=c11 \
  -I "$out" \
  tools/l2_meta_asm_runner.c \
  -o "$out/l2_meta_asm_runner"
```

One million MetaASM instructions:

```bash
"$out/l2_meta_asm_runner" 1000000
```

Measured result:

```text
status=fuel_exhausted meta_steps=1000000 guest_steps=352
```

Full L2 MetaASM run with a high cap:

```bash
"$out/l2_meta_asm_runner" 800000000
```

Measured result:

```text
status=halted meta_steps=634438903 guest_steps=35600
```

With `cc -O3`, this currently takes about one second on the local machine. The
final right simulated raw band starts:

```text
#TAPE #CELL #HEAD 1 0 #END_CELL
#CELL #NO_HEAD 1 0 #END_CELL
#CELL #NO_HEAD 0 1 #END_CELL
#CELL #NO_HEAD 0 1 #END_CELL
```

Those L1 symbol bits decode as `1 1 0 0`, so this is the fast end-to-end L2
MetaASM proof for the incrementer. It is still not the fully lowered L2 raw TM
run; it is the universal MetaASM semantics over the L2 `.utm.band`.

## Fast Raw TM C Runner

For bounded runs of the actual lowered raw transition table, generate dense C
dispatch data for a `.tm`/`.utm.band` pair and compile the generic runner:

```bash
uv run python tools/generate_raw_tm_runner_data.py \
  "$out/incrementer.l2.tm" \
  "$out/incrementer.l1.utm.band" \
  -o "$out/raw_tm_runner_data.h" \
  --right-dump-cells 8 \
  --raw-dump-cells 48

cc -O3 -std=c11 \
  -I "$out" \
  tools/raw_tm_runner.c \
  -o "$out/raw_tm_runner"

"$out/raw_tm_runner" 1000000
```

That cross-level run uses the wider L2 UTM raw host against the narrower L1
band. Current measured output:

```text
status=halted steps=54915 ... state=U_HALT
decoded_right: 1 1 0 0 _ _ _ _
```

So the real lowered wider host also accepts the smaller band.

For a bounded slice of the expensive real L2 raw run:

```bash
uv run python tools/generate_raw_tm_runner_data.py \
  "$out/incrementer.l2.tm" \
  "$out/incrementer.l2.utm.band" \
  -o "$out/raw_tm_runner_data.h" \
  --right-dump-cells 8

cc -O3 -std=c11 \
  -I "$out" \
  tools/raw_tm_runner.c \
  -o "$out/raw_tm_runner"

"$out/raw_tm_runner" 1000000000
```

Current measured slice:

```text
status=fuel_exhausted steps=1000000000 ... msteps_per_s=941.659
decoded_right: #TAPE #CELL #HEAD 1 0 #END_CELL #CELL #NO_HEAD
```

Combining that measured speed with the current raw-step estimate:

```text
634,438,903 MetaASM instructions * 2,245,707 raw L2 steps/instruction
  = 1,424,763,885,539,421 raw L2 steps

1.424e15 raw steps / 941.659e6 raw steps/sec
  ~= 1,513,036 sec
  ~= 420 hours
  ~= 17.5 days
```

This still does not make a full lowered L2 raw run small; it changes the local
estimate from "decades in Python" to "weeks in C" and makes honest slices cheap
enough to measure.

## Self-Contained Raw C Backends

`tools/generate_raw_tm_c.py` emits a standalone C file for a `.tm`/`.utm.band`
pair. It has two backends:

```bash
uv run python tools/generate_raw_tm_c.py \
  "$out/incrementer.l2.tm" \
  "$out/incrementer.l1.utm.band" \
  -o "$out/packed_l2host_l1band.c" \
  --backend packed-array \
  --right-dump-cells 8 \
  --raw-dump-cells 48

cc -O3 -std=c11 \
  "$out/packed_l2host_l1band.c" \
  -o "$out/packed_l2host_l1band"

"$out/packed_l2host_l1band" 1000000
```

Current packed-array cross-ABI result:

```text
backend=packed-array status=halted steps=54915 ... state=U_HALT
decoded_right: 1 1 0 0 _ _ _ _
```

Current packed-array real L2 bounded slice:

```text
backend=packed-array status=fuel_exhausted steps=1000000000 ...
msteps_per_s=451.802
```

This packed standalone form is portable C11, but it is currently slower than the
header-based dense runner. The bit packing removes table columns but adds decode
work on the hot path.

The computed-goto backend emits one label per valid transition and dispatches
with Clang/GNU C label pointers:

```bash
uv run python tools/generate_raw_tm_c.py \
  "$out/incrementer.l1.tm" \
  "$out/incrementer.l1.utm.band" \
  -o "$out/cgoto_l1.c" \
  --backend computed-goto \
  --right-dump-cells 8

cc -O0 -std=gnu11 \
  "$out/cgoto_l1.c" \
  -o "$out/cgoto_l1_O0"

"$out/cgoto_l1_O0" 1000000
```

Current computed-goto result at `-O0`:

```text
backend=computed-goto status=halted steps=54915 ... state=U_HALT
decoded_right: 1 1 0 0 _ _ _ _
msteps_per_s=5.812
```

The backend compiles syntactically on this machine, but optimized builds are not
practical yet. `cc -O3 -std=gnu11` on the 124k-transition L2 host was stopped
after about 4.5 minutes, and `cc -O1` on the smaller 25k-transition L1 host was
stopped after about 1 minute. The current label-per-transition shape gives the
compiler too much global control flow to optimize.
