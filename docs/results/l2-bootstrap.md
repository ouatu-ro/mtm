# L2 Bootstrap Results

## Motivation

The project goal is to compile the Universal Turing Machine using the same
pipeline we use for an ordinary guest machine. In other words, we want a real
bootstrap story:

```text
source TMProgram + source SourceTape
  -> L1 UTM host + L1 encoded band
  -> L2 UTM host + L2 encoded band
```

At L1, the source program and source input band are encoded into one UTM band,
then run by a lowered UTM host. At L2, the L1 raw host and L1 runtime band are
themselves encoded as a guest and run by another UTM.

This gets large quickly. The L2 guest is no longer the tiny source incrementer;
it is the raw L1 UTM transition program plus the L1 runtime tape. That usually
requires a bigger ABI because the encoded guest has many more states and symbols
than the original source TM.

## Object Hierarchy

The source-level objects are:

```text
TMProgram
  source transition relation

SourceTape
  source tape/input
```

The compiler turns those into a universal-machine instance:

```text
TMProgram + SourceTape
  -> EncodedTape / UTMBandArtifact
  -> UniversalInterpreter
  -> MetaASM program
  -> lowered raw TM host
```

For the incrementer:

```text
source incrementer + input 1011____
  -> incrementer.l1.tm
  -> incrementer.l1.utm.band
```

Then L2 treats the L1 raw host as the guest:

```text
incrementer.l1.tm + incrementer.l1.utm.band
  -> raw guest transition program + raw runtime tape
  -> incrementer.l2.tm
  -> incrementer.l2.utm.band
```

So L2 is not "the source incrementer again." It is the UTM interpreting the L1
raw UTM computation.

## ABI Lattice

To make this coherent, the band has to carry the guest-owned ABI facts. A wider
host may run a narrower band, but it must not reinterpret the narrower fields as
host-width padded values.

The current rule is:

```text
band_abi <= host_abi
```

The implementation now relies on delimited fields:

- The band carries `#HALT_STATE`, `#BLANK_SYMBOL`, `#LEFT_DIR`, and
  `#RIGHT_DIR`.
- Field comparisons and copies stop at field/cell end markers.
- The host does not inherit or impose L1 ABI metadata onto the L2 guest band.
- Fresh blank expansion copies the band-owned `#BLANK_SYMBOL`.

The direct compatibility tests include:

- `test_wider_host_runs_narrow_incrementer_band_end_to_end`
- `test_runtime_abi_compatibility_allows_wider_host_and_rejects_narrower_host`
- `test_move_sim_head_right_expands_with_band_blank_symbol_payload`
- `test_move_sim_head_left_expands_with_band_blank_symbol_payload`

The most important result is that a wider generated UTM host can run a smaller
incrementer band and still produce:

```text
1 1 0 0 _ _ _ _
```

## Direct Runs

The L1 incrementer run is small enough to run normally:

```text
input:  1 0 1 1 _ _ _ _
output: 1 1 0 0 _ _ _ _
steps:  35,600 L1 raw steps
```

The cross-ABI lowered raw check is also small:

```text
host: incrementer.l2.tm
band: incrementer.l1.utm.band

status=halted
steps=54,915
state=U_HALT
decoded_right: 1 1 0 0 _ _ _ _
```

This is not the full L2-band run. It is a real lowered raw host check proving
that the larger L2 UTM can execute the smaller L1 band correctly.

## MetaASM Host Path

The MetaASM host simulates the universal-machine algorithm at the instruction
and block level. It executes operations such as comparisons, copies, rule
lookup, and simulated-head movement as MetaASM instructions rather than as every
lowered raw TM microstep.

The Python MetaASM host became too slow for the full L2 incrementer. A
trace-derived estimate put the full L2 MetaASM run around:

```text
634,438,903 MetaASM instructions
35,600 simulated L1 raw guest steps
```

At the Python host speed observed earlier, that was on the order of many hours.

We then built a fixed-array C MetaASM runner specialized to the L2 band. It
runs the same universal MetaASM algorithm over the L2 `.utm.band`, but without
Python dictionaries and object overhead.

Measured result:

```text
status=halted
meta_steps=634,438,903
guest_steps=35,600
decoded result begins with encoded 1 1 0 0
```

This takes about a second to a second and a half locally, depending on the exact
measurement.

What this proves:

- The L2 band can be interpreted by the universal MetaASM semantics.
- The bootstrapped computation reaches the encoded L1 final tape for `1100`.

What this does not prove:

- It does not execute every lowered L2 raw TM transition.
- It is equivalent with respect to interpreted guest transitions and final band
  state, but it is not the full raw L2 microstep run.

## Real Lowered L2 Raw Cost

The honest lowered L2 raw TM has to execute the UTM microcode itself.

The expensive benchmark currently shows:

```text
1 lowered MetaASM instruction ~= 2,245,707 raw L2 steps
```

Combining that with the L2 MetaASM instruction count:

```text
634,438,903 * 2,245,707
  ~= 1,424,763,885,539,421 raw L2 steps
```

The dense C raw runner reaches roughly:

```text
~941,000,000 raw steps/sec
```

That gives:

```text
1.424e15 / 941.659e6
  ~= 1,513,036 sec
  ~= 420 hours
  ~= 17.5 days
```

So the real lowered L2 raw run is feasible in principle, but still not a casual
local experiment. The C runner changes the estimate from "decades in Python" to
"weeks in C."

## C Acceleration Experiments

We tried several C execution strategies for raw TM artifacts.

