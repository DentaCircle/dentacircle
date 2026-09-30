# Open items

- **CI on S0.1 PR.** Confirm the GitHub Actions run is green before merging
  `slice/S0.1-repo-tooling-ci` to `main`. Next action: open the PR and check both jobs.
- **Local Docker.** Docker is not installed on the dev machine, so `make db-up` and the
  database smoke test against a real Postgres were not verified locally. CI runs the smoke
  test. Next action: install Docker Desktop or Colima if you want local database checks.
