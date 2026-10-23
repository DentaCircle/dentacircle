# S3.1 proof: document upload

Taken at code commit `f8ad115` (branch `slice/S3.1-document-upload`).
Real app: API on :8000, web on :3000, a throwaway Postgres DB, synthetic data only.
Screen size is a phone width (about 620 px).

## Screenshots

| File | What it shows | Steps |
| --- | --- | --- |
| `01-documents-list.png` | Documents page with rows: name, type pill, size, uploader, time, Download link | Sign in as the desk user. Patient page, then Documents. |
| `02-empty-state.png` | Empty state for a patient with no documents | Open Documents for a patient with no uploads. |
| `03-refused-too-large.png` | A file over 8 MB is refused in the browser, nothing is sent | Choose a file bigger than 8 MiB, press Upload. |
| `04-refused-wrong-type.png` | A file that is not PDF, PNG or JPEG is refused in the browser | Choose a `.gif`, press Upload. |
| `05-no-access.png` | A role without document access sees "You do not have access." | Sign in as the inventory admin user, open a Documents URL. |
| `06-inactive-patient.png` | Inactive patient: old files can be downloaded, upload form is gone, reason is shown | Mark a patient inactive, open Documents. |
| `07-patient-page-button.png` | "Documents" button on the patient page; the buttons wrap on a narrow screen | Open a patient page. |
| `08-upload-success.png` | After a good upload the list shows the new row and the notice | Choose a small PDF, press Upload. |

Honest notes:

- Shots 03, 04 and 08 set the file input from a page script (the browser tool cannot open a
  file picker). The form logic that runs afterwards is the real one.
- Shot 03 uses a `File` object whose `size` was spoofed to look bigger than 8 MiB, to test the
  browser pre-check. The real size limit is proved by the API request below, with a real
  9 MiB body.
- Shot 07 was taken as a user who has the inventory_admin and receptionist roles. The first
  attempt (before the wrap fix) showed the "Patients" link cut off; the fix is commit
  `f8ad115`.

## Sample API calls (through the web proxy, `localhost:3000/api`)

Upload a PDF. The body is the raw file, the name is in the query.

```
POST /patients/{patient_id}/documents?filename=Sample%20xray%20note.pdf
Content-Type: application/pdf

HTTP 201
{"id":"48e16c0d-...","filename":"Sample xray note.pdf","content_type":"application/pdf",
 "size_bytes":26,"uploaded_at":"2026-10-23T18:12:43+05:30",
 "uploaded_by":{"id":"d66f7532-...","name":"Sample Desk"}}
```

Wrong type (a GIF sent as `image/gif`):

```
HTTP 415
{"error":{"code":"unsupported_media_type","message":"That file type is not allowed.","request_id":"27a791c4-..."}}
```

Too large (a PDF of 9 MiB plus a few bytes):

```
HTTP 413
{"error":{"code":"payload_too_large","message":"That file is too large.","request_id":"23ee821a-..."}}
```

List (newest first, paged):

```
GET /patients/{patient_id}/documents?page=1
HTTP 200
{"items":[{"id":"48e16c0d-...","filename":"Sample xray note.pdf", ...}, ...],
 "total":3,"page":1,"page_size":20}
```

Download headers:

```
HTTP/1.1 200 OK
content-disposition: attachment; filename="Sample xray note.pdf"; filename*=UTF-8''Sample%20xray%20note.pdf
content-length: 26
x-content-type-options: nosniff
cache-control: private, no-store
content-type: application/pdf
```

Size edge, checked with curl through `:3000/api`: just under 8 MiB and exactly 8 MiB give 201.
8 MiB plus 1 byte, 9 MiB and 12 MiB give the API's 413 JSON.

## Break it once (criterion 19)

Each change was made alone, the document tests were run, then the change was reverted with
`git checkout`. The tree is clean again.

| Break | Result |
| --- | --- |
| Comment out the `record(...)` audit call in `upload_document` | 3 failures, including `test_an_upload_stores_the_bytes_the_row_and_one_audit_event` and `test_failed_uploads_write_no_audit_row_and_a_success_writes_one` |
| Remove the clinic scope from `DocumentRepository.get_for_patient` | 2 failures: `test_a_document_of_another_patient_or_clinic_is_not_found` and `test_another_clinic_cannot_list_or_download` |
| Trust the declared type instead of the magic bytes | Many failures, including `test_a_wrong_type_stores_nothing[...]` and `test_a_wrong_or_disagreeing_type_is_415[...]` |
