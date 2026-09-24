---
name: calculations
description: Perform reproducible technical calculations with local Python, units, assumptions and numerical checks.
---

# Calculations

State inputs, units, sign conventions, formulas and assumptions before choosing
precision. Link external inputs to their sources; distinguish nominal, measured,
minimum, maximum and estimated values. Convert units explicitly and keep useful
precision internally; round the presented result to the evidence's precision.

Use `/opt/ai-harness-python/bin/python` for saved calculation scripts within the
workspace. The image contract provides Python's standard library, NumPy, SciPy,
SymPy and Matplotlib. Use `decimal` or `fractions` when decimal or rational
exactness matters, NumPy/SciPy for numerical work and SymPy for symbolic algebra.
Do not evaluate user-supplied expressions through unrestricted `eval` or `exec`;
write the intended calculation as explicit code.

Check dimensions, plausible magnitude, limiting cases and denominator/domain
restrictions. For a fit or simulation state the model, sampling assumptions,
random seed when applicable, and whether error bars describe measurement error,
model uncertainty or sampling variation. Check a numerical answer independently
when cancellation, conditioning or convergence affects the conclusion.

For a plot, save an artifact under the workspace using Matplotlib's noninteractive
`Agg` backend. Label axes and units, retain the script and input values, and inspect
the plotted range. A graph generated from assumed values is illustrative, not
measured evidence. Present the answer with enough formula and source detail for
another person to reproduce it; call out unresolved inputs rather than inventing
extra precision.
