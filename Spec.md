# Meta-TM Compiler Spec

## 0. Goal

Build a staged system where an object-level Turing machine program is encoded as data on a runtime raw tape view, and a meta-level universal interpreter can execute it.

There are two separate compilers:

```text
Object compiler:
  source TM program + source tape/configuration
    -> semantic UTM-encoded object
    -> serialized UTM artifact

Meta compiler:
  Meta-ASM universal interpreter
    -> ordinary raw TM transition table
```

The final execution target is:

```text
raw ordinary TM runner
  program:  lowered Meta-ASM transition table
  tape:     serialized UTM artifact plus runtime raw tape view
```

The immediate implementation target is the object compiler plus a Meta-ASM spec.

---

# 0.1 Object Model

The system should keep the following concepts distinct:

```text
TMProgram
  pure source-level TM semantics

TMBand
  source-level tape/configuration

TMAbi
  target encoding family / machine family

Encoding
  dense concrete assignment of IDs and bit widths under a chosen ABI

UTMEncoded
  semantic compiled object for the universal machine

UTMEncodingArtifact
  serialized `.utm`-style artifact for the universal machine

MetaASMProgram
  semantic universal interpreter in Meta-ASM form

RawTMProgram
  lowered ordinary TM transition table

RawTMConfig
  runner-facing execution state

DecodedBandView
  semantic interpretation of UTM execution state
```

Important design rule:

```text
raw tape view / `outer_tape` is a runtime/serialization representation,
not the primary semantic IR
```

The central semantic compiled object is `UTMEncoded`, not the raw tape view.

Public naming boundary:

| Primary names | Compatibility aliases |
| --- | --- |
| `build_encoded_band` | `build_runtime_tape`, `build_outer_tape` |
| `compile_tm_to_universal_tape` | `compile_tm_to_runtime_tape`, `compile_tm_to_encoded_band` |
| `materialize_runtime_tape`, `split_runtime_tape` | `materialize_raw_tape`, `split_raw_tape`, `split_outer_tape` |
| `pretty_runtime_tape` | `pretty_outer_tape` |
| `run_meta_asm_runtime`, `run_meta_asm_block_runtime` | `run_meta_asm_host`, `run_meta_asm_block` |
| `utm_encoded_from_band`, `utm_artifact_from_band` | `build_utm_encoded`, `build_utm_encoding_artifact` |

These aliases stay until downstream callers have moved to the primary names; after that, the shim layer can be removed mechanically.

---

# 0.2 Compatibility Boundary

During the migration, the codebase keeps two naming layers:

Primary names:

- `build_encoded_band`
- `compile_tm_to_encoded_band`
- `runtime_tape`
- `materialize_runtime_tape`
- `split_runtime_tape`
- `run_meta_asm_runtime`
- `run_meta_asm_block_runtime`
- `pretty_runtime_tape`

Compatibility aliases:

- `build_outer_tape`
- `compile_tm_to_universal_tape`
- `outer_tape`
- `materialize_raw_tape`
- `split_raw_tape`
- `split_outer_tape`
- `run_meta_asm_host`
- `run_meta_asm_block`
- `pretty_raw_tape`
- `pretty_outer_tape`

Rule:

```text
new docs and new code should prefer the primary names;
compatibility aliases remain only to avoid breaking existing callers.
```

---

# 1. Object Compiler API

```python
def infer_minimal_abi(tm_prog, source_band) -> TMAbi:
    ...

def compile_tm_to_encoded_band(
    tm_prog,
    source_band,
    *,
    abi,
    blanks_left=0,
    blanks_right=8,
):
    ...

def build_utm_encoded(encoded_band, *, minimal_abi=None) -> UTMEncoded:
    ...

def build_utm_encoding_artifact(encoded_band, *, minimal_abi=None) -> UTMEncodingArtifact:
    ...
```

Source TM format:

```python
tm_prog = {
    (state, read_symbol): (next_state, write_symbol, move_dir),
}
```

Where:

```python
L = -1
R = 1
```

Source tape/configuration format:

```python
TMBand(
    cells=...,
    head=...,
    blank="_",
)
```

The object compiler should support two explicit modes:

```text
1. infer minimal ABI requirement
2. compile under a selected target ABI
```

Compatibility helpers may still accept bare `input_symbols` and infer a minimal ABI automatically, but the main semantic pipeline should make both `source_band` and `abi` explicit.

The semantic compiler returns a semantic UTM object:

