---
name: ws-guide
description: Open the Workstreams guide PDF — the human-readable manual for the ws-* workflow. Use when the user asks to see, read, or open the workstreams guide, manual, handbook, or docs, or wants an overview of how the workstream workflow fits together.
metadata:
  version: "0.6.0"
  author: Caio Ariede
---

# ws-guide — open the guide

Open the bundled guide for the user (relative to this skill's directory):

- macOS: `open assets/WORKSTREAMS-GUIDE.pdf`
- Linux: `xdg-open assets/WORKSTREAMS-GUIDE.pdf`

That's the whole job — open it and confirm; don't summarize the PDF unless asked. For the machine-readable contract (store layout, IDs, flavors), that's the `ws` skill, not this guide.

The PDF is generated from `assets/WORKSTREAMS-GUIDE.html` via `just gen-guide-pdf` at the plugin root — if the user asks to update the guide, edit the HTML and regenerate.
