# Implementation Checklist

- [ ] Update the encoder to accept explicit `state_width`, `symbol_width`, and `dir_width`.
- [ ] Add the structural markers: `#END_FIELD`, `#END_REGS`, `#END_RULE`, `#END_CELL`.
- [ ] Update parsing and pretty-printing for the new encoded outer tape layout.
- [ ] Define Meta-ASM instruction dataclasses and labels.
- [ ] Implement `build_universal_meta_asm(encoding)`.
- [ ] Write a host interpreter for Meta-ASM over the encoded band.
- [ ] Lower the simplest instructions first: `SEEK`, `GOTO`, `HALT`, `FIND_HEAD_CELL`.
- [ ] Add fixed-width compare/copy lowering.
- [ ] Add simulated head movement lowering.
- [ ] Verify the milestone example: `1011₂ + 1 = 1100₂`.
- [ ] Lower Meta-ASM to raw TM and check boundary-equivalent execution.