```python
UTMEncoded(
    encoding=...,
    registers=...,
    rules=...,
    simulated_tape=...,
    simulated_head=...,
    minimal_abi=...,
    target_abi=...,
)
```

Serialization of that semantic object yields an artifact form:

```python
UTMEncodingArtifact(
    encoding=...,
    left_band=...,
    right_band=...,
    start_head=...,
    target_abi=...,
    minimal_abi=...,
)
```

The compiler is allowed to reject a source TM if the selected widths are too small:

```text
number_of_states  <= 2^state_width
number_of_symbols <= 2^symbol_width
number_of_dirs    <= 2^dir_width
```

Equivalently:

```text
required_abi <= selected_abi
```

The object compiler does **not** emit behavior. It emits a semantic compiled object plus a serialized artifact consumed by the universal interpreter.

---

# 2. Encoding Map

The compiler assigns dense numeric IDs to source-level states and symbols.

Example:

```text
states:
  qAdd        -> 00000000
  qDone       -> 00000001
  qFindMargin -> 00000010

symbols:
  "0" -> 00000000
  "1" -> 00000001
  "_" -> 00000010

directions:
  L -> 0
  R -> 1
```

Required property:

```text
decode(encode(x)) = x
```

No hashing unless collisions are impossible by construction. Dense interning is preferred.

---

# 3. Serialized UTM Artifact Layout

The serialized UTM artifact is split conceptually:

```text
negative addresses: meta side
nonnegative addresses: object tape side
```

The split is a serialization/runtime convention, not the primary semantic IR.

```text
... #REGS ... #RULES ... #END_RULES | #TAPE #CELL ... #END_TAPE ...
                                      ^
                                      address 0
```

## 3.1 Meta Side

The left/meta side contains registers and transition registry.

```text
#REGS
  #CUR_STATE     <state_bits>  #END_FIELD
  #CUR_SYMBOL    <symbol_bits> #END_FIELD
  #WRITE_SYMBOL  <symbol_bits> #END_FIELD
  #NEXT_STATE    <state_bits>  #END_FIELD
  #MOVE_DIR      <dir_bits>    #END_FIELD
  #CMP_FLAG      <bit>         #END_FIELD
  #TMP           <tmp_bits>    #END_FIELD
#END_REGS

#RULES
  #RULE
    #STATE <state_bits>  #END_FIELD
    #READ  <symbol_bits> #END_FIELD
    #WRITE <symbol_bits> #END_FIELD
    #NEXT  <state_bits>  #END_FIELD
    #MOVE  <dir_bits>    #END_FIELD
  #END_RULE

  ...
#END_RULES
```

Registers:

| Register        | Meaning                                                              |
| --------------- | -------------------------------------------------------------------- |
| `#CUR_STATE`    | Current simulated TM state.                                          |
| `#CUR_SYMBOL`   | Symbol copied from the simulated head cell.                          |
| `#WRITE_SYMBOL` | Symbol selected by matched transition rule.                          |
| `#NEXT_STATE`   | Next state selected by matched transition rule.                      |
| `#MOVE_DIR`     | Movement direction selected by matched transition rule.              |
| `#CMP_FLAG`     | Comparison result flag, usually `1` for equal and `0` for not equal. |
| `#TMP`          | Scratch space for compare/copy routines.                             |

Transition record:

```text
#RULE
  #STATE q
  #READ  a
  #WRITE b
  #NEXT  q'
  #MOVE  d
#END_RULE
```

Semantics:

```text
(q, a) -> (q', b, d)
```

## 3.2 Object Tape Side

The right/object side contains the simulated TM tape.

```text
#TAPE
  #CELL #HEAD    <symbol_bits> #END_CELL
  #CELL #NO_HEAD <symbol_bits> #END_CELL
  #CELL #NO_HEAD <symbol_bits> #END_CELL
  ...
#END_TAPE
```

Each encoded cell has:

| Field                | Meaning                                           |
| -------------------- | ------------------------------------------------- |
| `#CELL`              | Cell delimiter.                                   |
| `#HEAD` / `#NO_HEAD` | Whether this cell is the simulated head position. |
| `<symbol_bits>`      | Encoded simulated tape symbol.                    |
| `#END_CELL`          | Cell terminator.                                  |

Invariant:

```text
Exactly one encoded object-tape cell has #HEAD.
```

---

# 4. Field Width Policy

Initial implementation uses fixed-width fields:

```text
state field width  = state_width
symbol field width = symbol_width
direction width    = 1
```

But fields also carry terminators:

