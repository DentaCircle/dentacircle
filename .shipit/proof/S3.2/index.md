# S3.2 proof: document viewer and links

Taken at web commit `d04f4b7` (API commit `a65b1aa`, branch `slice/S3.2-document-viewer-and-links`).
Real app: API on :8000, web on :3000, local Postgres, synthetic data only.
Clinic: Synthetic Clinic. Staff: Synthetic Desk (`s32.desk@x.test`, receptionist and clinician), Synthetic Stores (`s32.inventory@x.test`, inventory_admin). Patient: Sample Noor, phone 9000000032, display id P-0010. The password is the one set with `make create-user` for this proof session.

## Screenshots

| File | What it shows | Steps |
| --- | --- | --- |
| `01-viewer-png.png` | Viewer for `chairside.png`: name, PNG, size, who and when, Download, and the image. No "Open in new tab". | Open `/patients/{id}/documents/{png id}`. The image loads from `.../file?disposition=inline`. |
| `02-viewer-pdf.png` | Viewer for `report.pdf` with Download and "Open in new tab", plus the visit line as text. | Open the PDF document. The page has no iframe. |
| `03-calendar-documents.png` | Completed visit row with a Documents link. | Calendar, day view, 23 Oct 2026. The visit is Consultation 10:00, Completed. |
| `04-visit-documents.png` | Filtered visit page: heading, Show all documents, Document linked, `report.pdf` with Unlink. | Calendar Documents link. Link `report.pdf`. The row is still there after reload. |
| `05-link-existing.png` | "Link a document that is already uploaded" expanded, with Link on the other files. | On the visit page, before linking, expand that control. |
| `06-follow-up-queue.png` | Follow-up queue, All open, with Documents on each row, including Sample Noor. | Follow-ups, All open. |
| `06b-follow-up-documents.png` | Filtered follow-up page: heading with the due date, `scan.png`, Unlink. | Documents on Sample Noor's follow-up (due 30 Oct 2026), after linking `scan.png`. |
| `07-timeline.png` | "Document uploaded" rows for chairside.png, report.pdf and scan.png. | Patient timeline. The chairside row opens the viewer. |
| `08-inactive-refused.png` | Unlink refused: "This patient is inactive." Upload form is hidden. The row stays. | Mark the patient inactive, open the visit documents page, press Unlink. |
| `09-inventory-no-access.png` | "You do not have access." | Sign in as the inventory admin and open the Documents URL. The viewer URL shows the same sentence. |

Honest notes:

- The completed visit was booked for the next day, then its start time was moved to today in the database so the status buttons would accept it. A future visit cannot be marked completed, and a visit in the past cannot be booked. The Documents link is the same row the calendar uses for every status.
- Shot 05 was taken before the link. Shot 04 is the same page after Link and the notice. Reload of the filtered list still returned `report.pdf`.
- Shot 06 is the queue. Shot 06b is the filtered page the queue link opens. They are two screens, so they are two files.

## Sample API calls

Inline PNG. CSP is present. PDF inline below has no CSP.

```
GET /patients/{id}/documents/{png id}/file?disposition=inline

HTTP 200
content-disposition: inline; filename="chairside.png"; filename*=UTF-8''chairside.png
content-length: 132
content-type: image/png
x-content-type-options: nosniff
cache-control: private, no-store
content-security-policy: sandbox; default-src 'none'
```

```
GET /patients/{id}/documents/{pdf id}/file?disposition=inline

HTTP 200
content-disposition: inline; filename="report.pdf"; filename*=UTF-8''report.pdf
content-length: 22
content-type: application/pdf
x-content-type-options: nosniff
cache-control: private, no-store
```

PATCH set a visit. The body has the document item, including the live visit.

```
PATCH /patients/{id}/documents/{png id}
{"appointment_id":"<visit id>"}

HTTP 200
{"id":"<png id>","filename":"chairside.png","content_type":"image/png","size_bytes":132,
 "uploaded_at":"2026-10-23T22:17:59.890180+05:30",
 "uploaded_by":{"id":"<user id>","name":"Synthetic Desk"},
 "appointment":{"id":"<visit id>","starts_at":"2026-10-23T10:00:00+05:30","type_name":"Consultation"},
 "follow_up":null}
```

PATCH a visit id that is not this patient's. The body has no filename and no id.

```
PATCH /patients/{id}/documents/{png id}
{"appointment_id":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}

HTTP 404
{"error":{"code":"not_found","message":"Not Found","request_id":"bf538486-d328-49b6-bd87-78559ea3ae80"}}
```

PATCH while the patient is inactive.

```
PATCH /patients/{id}/documents/{png id}
{"appointment_id":null}

HTTP 409
{"error":{"code":"patient_inactive","message":"This patient is inactive.","request_id":"b8721f74-5a2b-4e1b-a0a5-65613afa2339"}}
```

Filtered list for the visit. Only documents linked to that visit.

```
GET /patients/{id}/documents?appointment_id=<visit id>

HTTP 200
{"items":[ chairside.png with the Consultation link, report.pdf with the same link ],
 "total":2,"page":1,"page_size":20}
```