| Backend | Shape | Correctness | L2/L2 1B slice | Compile behavior | Notes |
| --- | --- | --- | --- | --- | --- |
| header dense array | Generic C interpreter with dense `next/write/move` arrays | passes | ~941M steps/sec | fast | Best raw-step throughput so far |
| packed-array | Standalone C with one packed `uint64_t` transition entry | passes | ~452M steps/sec | fast | Slower because unpacking costs more than saved loads |
| computed-goto | One C label per valid transition | passes at `-O0` | not practical | optimized compile hostile | Too much global control flow |
| state-fn | One C function per raw TM state | passes | ~328M steps/sec | fast enough | Indirect function call per step hurts |
| state-switch | One giant `switch(state)` with nested `switch(read)` | passes | not measured for L2/L2 | `-O3` cross-ABI compile took 85 min | Optimizer overwhelmed |

### Dense Header Runner

The dense runner is still an interpreter, but a very tight one:

```text
read tape[head]
lookup transition[state, read]
write
state = next
head += move
```

On the real L2/L2 bounded slice:

```text
steps=1,000,000,000
msteps_per_s=941.659
```

### Packed Array

The packed standalone backend stores transition fields in one `uint64_t`:

```text
valid | move | write | next
```

It passes the cross-ABI check:

```text
backend=packed-array
status=halted
steps=54,915
decoded_right: 1 1 0 0 _ _ _ _
```

But the real L2/L2 slice is slower:

```text
backend=packed-array
steps=1,000,000,000
msteps_per_s=451.802
```

The memory footprint is smaller, but the hot path pays for shifts and masks on
every raw step.

### Computed Goto

The computed-goto backend emits one label per valid transition and uses
Clang/GNU C label pointers.

It compiles syntactically on this machine and passes at `-O0`:

```text
backend=computed-goto
status=halted
steps=54,915
decoded_right: 1 1 0 0 _ _ _ _
msteps_per_s=5.812
```

Optimized builds are not practical in the current shape:

```text
L2 host, cc -O3 -std=gnu11: stopped after about 4.5 minutes
L1 host, cc -O1 -std=gnu11: stopped after about 1 minute
```

The current label-per-transition form gives the compiler too much global
control flow to optimize.

### State Function

The `state-fn` backend emits one C function per raw TM state:

```c
static State run_state_123(Symbol *tape, int *head) {
  switch (tape[*head]) {
    case TOK_0:
      tape[*head] = TOK_1;
      *head += 1;
      return STATE_456;
    default:
      return STUCK_STATE;
  }
}
```

It passes the cross-ABI check:

```text
backend=state-fn
status=halted
steps=54,915
decoded_right: 1 1 0 0 _ _ _ _
```

But the real L2/L2 slice is slower than dense interpretation:

```text
backend=state-fn
steps=1,000,000,000
msteps_per_s=327.661
```

The state-as-code shape is valid, but the indirect function call per raw step
costs more than dense table dispatch.

### State Switch

The `state-switch` backend emits raw TM states as cases in one large
`switch(state)`, with a nested `switch(tape[head])`.

It passes the L2-host/L1-band cross-ABI check:

```text
backend=state-switch
status=halted
steps=54,915
decoded_right: 1 1 0 0 _ _ _ _
```

Compile-time measurements for the L2-host/L1-band artifact:

```text
cc -O0 -std=c11: 5.118s total
cc -O3 -std=c11: 1:25:09.32 total
```

The `-O3` binary runs correctly, but the cross-ABI run halts after only 54,915
steps, so its runtime numbers are too small and noisy to compare with the 1B
step L2/L2 slices. A repeated short-run benchmark gave only a rough indication
that `-O3` is modestly faster than `-O0` on that tiny run.

The important result is compile behavior: `-O3` does finish, but only after
about 85 minutes for a 15 MB cross-ABI generated C file. That is not a practical
iteration loop.

## Interpretation

Naively compiling raw TM states or transitions to C does not automatically beat
a tight C interpreter.

The dense table runner is small, cache-friendly, and easy for the CPU. Huge
generated control flow increases compile time dramatically and can make runtime
worse. The compiler cannot cheaply recover the UTM's higher-level structure
from raw transition states alone.

The MetaASM C runner is fast because it operates one level up: it executes the
universal algorithm in structured operations such as compare, copy, rule lookup,
and simulated-head movement. That is why it can finish the L2 incrementer in
about a second while the honest raw L2 estimate is measured in weeks.

## Possible Future Directions

These are not required to claim the current result. They are possible directions
for exploring faster honest-ish execution.

### Routine-Local Compilation

Use the existing lowering source map:

```text
block, instruction_index, routine_name
```

Compile one routine group at a time. This would preserve raw tape/head/state
effects, but avoid global transition dispatch inside a routine-sized chunk.

### Hot Raw-Chain Fusion

Profile a bounded raw run, find hot deterministic state chains, and emit those
chains as straight-line C with a fallback to dense interpretation.

### Hybrid Runner

Keep the dense table interpreter as the baseline and add compiled fast paths
only for selected hot routines or chains.

### Profile-Guided Backend Selection

Use trace counts to decide whether a state or routine should be interpreted,
compiled as a local switch, or fused.

## Current Bottom Line

We now have:

- L1 proof: the source incrementer reaches `1100`.
- L2 MetaASM proof: bootstrapped L2 interpretation reaches encoded `1100`.
- Real raw host cross-ABI proof: `incrementer.l2.tm` runs
  `incrementer.l1.utm.band` and reaches `1100`.
- Real full lowered L2 raw estimate: weeks, not hours.
- C backend experiments showing dense interpretation beats naive whole-program
  C compilation so far.