```text
#STATE 00000010 #END_FIELD
#CELL #HEAD 00000001 #END_CELL
```

This redundancy is intentional.

Fixed-width routines can count bits:

```text
compare exactly W bits, then check #END_FIELD
```

Variable-width routines can later ignore `W` and scan until terminators:

```text
compare until #END_FIELD
```

This gives a path from a width-specialized universal family to a width-independent universal machine.

---

# 5. Meta-ASM

Meta-ASM is a macro language for expressing the universal interpreter over the encoded tape.

It is not Python. It is also not yet raw TM transitions. It is an intermediate language whose instructions must each have a finite raw-TM lowering.

## 5.1 Program Structure

```text
LABEL name
  instruction
  instruction
  ...
```

Control-flow instructions:

```text
GOTO label
HALT
```

Labels are resolved by the Meta-ASM compiler.

---

# 6. Meta-ASM Instruction Set

## 6.1 Movement / Search

```text
SEEK marker dir
```

Move outer TM head in direction `dir` until `marker` is found.

```text
SEEK_ONE_OF [marker1, marker2, ...] dir
```

Move until one of the listed markers is found.

```text
FIND_FIRST_RULE
```

Move to the first `#RULE` after `#RULES`, or to `#END_RULES` if no rule exists.

```text
FIND_NEXT_RULE
```

Precondition: outer head is at current `#RULE`.

Postcondition: outer head is at next `#RULE` or `#END_RULES`.

```text
FIND_HEAD_CELL
```

Find the encoded object-tape cell whose head flag is `#HEAD`.

Postcondition: outer head is at that cell’s `#CELL` marker.

---

## 6.2 Comparison

```text
COMPARE_GLOBAL_LOCAL global_marker local_marker width
```

Compare a unique global register field with a local field inside the current rule.

Example:

```text
COMPARE_GLOBAL_LOCAL #CUR_STATE #STATE state_width
```

Precondition:

```text
outer head is at current #RULE
```

Meaning:

```text
compare bits after global #CUR_STATE
against bits after local #STATE in current rule
```

Postcondition:

```text
outer head returns to current #RULE
#CMP_FLAG = 1 if equal, else 0
all temporary marks are cleaned
```

```text
COMPARE_GLOBAL_LITERAL global_marker literal_bits
```

Compare a global register field against a literal bitstring.

Example:

```text
COMPARE_GLOBAL_LITERAL #MOVE_DIR 0
```

Postcondition:

```text
#CMP_FLAG = 1 if equal, else 0
```

```text
BRANCH_CMP label_equal label_not_equal
```

Branch based on `#CMP_FLAG`.

---

## 6.3 Copying

```text
COPY_LOCAL_GLOBAL local_marker global_marker width
```

Copy a local field from the current rule into a global register.

Example:

```text
COPY_LOCAL_GLOBAL #WRITE #WRITE_SYMBOL symbol_width
```

Precondition:

```text
outer head is at current #RULE
```

Postcondition:

```text
outer head returns to current #RULE
target global register overwritten
```

```text
COPY_GLOBAL_GLOBAL src_marker dst_marker width
```

Copy one global register field into another.

Example:

```text
COPY_GLOBAL_GLOBAL #NEXT_STATE #CUR_STATE state_width
```

```text
COPY_HEAD_SYMBOL_TO global_marker width
```

Copy symbol bits from the current simulated head cell into a global register.

Precondition:

```text
outer head is at #CELL of the head cell
```

Example:

```text
COPY_HEAD_SYMBOL_TO #CUR_SYMBOL symbol_width
```

```text
COPY_GLOBAL_TO_HEAD_SYMBOL global_marker width
```

Copy a global register field into the symbol field of the current simulated head cell.

Precondition:

```text
outer head is at #CELL of the head cell
```

Example:

```text
COPY_GLOBAL_TO_HEAD_SYMBOL #WRITE_SYMBOL symbol_width
```

---

## 6.4 Writing

```text
WRITE_GLOBAL global_marker literal_bits
```

Overwrite a global register with literal bits.

Example:

```text
WRITE_GLOBAL #CMP_FLAG 0
```

This is mostly useful for initialization, cleanup, and debugging.

---

## 6.5 Simulated Head Movement

```text
MOVE_SIM_HEAD_LEFT
```

Move the `#HEAD` flag from the current simulated cell to the previous encoded cell.

Precondition:

```text
outer head is at current simulated #CELL
```

Postcondition:

```text
old cell has #NO_HEAD
left neighbor has #HEAD
outer head is at new head cell's #CELL
```

