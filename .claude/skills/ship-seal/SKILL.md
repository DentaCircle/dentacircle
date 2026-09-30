---
name: ship-seal
description: >-
  Close out a slice after the developer has reviewed and approved it. Use only when the
  developer says the review is approved. Updates the tracker and product state, writes
  the commit or PR text, and proposes the next slice.
---

# Seal

Record finished work so the next session starts from the truth.

## Only after approval

The developer must have said the review is approved. If they asked for changes or have
not reviewed yet, stop and say so. Do not seal on your own judgment.

## Steps

1. Run the full checks once more. If anything fails, stop and report.
2. Set the brief to `Status: done`. Optionally move it to `.shipit/slices/done/`.
3. Tick the slice in ROADMAP.md and update the "Now" line. If a milestone is complete,
   note it and the date.
4. Update the Current state in PRODUCT.md in a few lines. Record any decision made during
   the slice. Do not append a changelog.
5. Put unresolved items in `.shipit/open.md`, each with a next action. Remove items that
   are now resolved. Skip this file if there is nothing to record.
6. Write the commit message or PR description: what changed and why, acceptance criteria
   covered, how to verify, and known limits. Plain words.
7. If the slice took much longer or shorter than its size suggested, add one line to the
   brief with the actual time. This keeps the roadmap honest.

## Finish

Propose the next slice in one line. Do not start it. Suggest `/ship-slice`.

Use plain words and short instructions.
