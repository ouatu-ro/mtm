---
title: Trace Viewer
description: Browser-based trace viewer built from HTML, JavaScript, and trace assets.
audience: engineer
---

# Trace Viewer

The trace viewer is a browser surface built from the existing files in `tools/`:

- `tools/trace-viewer.html`
- `tools/assets/incrementer-raw-trace.js`
- `tools/assets/right-left-walk.tm`
- `tools/assets/right_left_walk_tm.py`

It is an HTML/JS tool with supporting assets, not a library module and not a CLI
subcommand.

The current role of the viewer is to inspect concrete trace data and related
fixture assets while working on debugger and trace workflows.

The viewer sits alongside the debugger specs and the bootstrap results:

- [Debugger REPL Spec](../specs/debugger-repl.md)
- [Debugger Presentation Model Spec](../specs/debugger-presentation.md)
- [L2 Bootstrap Results](../results/l2-bootstrap.md)

