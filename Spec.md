# Meta-TM Compiler Spec

## 1. Goal

Build a staged system where a source-level Turing machine is compiled into an
encoded UTM input band, and a generated universal interpreter executes that band
on an ordinary TM runner.

The two emitted runtime artifacts are:

```text
utm.tm              lowered universal-machine transition program
object.utm.band     encoded object program plus simulated object tape
```

Execution pairs them as:

```text
ordinary TM runner
  program: utm.tm
  input:   object.utm.band
```

There are two compilation pipelines:

```text
Object compiler:
  TMInstance
  -> UTMEncoded
  -> UTMBandArtifact

Universal interpreter compiler:
  TMAbi
  -> MetaASMProgram
  -> TMTransitionProgram
  -> UTMProgramArtifact
```

## 2. Public Interface

The intended top-level workflow is:

```python
instance = TMInstance(program, band)

compiler = Compiler(target_abi=abi)
encoded = compiler.compile(instance)

band_artifact = encoded.to_band_artifact()
band_artifact.write("object.utm.band")

interpreter = UniversalInterpreter.for_abi(encoded.target_abi)
asm = interpreter.to_meta_asm()
program_artifact = asm.lower().to_artifact()
program_artifact.write("utm.tm")

result = program_artifact.run(band_artifact, fuel=100_000)
view = result.decode(encoded.encoding)
```

Primary objects:

- `TMProgram`
- `TMBand`
- `TMInstance`
- `TMAbi`
- `Encoding`
- `Compiler`
- `UTMEncoded`
- `UTMBandArtifact`
- `UniversalInterpreter`
- `MetaASMProgram`
- `TMTransitionProgram`
- `UTMProgramArtifact`
- `TMRunConfig`
- `DecodedBandView`

## 3. Source Program and Band

Source transition shape:

```python
(state, read_symbol) -> (next_state, write_symbol, move_direction)
```

Directions:

```python
L = -1
R = 1
```

Source band:

```python
TMBand(
    cells=("1", "0", "1", "1"),
    head=0,
    blank="_",
)
```

Source instance:

```python
TMInstance(
    program=program,
    band=band,
)
```

The source band is a finite demonstrational tape/configuration. The UTM band
artifact may include explicit blank padding on either side of the provided
source cells.

## 4. ABI and Encoding

The object compiler supports two ABI operations:

```python
Compiler.infer_abi(instance) -> TMAbi
Compiler(target_abi=abi).compile(instance) -> UTMEncoded
```

The compiler accepts a selected ABI when:

```text
number_of_states  <= 2^state_width
number_of_symbols <= 2^symbol_width
number_of_dirs    <= 2^dir_width
```

Encoding assigns dense IDs:

```text
states:
  qAdd         -> 00000000
  qDone        -> 00000001
  qFindMargin  -> 00000010

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

## 5. Semantic UTM Object

The object compiler produces:

```python
UTMEncoded(
    encoding=...,
    registers=...,
    rules=...,
    simulated_tape=...,
    minimal_abi=...,
    target_abi=...,
)
```

Registers:

| Register | Meaning |
| --- | --- |
| `cur_state` | Current simulated source state. |
| `cur_symbol` | Symbol copied from the simulated head cell. |
| `write_symbol` | Symbol selected by the matched transition rule. |
| `next_state` | Next state selected by the matched transition rule. |
| `move_dir` | Direction selected by the matched transition rule. |
| `cmp_flag` | Boolean comparison flag represented as a bit. |
| `tmp_bits` | Scratch bits used by copy/compare routines. |

Rules:

```python
UTMEncodedRule(
    state=...,
    read_symbol=...,
    next_state=...,
    write_symbol=...,
    move_dir=...,
)
```

Simulated tape:

```python
UTMSimulatedTape(
    cells=...,
    head=...,
    blank=...,
)
```

## 6. `.utm.band` Artifact Layout

`UTMBandArtifact` serializes the semantic UTM object into a split band:

```text
left band:   registers + transition rules
right band:  simulated object tape
```

Runtime materialization:

```text
... left_band[-3] left_band[-2] left_band[-1] | right_band[0] right_band[1] right_band[2] ...
                                               ^
                                               split point between -1 and 0