If no left neighbor exists, first implementation may either:

```text
1. enter STUCK, or
2. extend the encoded tape with a blank cell on the left
```

For simplicity, initial bounded implementation may choose `STUCK`.

```text
MOVE_SIM_HEAD_RIGHT
```

Move the `#HEAD` flag from the current simulated cell to the next encoded cell.

If the next marker is `#END_TAPE`, implementation may either:

```text
1. enter STUCK, or
2. insert/expose a new blank cell before #END_TAPE
```

For simplicity, initial bounded implementation may choose `STUCK`; dynamic extension can be added later.

---

## 6.6 Branching on Current Marker

```text
BRANCH_AT marker label_true label_false
```

If the outer head is currently on `marker`, branch to `label_true`; otherwise branch to `label_false`.

Useful after:

```text
FIND_FIRST_RULE
FIND_NEXT_RULE
SEEK_ONE_OF
```

Example:

```text
BRANCH_AT #END_RULES STUCK CHECK_STATE
```

---

# 7. Universal Interpreter in Meta-ASM

For fixed widths:

```text
state_width  = Wq
symbol_width = Ws
dir_width    = 1
L_BITS        = encoding of L
R_BITS        = encoding of R
HALT_BITS     = encoding of halt_state
```

Meta-ASM program:

```text
LABEL START_STEP
  COMPARE_GLOBAL_LITERAL #CUR_STATE HALT_BITS
  BRANCH_CMP HALT FIND_HEAD

LABEL FIND_HEAD
  FIND_HEAD_CELL
  COPY_HEAD_SYMBOL_TO #CUR_SYMBOL Ws
  FIND_FIRST_RULE
  GOTO LOOKUP_RULE

LABEL LOOKUP_RULE
  BRANCH_AT #END_RULES STUCK CHECK_STATE

LABEL CHECK_STATE
  COMPARE_GLOBAL_LOCAL #CUR_STATE #STATE Wq
  BRANCH_CMP CHECK_READ NEXT_RULE

LABEL CHECK_READ
  COMPARE_GLOBAL_LOCAL #CUR_SYMBOL #READ Ws
  BRANCH_CMP MATCHED_RULE NEXT_RULE

LABEL NEXT_RULE
  FIND_NEXT_RULE
  GOTO LOOKUP_RULE

LABEL MATCHED_RULE
  COPY_LOCAL_GLOBAL #WRITE #WRITE_SYMBOL Ws
  COPY_LOCAL_GLOBAL #NEXT  #NEXT_STATE Wq
  COPY_LOCAL_GLOBAL #MOVE  #MOVE_DIR 1

  FIND_HEAD_CELL
  COPY_GLOBAL_TO_HEAD_SYMBOL #WRITE_SYMBOL Ws

  COPY_GLOBAL_GLOBAL #NEXT_STATE #CUR_STATE Wq

  COMPARE_GLOBAL_LITERAL #CUR_STATE HALT_BITS
  BRANCH_CMP HALT DISPATCH_MOVE

LABEL DISPATCH_MOVE
  COMPARE_GLOBAL_LITERAL #MOVE_DIR L_BITS
  BRANCH_CMP MOVE_LEFT CHECK_RIGHT

LABEL CHECK_RIGHT
  COMPARE_GLOBAL_LITERAL #MOVE_DIR R_BITS
  BRANCH_CMP MOVE_RIGHT START_STEP

LABEL MOVE_LEFT
  FIND_HEAD_CELL
  MOVE_SIM_HEAD_LEFT
  GOTO START_STEP

LABEL MOVE_RIGHT
  FIND_HEAD_CELL
  MOVE_SIM_HEAD_RIGHT
  GOTO START_STEP

LABEL HALT
  HALT

LABEL STUCK
  HALT
```

This program is the universal interpreter at the Meta-ASM level.

---

# 8. Lowering Strategy

Each Meta-ASM instruction lowers to a finite fragment of raw TM transition states.

Raw TM transition shape:

```python
meta_tm_prog = {
    (state, read_symbol): (next_state, write_symbol, move_dir),
}
```

A lowering function has the shape:

```python
def lower_instruction(builder, instr, continuation_label):
    ...
```

The builder emits raw transitions and generates fresh raw states:

```python
class TMBuilder:
    def fresh(self, prefix): ...
    def emit(self, state, read, next_state, write, move): ...
    def label_state(self, label): ...
```

## 8.1 Lowering Obligations

Every Meta-ASM instruction must specify:

