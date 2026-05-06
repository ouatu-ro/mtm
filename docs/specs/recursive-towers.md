---
title: Recursive Towers
status: current spec
audience: implementers
---

# Recursive Towers

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
