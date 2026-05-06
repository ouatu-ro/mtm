# Meta-TM Compiler Spec

## 1. Goal

Build a staged system where a source-level Turing machine is compiled into an
encoded UTM input band, and a generated universal interpreter executes that band
on an ordinary TM runner.

The two primary emitted runtime artifacts are:

```text
object.l1.tm        lowered universal-machine transition program for level 1
object.l1.utm.band  encoded guest input band for level 1
```

Execution pairs them as:

```text
ordinary TM runner
  program: object.l1.tm
  input:   object.l1.utm.band
```

There are two compilation pipelines:

```text
Source-guest compiler:
  TMInstance
  -> UTMEncoded
  -> UTMBandArtifact

Universal interpreter compiler:
  Encoding
  -> MetaASMProgram
  -> TMTransitionProgram
  -> UTMProgramArtifact
```

The current compiler handles source guests. Recursive self-hosting requires a
second path for raw guests:

```text
Raw-guest compiler:
  RawTMInstance
  -> UTMEncoded
  -> UTMBandArtifact
```

## 2. Public Interface

The current top-level workflow is:

```python
instance = TMInstance(program, band, initial_state=..., halt_state=...)

compiler = Compiler(target_abi=abi)
encoded = compiler.compile(instance)

band_artifact = encoded.to_band_artifact()
band_artifact.write("object.l1.utm.band")

interpreter = UniversalInterpreter.for_encoded(encoded)
asm = interpreter.to_meta_asm()
program_artifact = interpreter.lower_for_band(band_artifact)
program_artifact.write("object.l1.tm")

result = program_artifact.run(band_artifact, fuel=100_000)
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
- `RawTMInstance`
- `DecodedBandView`

Planned missing objects:

- `SourceArtifact`

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
    right_band=("1", "0", "1", "1"),
    head=0,
    blank="_",
)
```

For tapes with explicit negative source addresses:

```python
TMBand.from_dict({-2: "1", 0: "0", 2: "1"}, head=-2, blank="_")
```

Source instance:

```python
TMInstance(
    program=program,
    band=band,
    initial_state="q0",
    halt_state="HALT",
)
```

The source band is a finite demonstrational tape/configuration. The source band
itself may include explicit blank cells when a larger initial simulated window
is desired, and the UTM movement routines can also construct fresh blank cells
at the encoded tape boundaries.

Source well-formedness requires:

```text
TMProgram.blank == TMBand.blank
```

## 4. ABI and Encoding

The object compiler supports two ABI operations:

```python
Compiler().infer_abi(instance) -> TMAbi
Compiler(target_abi=abi).compile(instance) -> UTMEncoded
```

The compiler accepts a selected ABI when:

```text
number_of_states  <= 2^state_width
number_of_symbols <= 2^symbol_width
number_of_dirs    <= 2^dir_width
grammar_version matches
```

Encoding assigns dense IDs:

```text
states:
  qAdd         -> 00000000
  qDone        -> 00000001
  qFindMargin  -> 00000010

symbols:
  "_" -> 00000000
  "0" -> 00000001
  "1" -> 00000010

directions:
  L -> 0
  R -> 1
```

Required property:

```text
decode(encode(x)) = x
```

The blank symbol is always assigned id `0`, so its encoded bitstring is all
zeroes at the selected symbol width.

`TMAbi` is compatibility metadata. `Encoding` is the guest-specific semantic
dictionary used to recover source-level meaning from an encoded band.

Runtime UTM compatibility is a lattice, not exact ABI equality:

```text
band_abi <= host_abi  => executable
band_abi > host_abi   => rejected before execution
```

The encoded band is the authority for guest field lengths and guest constants.
The host UTM's selected widths are upper bounds that keep generated routines
finite. A wider host must not reinterpret a narrower band field by padding or
inheriting host-width literals. Field and cell terminators delimit the actual
guest values at runtime.

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
    left_band=...,
    right_band=...,
    head=...,
    blank=...,
)
```

## 6. `.utm.band` Artifact Layout

Artifact policy:

```text
.utm.band carries guest-specific encoding metadata.
.tm carries host-family ABI metadata, when known.
Raw execution depends on neither encoding nor ABI.
Semantic decoding depends on encoding.
Compatibility checks depend on ABI.
```

`UTMBandArtifact` serializes the semantic UTM object into a concrete split
encoded band:

```text
left band:   encoded negative simulated tape region
             + #TAPE_LEFT
             + registers
             + transition rules
