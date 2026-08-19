# Debug Session: hex-edit-send-loss

Status: [OPEN]

## Symptom

Selected flow 1 -> switch to Hex -> Edit and replay -> auto switches to new flow 2 -> add a few characters in flow 2 Hex -> click Send -> added characters disappear.

## Hypotheses

1. Hex edits are not tracked as the active source tab, so Send saves from Raw instead of Hex.
2. Switching between session 1 and session 2 re-renders Hex from the underlying flow and overwrites pending text edits.
3. Save/apply logic on Send reads stale widget state after the tab or session changes.
4. Hex edits are converted through a text path that strips trailing characters or normalizes line structure before bytes are written back.
5. A tab-change handler or stale-tab refresh path re-populates Hex just before Send, discarding the user's last input.

## Reproduction Notes

- Session 1: open a flow, switch to Hex, use edit and replay.
- Session 2: in Hex, append arbitrary characters.
- Click Send.
- Observe appended characters disappear.

## Evidence Log

- Static evidence confirmed `apply_request_edits` writes Hex bytes to `req.content`, then immediately marks Hex stale and re-renders the current tab.
- In the reported reproduction, the current tab is Hex, so the just-entered suffix is replaced by the normalized hex dump generated from flow content.
- Minimal fix: skip immediate current-tab re-render when the edit source is Hex. Other tabs remain stale and will refresh on demand.

## Fix

- `InspectorPanel.apply_request_edits`: after saving Hex edits, do not call `_render_tab` for the active Hex tab.
- Syntax and IDE diagnostics passed.