```text
Precondition:
  where the raw TM head is expected to be

Postcondition:
  where the raw TM head is left
  which tape fields may be mutated
  which markers/temporary symbols are cleaned
```

This is mandatory. Without pre/post head-position contracts, macro expansion becomes unmanageable.

---

# 9. Example Lowering Descriptions

## 9.1 `SEEK marker dir`

High-level behavior:

```text
while scanned symbol != marker:
    move dir
continue
```

Raw lowering:

```text
state seek_marker:
  on marker: goto continuation, keep marker, stay or normalize
  on any other symbol: keep symbol, move dir, stay in seek_marker
```

Requires enumerating the outer alphabet.

---

## 9.2 `COMPARE_GLOBAL_LITERAL marker literal_bits`

High-level behavior:

```text
seek marker
for each bit in literal_bits:
    move to next unprocessed bit
    compare with expected literal bit
    if mismatch: write #CMP_FLAG = 0
if all match: write #CMP_FLAG = 1
cleanup
```

Lowering idea:

```text
For each bit position i:
  emit control states:
    compare_i_expect_0
    compare_i_expect_1

Mismatch jumps to write_cmp_false.
Success after all bits jumps to write_cmp_true.
```

This can be implemented either by counting fixed width in control states or by marking consumed bits.

For first implementation, fixed-width counting is simpler.

---

## 9.3 `COMPARE_GLOBAL_LOCAL global_marker local_marker width`

High-level behavior:

```text
save current #RULE anchor
compare width bits after global_marker
with width bits after local_marker in current rule
set #CMP_FLAG
return to #RULE
```

Lowering idea:

```text
for i in 0..width-1:
  go to global_marker
  move i+1 cells to bit i
  branch on bit 0/1 into control state
  return to current #RULE
  scan right to local_marker
  move i+1 cells to local bit i
  compare bit
  if mismatch: set #CMP_FLAG=0 and return to #RULE
after all bits:
  set #CMP_FLAG=1 and return to #RULE
```

Requires either:

```text
1. preserving current #RULE by returning to it via local scans, or
2. marking the active #RULE temporarily.
```

Prefer marking the active rule:

```text
#RULE -> #RULE_ACTIVE
```

Then local scans can reliably return to `#RULE_ACTIVE`.

Cleanup:

```text
#RULE_ACTIVE -> #RULE
```

---

## 9.4 `COPY_LOCAL_GLOBAL local_marker global_marker width`

High-level behavior:

```text
mark active #RULE
for each bit i:
    read bit i from local field
    write it to bit i of global field
restore active #RULE marker
return to #RULE
```

Lowering idea:

```text
for each bit i:
  scan from #RULE_ACTIVE to local_marker
  move to bit i
  branch into saw_0 / saw_1 state
  scan to global_marker
  move to bit i
  write 0 or 1
  scan back to #RULE_ACTIVE
```

Again, fixed-width indexing can be encoded in control states.

---

## 9.5 `FIND_HEAD_CELL`

High-level behavior:

```text
seek #TAPE
repeat:
  seek next #CELL
  inspect following head flag
  if #HEAD: stop at that #CELL
  if #NO_HEAD: continue
  if #END_TAPE: stuck
```

Lowering idea:

```text
scan right to #TAPE
scan right to #CELL or #END_TAPE
if #END_TAPE: goto STUCK
if #CELL:
    move right one symbol
    if #HEAD:
        move left one symbol back to #CELL
        continue
    if #NO_HEAD:
        continue scanning right
```

Postcondition:

```text
raw head is at the #CELL marker of the simulated head cell
```

---

## 9.6 `COPY_HEAD_SYMBOL_TO global_marker width`

Precondition:

```text
raw head at current simulated #CELL
```

High-level behavior:

```text
for i in 0..width-1:
    read symbol bit i from cell
    write it into global register bit i
return to #CELL
```

Lowering idea:

```text
mark current #CELL as #CELL_ACTIVE
for each i:
  move to cell symbol bit i
  branch saw_0/saw_1
  seek global_marker
  move to bit i
  write bit
  seek #CELL_ACTIVE
restore #CELL_ACTIVE to #CELL
```

---

## 9.7 `COPY_GLOBAL_TO_HEAD_SYMBOL global_marker width`

Same as above, but direction reversed:

```text
for i in 0..width-1:
    read global bit i
    write symbol bit i into active head cell
```

---

## 9.8 `MOVE_SIM_HEAD_RIGHT`

Precondition:

