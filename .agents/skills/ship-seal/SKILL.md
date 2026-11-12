---
name: ship-seal
description: >-
  Close out a slice when the developer asks to seal it. A separate post-build review
  approval is not required. Updates the tracker and product state, writes the commit or
  PR text, and proposes the next slice.
---

# Seal

Record finished work so the next session starts from the truth.

## When requested

Run this skill only when the developer asks to seal the slice and explicitly says the
review is approved. A request to seal alone is not enough. If the developer asks for
changes instead, make those changes and do not seal unless they also ask to seal and
approve the review.

## Steps

1. Before changing status or the roadmap, confirm `.shipit/proof/<slice>/index.md` exists.
   For a visible change, inspect every screenshot for patient data. Stop if proof is missing
   or contains real patient data. For an API-only slice, confirm sample requests and
   responses are present instead.
2. Run the full checks once more. If anything fails, stop and report.
3. Set the brief to `Status: done`. Optionally move it to `.shipit/slices/done/`.
4. Tick the slice in ROADMAP.md and update the "Now" line. If a milestone is complete,
   note it and the date.
5. Update the Current state in PRODUCT.md in a few lines. Record any decision made during
   the slice. Do not append a changelog.
6. Put unresolved items in `.shipit/open.md`, each with a next action. Remove items that
   are now resolved. Skip this file if there is nothing to record.
7. If the slice took much longer or shorter than its size suggested, add one line to the
   brief with the actual time. This keeps the roadmap honest.
8. Commit the seal changes (tracker, product state, brief) on the slice branch.
9. Raise the PR (see below).

## Raise the PR

Every slice ends in a PR that uses `.github/pull_request_template.md`. Never merge it.

1. Push the branch: `git push -u origin <branch>`.
2. Fill in the template in a temp file, every section, in plain words. Keep it short:
   the brief remains the detailed record of acceptance criteria and test coverage.
   - Capabilities: three to seven bullets describing what people or the system can now
     do. Include a role or business constraint only when it defines the capability.
   - Scenarios shown: choose the distinct screenshots that best explain those
     capabilities. Introduce each with a scenario naming the starting role or state,
     the action, and the visible outcome. Embed it as `![caption](url)`. The URL is
     pinned to the pushed commit, not the branch name:
     `https://github.com/<owner>/<repo>/blob/<commit-sha>/.shipit/proof/<slice>/<file>.png?raw=true`
     Get `<owner>/<repo>` from `git remote get-url origin` and the sha from
     `git rev-parse HEAD`.
   - Verification: summarize the real check results in one line. Add a short manual
     path only when it helps explain the feature. Do not claim a check that was not run.
   - Limits: include only important behavior deliberately left out. Write "None" when
     there is nothing useful to record.
3. Run `gh pr create --base main --head <branch> --title "<slice id> <name>" --body-file <file>`.
   If `gh` is missing, not signed in, or fails, do not retry in loops. Give the developer
   the compare link instead, with the filled body saved to a file they can paste:
   `https://github.com/<owner>/<repo>/compare/main...<branch>?expand=1`
4. Show the PR link in chat and open the PR page in a way the developer can check the
   images render. If they do not render (private repo, wrong URL), say so and fix the URLs.

## Finish

Propose the next slice in one line. Do not start it. Suggest `$ship-slice`.

Use plain words and short instructions.
