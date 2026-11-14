# Example: explaining how the token audit works

The `explaining-how-it-works` skill applied to real code in this repo. The question: *"How does the token audit get from my agent's API call to the report page?"*

| File | What it is |
|---|---|
| `explainer.json` | The explainer: seven plain steps, nine traced hops with file:line, one external service card, failure modes, debug notes, and the four diagram specs |
| `out/index.html` | The page. Open it in a browser |
| `out/diagrams/*.svg` | The four views: context, containers, components, sequence |
| `out/diagrams/*.excalidraw` | The same views, editable at excalidraw.com (☰ → Open) |

Rebuild from the repo root:

```bash
python3 src/engineering/explaining-how-it-works/scripts/build_explainer.py test/example-how-it-works/explainer.json test/example-how-it-works/out
```