right band:  encoded nonnegative simulated tape region
```

Runtime materialization:

```text
... left_band[-3] left_band[-2] left_band[-1] | right_band[0] right_band[1] right_band[2] ...
                                               ^
                                               split point between -1 and 0
```

The left band is placed at negative addresses. The right band starts at address
`0`. The simulated tape head is represented by a `#HEAD` marker inside either
the negative simulated tape region or the nonnegative tape region. The raw
runtime start head for the host is stored separately as `start_head`, usually at
the registry entry point rather than at the simulated tape head.

Current `.utm.band` files persist:

- concrete encoded band contents
- `encoding`
- `start_head`
- `target_abi`
- `minimal_abi`
- file format version

### 6.1 Left Band

The left band starts with the negative side of the simulated source tape:

```text
#END_TAPE_LEFT
  #CELL #NO_HEAD <symbol_bits> #END_CELL
  ...
#TAPE_LEFT
```

The negative source cells are placed to the left of `#TAPE_LEFT`. `#TAPE_LEFT`
itself is fixed. Left growth overwrites the old `#END_TAPE_LEFT` with the new
blank cell's `#END_CELL`, writes the rest of that blank cell to the left, and
writes a new `#END_TAPE_LEFT` one cell-width farther left. It does not move
`#TAPE_LEFT` or the registry/rule area.

After `#TAPE_LEFT`, the same physical left band contains registers and
transition rules:

```text
#REGS
  #CUR_STATE     <state_bits>  #END_FIELD
  #CUR_SYMBOL    <symbol_bits> #END_FIELD
  #WRITE_SYMBOL  <symbol_bits> #END_FIELD
  #NEXT_STATE    <state_bits>  #END_FIELD
  #MOVE_DIR      <dir_bits>    #END_FIELD
  #HALT_STATE    <state_bits>  #END_FIELD
  #BLANK_SYMBOL  <symbol_bits> #END_FIELD
  #LEFT_DIR      <dir_bits>    #END_FIELD
  #RIGHT_DIR     <dir_bits>    #END_FIELD
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

`#HALT_STATE`, `#BLANK_SYMBOL`, `#LEFT_DIR`, and `#RIGHT_DIR` are copied from
the band's guest encoding. They prevent the generated UTM from baking
host-width halt, blank, or direction literals into runtime decisions.

### 6.2 Right Band

The right band contains the nonnegative side of the simulated source tape:

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

The head may be on either the negative side before `#TAPE_LEFT` or the
nonnegative side after `#TAPE`, but not both.

### 6.3 Field Widths

Generated bands use one fixed payload width per field kind:

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

The band width is the semantic width of that encoded guest. A host UTM may use
wider maximum widths, but runtime comparison and copying must treat the
terminators as the actual field boundaries.

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

Comparison is width-bounded and delimiter-aware. `width` is the host maximum
payload width. The routine compares at most `width + 1` positions: up to
`width` payload bits plus the terminator position. Equality succeeds when the
two streams match through the terminator. This preserves exact-ABI behavior and
also allows a wider host UTM to run a valid narrower band without padding the
band's fields.

```text
COMPARE_GLOBAL_GLOBAL lhs_marker rhs_marker width
```

Compare two global register fields using the same width-bounded,
delimiter-aware rule.

```text
COMPARE_GLOBAL_LITERAL global_marker literal_bits
```

Compare a global register field against a literal bitstring.

Literal comparison is only appropriate for host-owned constants. Guest-owned
values whose width depends on the band, such as halt state and directions, must
be represented as delimited band fields and compared with
`COMPARE_GLOBAL_LOCAL` or `COMPARE_GLOBAL_GLOBAL`.

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