```

The left band is placed at negative addresses. The right band starts at address
`0`.

### 6.1 Left Band

The left band contains registers and transition rules:

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

Transition record semantics:

```text
(#STATE, #READ) -> (#NEXT, #WRITE, #MOVE)
```

### 6.2 Right Band

The right band contains the simulated source tape:

```text
#TAPE
  #CELL #HEAD    <symbol_bits> #END_CELL
  #CELL #NO_HEAD <symbol_bits> #END_CELL
  #CELL #NO_HEAD <symbol_bits> #END_CELL
  ...
#END_TAPE
```

Invariant:

```text
Exactly one encoded tape cell carries #HEAD.
```

### 6.3 Field Widths

Initial fixed-width fields:

```text
state field width  = state_width
symbol field width = symbol_width
direction width    = dir_width
```

Fields also carry terminators:

```text
#STATE 00000010 #END_FIELD
#CELL #HEAD 00000001 #END_CELL
```

The fixed width lets the interpreter count bits. The terminators make layout
validation and variable-width routines straightforward.

## 7. Meta-ASM

Meta-ASM is the semantic instruction language for the generated universal
interpreter. A `MetaASMProgram` contains labeled blocks:

```text
LABEL name
  instruction
  instruction
  ...
```

Control flow:

```text
GOTO label
HALT
```

Labels resolve during lowering.

## 8. Meta-ASM Instruction Set

### 8.1 Movement and Search

```text
SEEK marker dir
```

Move the runtime head in `dir` until `marker` is found.

```text
SEEK_ONE_OF [marker1, marker2, ...] dir
```

Move until one of the listed markers is found.

```text
FIND_FIRST_RULE
```

Move to the first `#RULE` after `#RULES`, or to `#END_RULES` when the rule
registry is empty.

```text
FIND_NEXT_RULE
```

Precondition: head is at the current `#RULE`.

Postcondition: head is at the next `#RULE` or `#END_RULES`.

```text
FIND_HEAD_CELL
```

Find the simulated object-tape cell carrying `#HEAD`.

Postcondition: head is at that cell's `#CELL` marker.

### 8.2 Comparison

```text
COMPARE_GLOBAL_LOCAL global_marker local_marker width
```

Compare a global register field with a field inside the current rule.

Example:

```text
COMPARE_GLOBAL_LOCAL #CUR_STATE #STATE state_width
```

Postcondition:

```text
head returns to the current #RULE
#CMP_FLAG = 1 when equal
#CMP_FLAG = 0 when different
temporary marks are cleaned
```

```text
COMPARE_GLOBAL_LITERAL global_marker literal_bits
```

Compare a global register field against a literal bitstring.

```text
BRANCH_CMP label_equal label_not_equal
```

Branch based on `#CMP_FLAG`.

### 8.3 Copying

```text
COPY_LOCAL_GLOBAL local_marker global_marker width
```

Copy a local field from the current rule into a global register.

```text
COPY_GLOBAL_GLOBAL src_marker dst_marker width
```

Copy one global register into another global register.

```text
COPY_HEAD_SYMBOL_TO global_marker width
```

Copy symbol bits from the current simulated head cell into a global register.

Precondition: head is at the simulated head cell's `#CELL`.

```text
COPY_GLOBAL_TO_HEAD_SYMBOL global_marker width
```

Copy a global register into the symbol field of the current simulated head cell.

Precondition: head is at the simulated head cell's `#CELL`.

### 8.4 Writing

```text
WRITE_GLOBAL global_marker literal_bits
```

Overwrite a global register with a literal bitstring.

### 8.5 Simulated Head Movement

```text
MOVE_SIM_HEAD_LEFT
```

Move the `#HEAD` flag from the current simulated cell to the previous encoded
cell.

Precondition:

```text
head is at the current simulated #CELL
```

Postcondition:

```text
old cell has #NO_HEAD
left neighbor has #HEAD
head is at the new head cell's #CELL
```

```text
MOVE_SIM_HEAD_RIGHT
```

Move the `#HEAD` flag from the current simulated cell to the next encoded cell.

Precondition:

```text
head is at the current simulated #CELL
```

Postcondition:

```text
old cell has #NO_HEAD
right neighbor has #HEAD
head is at the new head cell's #CELL
```

The bounded demonstrational implementation may enter `STUCK` when movement
would leave the encoded tape window.

### 8.6 Branching on Current Marker

```text
BRANCH_AT marker label_true label_false
```

Branch according to the marker currently under the runtime head.

## 9. Universal Interpreter Program

For a selected ABI:

```text
state_width  = Wq
symbol_width = Ws
dir_width    = Wd
L_BITS        = encoding of L
R_BITS        = encoding of R
HALT_BITS     = encoding of halt_state
```

Generated Meta-ASM:

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
  COPY_LOCAL_GLOBAL #MOVE  #MOVE_DIR Wd

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

One pass through `START_STEP` implements one simulated source-TM step, unless
the source state is already halting or the encoded machine becomes stuck.

## 10. Lowering to `.tm`

Each Meta-ASM instruction lowers through an explicit compiler pipeline:

```text
Instruction -> Routine -> RoutineCFG -> TMBuilder -> TMTransitionProgram
```

The semantic lowerer does not receive a `TMBuilder` and does not emit raw
transition rows. It returns a `Routine`:

```python
@dataclass(frozen=True)
class Routine:
    name: str
    entry: str
    exits: tuple[str, ...]
    falls_through: bool
    ops: tuple[Op, ...]
    requires: HeadContract = HeadAnywhere()
    ensures: HeadContract = HeadAnywhere()
```

`Routine.entry` and `Routine.exits` are labels supplied by the caller. Any
internal labels in the routine are symbolic; concrete internal state names are
allocated later by `compile_routine`. Fallthrough routines usually have one
exit: the continuation label. Branching or terminal routines name their real
control exits instead:

```python
Goto(label)    -> exits=(label,), falls_through=False
Halt()         -> exits=("__HALT__",), falls_through=False
BranchCmp(a,b) -> exits=(a, b), falls_through=False
Seek(...)      -> exits=(cont,), falls_through=True
```

Routine operations are composable lowering IR nodes such as:

```python
SeekOp(...)
MoveStepsOp(...)
BranchOnBitOp(...)
WriteBitOp(...)
EmitOp(...)
EmitAllOp(...)
EmitAnyExceptOp(...)
```

`compile_routine` turns a routine into a structured CFG:

```python
@dataclass(frozen=True)
class RoutineCFG:
    entry: str
    exits: tuple[str, ...]
    internal_states: tuple[str, ...]
    transitions: tuple[CFGTransition, ...]
```

`CFGTransition` is still structured. It uses the closed `ReadSet` and
`WriteAction` IR unions so wide alphabet cases like "all symbols except marker
X" remain inspectable until the final assembly boundary.

Only final assembly calls `TMBuilder.emit`:

```python
routine = lower_instruction_to_routine(instruction, state=entry, cont=exit)
cfg = compile_routine(routine, NameSupply(routine.name))
validate_cfg(cfg, alphabet)
assemble_cfg(builder, cfg)
```

Program lowering follows the same inspect-before-mutate rule:

```python
cfgs = program_to_cfgs(program)
validate_program_cfgs(cfgs, alphabet)
for cfg in cfgs:
    assemble_cfg(builder, cfg)
```

Every routine defines:

- expected head position before the instruction
- head position after the instruction
- fields and markers it may mutate
- temporary markers it must clean
- continuation behavior

`validate_cfg` checks the generated control graph before raw transition rows
exist. It rejects duplicate `(state, read)` coverage, transitions out of any
routine exit state, unknown transition states, unreachable internal states,
empty read sets, and read/write symbols outside the alphabet.

The final output is:

```python
TMTransitionProgram(
    transitions=...,
    start_state=...,
    halt_state=...,
    alphabet=...,
    blank=...,
)
```

Wrapping that program with ABI metadata yields:

```python
UTMProgramArtifact(
    program=transition_program,
    abi=abi,
)
```

## 11. Lowering Sketches

### 11.1 `SEEK marker dir`

Behavior:

```text
while scanned symbol != marker:
    move dir
continue
```

Lowering:

```text
state seek_marker:
  on marker: goto continuation
  on any other symbol: keep symbol, move dir, stay in seek_marker
```

### 11.2 `COMPARE_GLOBAL_LITERAL marker literal_bits`

Behavior:

```text
seek marker
for each bit in literal_bits:
    move to the bit position
    compare with the expected bit
write #CMP_FLAG
cleanup
```

The first implementation counts fixed-width bit positions in control states.

### 11.3 `COMPARE_GLOBAL_LOCAL global_marker local_marker width`

Behavior:

```text
mark current #RULE as #RULE_ACTIVE
for i in 0..width-1:
    read global bit i
    read local bit i in the active rule
    compare
write #CMP_FLAG
restore #RULE_ACTIVE to #RULE
return to #RULE
```

### 11.4 `COPY_LOCAL_GLOBAL local_marker global_marker width`

Behavior:

```text
mark current #RULE as #RULE_ACTIVE
for i in 0..width-1:
    read local bit i
    write global bit i
restore #RULE_ACTIVE to #RULE
return to #RULE
```

### 11.5 `FIND_HEAD_CELL`

Behavior:

```text
seek #TAPE
repeat:
  seek next #CELL or #END_TAPE
  if #CELL is followed by #HEAD: stop at #CELL
  if #CELL is followed by #NO_HEAD: continue
  if #END_TAPE: goto STUCK
```

### 11.6 `COPY_HEAD_SYMBOL_TO global_marker width`

Behavior:

```text
mark current #CELL as #CELL_ACTIVE
for i in 0..width-1:
    read cell symbol bit i
    write global bit i
restore #CELL_ACTIVE to #CELL
return to #CELL
```

### 11.7 `COPY_GLOBAL_TO_HEAD_SYMBOL global_marker width`

Behavior:

```text
mark current #CELL as #CELL_ACTIVE
for i in 0..width-1:
    read global bit i
    write cell symbol bit i
restore #CELL_ACTIVE to #CELL
return to #CELL
```

### 11.8 `MOVE_SIM_HEAD_RIGHT`

Behavior:

```text
at current #CELL:
  move to head flag
  write #NO_HEAD
  scan right to next #CELL or #END_TAPE
  if #END_TAPE: goto STUCK
  write #HEAD on the next cell
  return to the new #CELL
```

### 11.9 `MOVE_SIM_HEAD_LEFT`

Behavior:

```text
at current #CELL:
  move to head flag
  write #NO_HEAD
  scan left to previous #CELL or #TAPE
  if #TAPE: goto STUCK
  write #HEAD on the previous cell
  return to the new #CELL
```

## 12. Runtime Alphabet

The runtime alphabet contains:

- layout markers
- field markers
- tape-cell markers
- bits `0` and `1`
- active marker variants such as `#RULE_ACTIVE` and `#CELL_ACTIVE`
- marked bit variants when required by a lowering routine
- the runtime blank symbol

Cycle-boundary invariants:

```text
no active markers remain
no marked bits remain
exactly one #HEAD exists in the right band
```

## 13. Correctness Targets

### 13.1 Object Compiler

For a source instance `I`:

```text
decode(Compiler.compile(I).to_band_artifact()) = initial semantic UTM state for I
```

### 13.2 Meta-ASM Interpreter

For a non-halting source configuration with a matching rule:

```text
one Meta-ASM interpreter cycle = one source TM step
```

### 13.3 Lowering

For each Meta-ASM instruction:

```text
lowered transition fragment implements the instruction contract
```

For the full interpreter:

```text
MetaASMProgram.lower() preserves Meta-ASM behavior at label boundaries
```

### 13.4 End-to-End

For source machine `M` and configuration `C`:

```text
Encode(C) --utm.tm*--> Encode(step_M(C))
```

The run continues until halt, stuck, or fuel exhaustion.

## 14. Initial Milestone

The first complete target:

```python
abi = Compiler.infer_abi(instance)
encoded = Compiler(target_abi=abi).compile(instance)

band_artifact = encoded.to_band_artifact()
interpreter = UniversalInterpreter.for_abi(encoded.target_abi)
asm = interpreter.to_meta_asm()

status, final_band, trace, reason = asm.run_host(band_artifact, fuel=...)
```

Expected demonstration:

```text
1011₂ + 1 = 1100₂
```

The next target emits and runs the lowered program:

```python
program_artifact = asm.lower().to_artifact()
result = program_artifact.run(band_artifact, fuel=...)
```

The lowered run should match the host Meta-ASM run at interpreter-cycle
boundaries.
