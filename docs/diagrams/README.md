# Diagrams

| Image (`../img/`) | Source here | How it is made |
|---|---|---|
| `architecture.svg` | none (drawn by hand as SVG) | edit the SVG directly |
| `jd-analysis-sequence.svg` | `jd-analysis-sequence.mmd` | exported from Mermaid |
| `subagent-replay-sequence.svg` | `subagent-replay-sequence.mmd` | exported from Mermaid |
| `fit-and-tuning-states.svg` | `fit-and-tuning-states.mmd` | exported from Mermaid |

After editing a `.mmd`, regenerate its SVG: run `python3 docs/diagrams/export.py`, open http://127.0.0.1:8765 in a browser, wait for "done", then stop the script. It needs an internet connection to load the Mermaid library.