Copy routines copy delimited source payloads, subject to the same `width + 1`
upper bound. Field-to-field copies may overwrite through the field terminator.
Cell-to-field and field-to-cell symbol copies stop at the source terminator and
preserve the destination's own terminator shape. Generated bands are expected to
keep same-kind fields at the same guest width, so copy does not resize or shift
destination fields.

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

When movement reaches `#END_TAPE` or `#END_TAPE_LEFT`, the lowered
implementation constructs a fresh blank cell using the band-carried
`#BLANK_SYMBOL` payload. It may enter `STUCK` on malformed layouts or failed
structural searches.

### 8.6 Branching on Current Marker

```text
BRANCH_AT marker label_true label_false
```

Branch according to the marker currently under the runtime head.

## 9. Universal Interpreter Program

For a selected host encoding, whose widths come from `target_abi`:

```text
Wq = encoding.state_width
Ws = encoding.symbol_width
Wd = encoding.direction_width
```

These widths are upper bounds for runtime routines. Guest-owned constants are
read from the encoded band:

```text
#HALT_STATE
#BLANK_SYMBOL
#LEFT_DIR
#RIGHT_DIR
```

Generated Meta-ASM:

```text
LABEL START_STEP
  COMPARE_GLOBAL_GLOBAL #CUR_STATE #HALT_STATE Wq
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

LABEL DISPATCH_MOVE
  COMPARE_GLOBAL_GLOBAL #MOVE_DIR #LEFT_DIR Wd
  BRANCH_CMP MOVE_LEFT CHECK_RIGHT

LABEL CHECK_RIGHT
  COMPARE_GLOBAL_GLOBAL #MOVE_DIR #RIGHT_DIR Wd
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
Halting is checked only at the step boundary. A transition whose `#NEXT` is
the guest halt state still performs its write, move, and state update; the next
`START_STEP` then halts because `#CUR_STATE` matches `#HALT_STATE`.

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
    prog=...,
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
    target_abi=abi,
)
```

Current `.tm` serialization persists:

- raw transition table
- start state
- halt state
- alphabet
- blank
- optional `target_abi`
- optional `minimal_abi`

ABI on `.tm` is optional compatibility/provenance metadata and must not be an
execution dependency.

If both a `.tm` artifact and a `.utm.band` artifact carry `target_abi`,
tooling should reject:

- mismatched `grammar_version`
- `band_abi > host_abi`

before execution starts. A host with wider state, symbol, or direction widths
may run a narrower band. If `.tm` ABI metadata is absent, execution is still
allowed and compatibility remains unchecked.

## 11. Artifact Naming and Tower Workflow

Level numbers describe how many UTM layers the guest has been wrapped in.

Recommended artifact names:

```text
incrementer.py            authoring format
incrementer.mtm.source    serializable source artifact

incrementer.l1.utm.band   encoded source guest for level 1
incrementer.l1.tm         lowered host for level 1

incrementer.l2.utm.band   encoded raw guest for level 2
incrementer.l2.tm         lowered host for level 2
```

Level-1 compilation:

```text
incrementer.py
  -> incrementer.l1.utm.band
  -> incrementer.l1.tm
```

Level-2 compilation uses the raw-guest path:

```text
guest program = incrementer.l1.tm
guest runtime tape = incrementer.l1.utm.band materialized runtime tape

(guest program, guest runtime tape)
  -> incrementer.l2.utm.band
  -> incrementer.l2.tm
```

The host at each level is allowed to be encoding-specific under the current
implementation. True ABI-family-only hosts are a separate cleanup, not a
prerequisite for recursive towers.

Level meanings:

```text
l1 artifacts run the original source guest under one UTM layer.
l2 artifacts run the l1 raw host computation as the guest under another UTM layer.
l3 repeats the same wrapping process again.
```

## 12. Lowering Sketches

### 12.1 `SEEK marker dir`

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

### 12.2 `COMPARE_GLOBAL_LITERAL marker literal_bits`

Behavior:

```text
seek marker
for each bit in literal_bits:
    move to the bit position
    compare with the expected bit
write #CMP_FLAG
cleanup
```

The first implementation counted fixed-width bit positions in control states.
The ABI-compatible implementation still uses width-counting as a maximum guard,
but field equality and copy completion are delimited by `#END_FIELD` or
`#END_CELL`.

