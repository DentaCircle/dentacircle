# S2.1a proof

Code these shots were taken against: `ade1c4d` (Keep the care form usable after a plan or item is added).

Clinic: Synthetic Clinic. Staff: Sample Clinician (`care-clinician@x.test`), Sample Desk (`care-desk@x.test`), and the existing inventory admin Test Stock. Patient: Sample Ada. Plan title: Sample plan. Service names: Cleaning, Filling, Crown. No clinical notes.

1. `01-empty-clinician.png` — Signed in as Sample Clinician on a patient with no plans. The page says "No care plans yet." and shows New care plan.
2. `02-three-items.png` — Sample plan with Cleaning Planned, Filling Started, and Crown Completed. The plan badge is Open. Start, Complete, Cancel, and Rename are on the open items. Completed has no actions.
3. `03-complete-confirm.png` — Complete on Crown while it was still Planned. The row asks "Mark as completed?" with Yes and Keep. The "Item added." notice from the previous add is still on the page. Yes was clicked after this frame.
4. `04-receptionist.png` — Signed out, signed in as Sample Desk, same care page. The three items and the Open badge are shown. There is no New care plan, Add item, Start, Complete, Cancel, or Rename.
5. `05-stale-tab.png` — The page still showed Start on Cleaning. A second session marked Cleaning started. Start on the open page reloaded with "This care item has already changed." Cleaning is Started.
6. `06-inactive-patient.png` — Sample Ada was set inactive. Add item for Polish stayed on the form and said "This patient is inactive." Polish was not added.
7. `07-inventory-admin.png` — Signed in as Test Stock. Opening the care page shows "You do not have access."
