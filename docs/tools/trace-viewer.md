---
title: Trace Viewer
description: Browser-based trace viewer built from HTML, JavaScript, and trace assets.
audience: engineer
---

# Trace Viewer

The trace viewer is a browser surface built from the viewer file, its fixture
bundle, and the example inputs that generated that bundle:

- `tools/trace-viewer.html`
- `tools/trace-viewer-assets/fixtures.js`: bundled fixture data for `tools/trace-viewer.html`
- `examples/raw/right-left-walk.tm`
- `examples/source/right_left_walk_tm.py`

It is an HTML/JS tool with supporting assets, not a library module and not a CLI
subcommand.

The current role of the viewer is to inspect concrete trace data and related
fixture assets while working on debugger and trace workflows.

The viewer sits alongside the debugger docs and the bootstrap results:

- [Debugger REPL Spec](../specs/debugger-repl.md)
- [Debugger Stepper Layers](../architecture/debugger-stepper.md)
- [L2 Bootstrap Results](../results/l2-bootstrap.md)