### 12.3 `COMPARE_GLOBAL_LOCAL global_marker local_marker width`

Behavior:

```text
mark current #RULE as #ACTIVE_RULE
for i in 0..width:
    read global item i
    read local item i in the active rule
    compare bits or matching terminators
    if matching terminators: succeed
    if mismatch: fail
write #CMP_FLAG
restore #ACTIVE_RULE to #RULE
return to #RULE
```

`COMPARE_GLOBAL_GLOBAL lhs_marker rhs_marker width` uses the same loop without
the `#ACTIVE_RULE` marker bookkeeping, because both compared fields live in
`#REGS`.

### 12.4 `COPY_LOCAL_GLOBAL local_marker global_marker width`

Behavior:

```text
mark current #RULE as #ACTIVE_RULE
for i in 0..width:
    read local item i
    write global item i
    if local item is the expected terminator: stop
restore #ACTIVE_RULE to #RULE
return to #RULE
```

### 12.5 `FIND_HEAD_CELL`

Behavior:

```text
seek #TAPE
repeat:
  seek next #CELL or #END_TAPE
  if #CELL is followed by #HEAD: stop at #CELL
  if #CELL is followed by #NO_HEAD: continue
  if #END_TAPE: goto STUCK
```

### 12.6 `COPY_HEAD_SYMBOL_TO global_marker width`

Behavior:

```text
for i in 0..width:
    read the item at offset i from the current headed cell
    if the item is #END_CELL: stop
    seek the target global field
    write that item
    seek back to the simulated #HEAD cell when another item remains
```

### 12.7 `COPY_GLOBAL_TO_HEAD_SYMBOL global_marker width`

Behavior:

```text
for i in 0..width:
    read the global item at offset i
    if the item is #END_FIELD: stop
    seek the current headed cell
    write the corresponding symbol item
    return to the global field when another item remains
```

### 12.8 `MOVE_SIM_HEAD_RIGHT`

Behavior:

```text
at current #CELL:
  move to head flag
  write #NO_HEAD
  scan right to next #CELL, #TAPE_LEFT, or #END_TAPE
  if #TAPE_LEFT: jump right over registers/rules to #TAPE and continue
  if #END_TAPE: construct a blank right cell
  write #HEAD on the next cell
  return to the new #CELL
```

### 12.9 `MOVE_SIM_HEAD_LEFT`

Behavior:

```text
at current #CELL:
  move to head flag
  write #NO_HEAD
  scan left to previous #CELL, #TAPE, or #END_TAPE_LEFT
  if #TAPE: jump left over registers/rules to #TAPE_LEFT and continue
  if #END_TAPE_LEFT: move #END_TAPE_LEFT left and construct a blank left cell
  write #HEAD on the previous cell
  return to the new #CELL
```

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

## 15. Milestones and Current Results

The initial complete target compiles and runs a source TM under one UTM layer:

```python
abi = Compiler().infer_abi(instance)
encoded = Compiler(target_abi=abi).compile(instance)

band_artifact = encoded.to_band_artifact()
interpreter = UniversalInterpreter.for_encoded(encoded)
asm = interpreter.to_meta_asm()
program_artifact = interpreter.lower_for_band(band_artifact)
result = program_artifact.run(band_artifact, fuel=...)
```

Expected and current demonstration:

```text
1011₂ + 1 = 1100₂
```

The level-1 artifact path emits and runs the lowered program:

```python
program_artifact.write("incrementer.l1.tm")
result = program_artifact.run(band_artifact, fuel=...)
```

Recursive self-hosting through `RawTMInstance` and levelled artifacts now emits
L2 artifacts such as:

```text
incrementer.l2.utm.band
incrementer.l2.tm
```

Current result notes:

- L1 raw execution reaches `1100`.
- L2 MetaASM C execution reaches the encoded L1 final tape for `1100`.
- The real lowered L2 raw host can run the narrower L1 band and reaches `1100`.
- The full lowered L2 raw run is currently estimated in weeks on the local C
  raw runner.

See `docs/results/l2-bootstrap.md` for the current measurements and backend
experiments.