```text
raw head at current simulated #CELL
```

High-level behavior:

```text
set current head flag to #NO_HEAD
find next #CELL
set its head flag to #HEAD
return to new #CELL
```

Lowering idea:

```text
at #CELL:
  move right to head flag
  write #NO_HEAD
  scan right to next #CELL or #END_TAPE
  if #END_TAPE: STUCK or extension routine
  if #CELL:
      move right to head flag
      write #HEAD
      move left to #CELL
```

---

## 9.9 `MOVE_SIM_HEAD_LEFT`

Precondition:

```text
raw head at current simulated #CELL
```

High-level behavior:

```text
set current head flag to #NO_HEAD
scan left to previous #CELL
set its head flag to #HEAD
return to previous #CELL
```

Lowering issue:

```text
Because #CELL appears at the beginning of each cell, scanning left from current #CELL to previous #CELL is straightforward if cell terminators are present but not strictly required.
```

Bounded first version:

```text
if previous marker is #TAPE: STUCK
```

Dynamic-extension version can be added later.

---

# 10. Active Marker Alphabet

Some lowering routines need temporary active markers.

Suggested marker variants:

```text
#RULE        -> #RULE_ACTIVE
#CELL        -> #CELL_ACTIVE
0            -> 0^
1            -> 1^
```

The raw TM alphabet must include:

```text
base markers
base bits
active marker variants
marked bit variants
outer blank
```

Invariant at interpreter-cycle boundaries:

```text
No active markers remain.
No marked bits remain.
Exactly one #HEAD exists on the object tape.
```

---

# 11. Correctness Targets

## 11.1 Object Compiler Correctness

For source TM `M` and input `x`:

```text
decode_utm_encoding_artifact(compile_tm_to_encoded_band(M, x))
=
initial configuration of M on x
```

## 11.2 Meta-ASM Reference Correctness

One Meta-ASM interpreter cycle corresponds to one object TM step:

```text
decode(band_after_one_meta_cycle)
=
step_M(decode(band_before_one_meta_cycle))
```

for non-halting configurations with a matching rule.

## 11.3 Lowering Correctness

For each Meta-ASM instruction:

```text
raw TM fragment implements the instruction's pre/post contract
```

For the whole lowered universal interpreter:

```text
At Meta-ASM label boundaries,
raw TM tape decodes to the same semantic state as the Meta-ASM execution.
```

## 11.4 End-to-End Correctness

If object TM `M` reaches configuration `C'` from `C` in one step, then the lowered meta-TM reaches the encoded `C'` after finitely many raw TM steps:

```text
Encode(C) --META_TM_PROG*--> Encode(C')
```

A full run simulates the object TM until halt, stuck, or fuel exhaustion.

---

# 12. Implementation Order

Recommended order:

```text
1. Update current encoder to accept explicit widths.
2. Add #END_FIELD, #END_REGS, #END_RULE, #END_CELL markers.
3. Update parsers and pretty printers.
4. Define Meta-ASM instruction dataclasses.
5. Generate the universal Meta-ASM program from Encoding widths and marker family.
6. Write a Python interpreter for Meta-ASM over the semantic UTM object / serialized artifact.
7. Lower the simplest instructions first:
     SEEK
     GOTO
     HALT
     FIND_HEAD_CELL
8. Then lower fixed-width copy/compare instructions.
9. Finally lower MOVE_SIM_HEAD_LEFT/RIGHT.
```

Do not lower everything before the Meta-ASM interpreter works. The Meta-ASM interpreter is the executable spec for the lowering.

---

# 13. Minimal Immediate Milestone

The next concrete milestone should be:

```python
abi = infer_minimal_abi(tm_prog, source_band)

encoded = compile_tm_to_encoded_band(
    tm_prog,
    source_band,
    abi=abi,
)

artifact = serialize_utm(encoded)
asm = build_universal_meta_asm(encoded.encoding)

status, final_runtime_tape, trace, reason = run_meta_asm_runtime(asm, encoded.encoding, encoded.runtime_tape)
```

Expected decoded result:

```text
1011₂ + 1 = 1100₂
```

At this stage, no raw TM transition table is required yet. The next milestone after that is:

```python
meta_tm_prog = lower_meta_asm_to_tm(
    asm,
    abi=encoded.target_abi,
    alphabet=chosen_outer_alphabet,
)
```

Then:

```python
run_tm(meta_tm_prog, artifact, initial_state="U_START")
```

should match the host Meta-ASM run at label/interpreter-cycle boundaries.
