# Open items

- **Merge base for S1.0.** `slice/S1.0-clinic-day` branches from S0.5. `origin/main`
  currently has a revert of that walking skeleton. Next action: merge or restore S0.5 on
  `main`, then open the S1.0 PR against it.
- **`get_or_create_clinic` matches by display name.** The name is not unique, not trimmed,
  and case-sensitive. Fine for one dev clinic; fragile for multi-clinic provisioning. Next
  action: decide in a later slice whether `create-user` should take `--clinic-id` or a
  stable slug instead.
