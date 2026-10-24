# S3.3 proof: lab work

Taken at commit `5279b4c` on `slice/S3.3-lab-work`.
Real app: API on :8000, web on :3000, local Postgres, synthetic data only.
Clinic: Synthetic Clinic. Staff: Synthetic Desk (`s33.desk@x.test`, receptionist and clinician), Synthetic Stores (`s33.inventory@x.test`, inventory_admin). Patient: Sample Lila, phone 9000000033, display id P-0011. The empty Lab shot is a second clinic, Synthetic Empty Clinic, signed in as Synthetic Empty (`s33.empty@x.test`). The password is the one set with `make create-user` for this proof session.

## Screenshots

| File | What it shows | Steps |
| --- | --- | --- |
| `01-patient-lab.png` | Sample Lila's Lab page: Denture collected, Bridge ready, Crown pending and Overdue. | Add the three items. Mark Denture ready, then collected. Mark Bridge ready. Set Crown's expected date to 23 Oct 2026 in the database, then open `/patients/{id}/lab`. |
| `02-add-validation.png` | Add form with "Enter a title." | Open the Lab page and press Add lab work with an empty title. |
| `03-clinic-open.png` | Open view. Crown is Overdue. Bridge is ready and has no Overdue badge. | Open `/lab`. |
| `04-clinic-all.png` | All view, with Denture collected and no row buttons. | Open `/lab?view=all`. |
| `05-empty.png` | "No lab work is open." | Sign in to Synthetic Empty Clinic and open `/lab`. |
| `06-follow-ups.png` | Sample Lila due today after a ready move. | Follow-ups, Due. |
| `07-documents-linked.png` | "Documents for Crown", `result.png`, and Unlink. | Documents on the Crown row. |
| `08-link-existing.png` | The existing-document list expanded, with Link on `other.png`. | On that page, press "Link a document that is already uploaded". |
| `09-viewer.png` | Viewer text "Lab work: Crown, Pending". | Open `result.png`. |
| `10-timeline.png` | Lab rows, the follow-up row, and the two uploads. | Patient timeline. |
| `11-inactive.png` | Upload form hidden, and Unlink refused with "This patient is inactive." | Mark Sample Lila inactive, open Crown's documents, press Unlink. The Lab page for the same patient hides the add form and says lab work cannot be added. |
| `12-inventory.png` | "You do not have access." | Sign in as the inventory admin and open `/lab`. |

Honest notes:

- The browser pane is narrow, so the clinic and follow-up tables wrap. The Overdue badge, the ready row without that badge, and Sample Lila due today are on the shots.
- Crown was created with expected date 24 Oct 2026. The create API refuses a past date, so the overdue shot uses a database update to 23 Oct 2026 after the row existed.
- The Next.js dev-tools button is on the shots. It is the dev server, not part of the page.

## Sample API calls

Signed in as Synthetic Desk. Patient Sample Mira, P-0012. Title sent as `" Crown "` and stored as `Crown`.

```
POST /patients/{mira}/lab-work
{"title":" Crown ","expected_on":"2026-10-30"}

HTTP 201
{"status":"pending","title":"Crown","expected_on":"2026-10-30","overdue":false,"appointment":null}
```

```
POST /lab-work/{id}/status
{"status":"ready"}

HTTP 200
{"status":"ready","title":"Crown","overdue":false}
```

```
GET /lab-work?view=open&page=1&page_size=2

HTTP 200
{"total":3,"page":1,"page_size":2}
first item: pending, Crown, expected_on 2026-10-23, overdue true
```

```
PATCH /patients/{mira}/documents/{id}
{"lab_work_id":null}

HTTP 200
{"filename":"result.png","lab_work":null}
```

The file had been uploaded with `?lab_work_id={id}` and the 201 body included `lab_work.title` Crown.

```
GET /patients/{mira}/documents?lab_work_id={id}

HTTP 200
{"total":0,"items":[]}
```

```
POST /lab-work/{id}/status
{"status":"pending"}

HTTP 409
{"error":{"code":"invalid_status","message":"This lab work has already changed."}}
```

```
GET /lab-work/00000000-0000-4000-8000-000000000099

HTTP 404
{"error":{"code":"not_found","message":"Not Found"}}
```
