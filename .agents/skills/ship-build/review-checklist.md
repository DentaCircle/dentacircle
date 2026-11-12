# Review checklist

For the agent's self-review and for the developer's own review of the diff.

## Tenancy and access
- Does every new query filter by `clinic_id`? Can one clinic ever read another's rows?
- Does every new endpoint declare its allowed roles? Is the default deny?
- Does the UI hide things the API would refuse, and does the API refuse them anyway?

## Data and migrations
- Is the migration additive? Is there a safe path back? Are indexes and constraints present
  (unique, foreign key, not null) for the rules the code assumes?
- Are money, dates and times stored in sane types? Are time zones handled on purpose?
- Are stock and status changes done in one transaction?

## Business rules
- Is the rule in a service or domain function, not in a route or a React component?
- Are the edge cases covered: double booking, cancelling a completed appointment,
  negative stock, a follow-up created twice?
- Are invalid state transitions rejected?

## Safety and privacy
- Any patient data in logs, errors, fixtures or test names?
- Any place where AI output could change state without a validated service call?
- Is an `AuditEvent` written for each state change that AGENTS.md lists?

## Code quality
- Can you explain every function? Is anything clever that could be plain?
- Error paths: what does the user see, what gets logged, is anything swallowed?
- Do the tests fail if the behavior breaks, or do they only run the code?
- Anything unused, duplicated, or added "for later"?
