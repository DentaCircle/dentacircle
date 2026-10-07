# Open items

- **Merge base for S1.0.** `origin/main` already contains S0.5, including migration
  `0002_auth`. Before merging the S1.0 PR, confirm `slice/S1.0-clinic-day` is aligned with
  current `main` (merge or rebase as needed).
- **`get_or_create_clinic` matches by display name.** The name is not unique, not trimmed,
  and case-sensitive. Fine for one dev clinic; fragile for multi-clinic provisioning. Next
  action: decide in a later slice whether `create-user` should take `--clinic-id` or a
  stable slug instead.
