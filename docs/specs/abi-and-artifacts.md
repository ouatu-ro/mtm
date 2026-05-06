---
title: ABI and Artifacts
status: current spec
audience: implementers
---

# ABI and Artifacts

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

