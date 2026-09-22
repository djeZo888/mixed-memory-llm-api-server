# PDF helper notices and provenance

`pdf_tools.py` and its tests are first-party MIT code. This implementation was
written for the bounded H001-TOOLS task. It uses a selected-page / rasterize /
visually-verify workflow reviewed against these MiniMax Code files at exact
revision `ae65651df5f97ae1085ab4e19964f4b78c769a4e`:

- `packages/local-runtime/assets/skills/pdf/SKILL.md`
- `packages/local-runtime/assets/skills/pdf/docs/read-guide.md`
- `packages/local-runtime/assets/skills/pdf/scripts/render/page_rasterize.py`
- `packages/local-runtime/assets/skills/pdf/scripts/render_html.cjs`

Source: https://github.com/MiniMax-AI/minimax-code/tree/ae65651df5f97ae1085ab4e19964f4b78c769a4e/packages/local-runtime/assets/skills/pdf

No upstream renderer code, automatic package installation, remote-URL rendering,
Matrix/cloud vision fallback, global Playwright lookup, or sandbox-disabling
behavior is incorporated. The upstream MIT notice is retained in
`MINIMAX-LICENSE.txt` for workflow adaptations. It does not relicense dependency
code. `dependency-notices.json` records exact Python dependencies and their
upstream metadata/source links. Preserve their installed distribution licenses
when assembling the image; Poppler, Tesseract and Chromium retain their own
licenses and package notices. These packages are not first-party MIT code.
