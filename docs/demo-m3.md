# M3 demo

One synthetic patient. Scaling is finished, root canal is still open, and a six-month Scaling recall is booked and completed. No clinical notes. No real patient data.

Lab work, a crown and a document are not in this demo. Those arrive in S3.x.

## Setup

1. From the repo root, `make dev`. Open `http://localhost:3000`.
2. In another terminal, create two users in one clinic. The password is prompted, or read from `CREATE_USER_PASSWORD`. It is never an argument.

   ```sh
   make create-user ARGS='--clinic "Synthetic Clinic" --email s27.clinician@x.test --name "Synthetic Clinician" --roles clinician'
   make create-user ARGS='--clinic "Synthetic Clinic" --email s27.desk@x.test --name "Synthetic Desk" --roles receptionist'
   ```

   Synthetic Clinician starts and completes visits and records care. Synthetic Desk is the coordinator: Follow-ups and Recalls. If a user already exists, sign in with the password you set then.

3. The clinic day is the seeded one: Asia/Kolkata, Monday to Friday, 09:00 to 18:00. Scaling already has a six-month recall. Book every visit for today so Arrived is allowed. Today has to be a weekday the clinic is open.

## The story

### 1. Register, book, arrive, start

Sign in as `s27.clinician@x.test`.

1. Patients, then New patient. Name `Sample Ada`. Phone `9000000091`. Leave Date of birth (optional) empty. Save patient. The list says `Saved P-0009.` Open the name. The patient page shows the display id.
2. Book appointment. The form opens on Type Consultation and the first clinician in the list. Choose Type Scaling and Clinician Synthetic Clinician. Date is already today. Pick an open time. Book. The patient page says Booked.
3. Calendar. It opens on today. On the Scaling row: Arrived, then Start. The row shows In progress and a Care session link.

### 2. Plan, session, complete

1. Open the patient, then Care. Title `Sample plan`, New care plan. An empty plan can show Finished until an item exists. Service name `Scaling`, Add item. Service name `Root canal`, Add item. Both show Planned. Do not use the manual Create follow-up form on this page. The due-today follow-up comes from the visit completion date.
2. Calendar, Care session on the Scaling visit. Scaling: Completed. Root canal: Started. Save care session, then Yes. Completed items cannot be undone.
3. Calendar, Complete on that visit. Follow-up date: today. Yes. The row shows Completed.
4. Care shows Follow-up due today, Scheduled. Scaling is Completed. Root canal is Started.

Setting the follow-up date to today is what puts Ada in Due at once. Leaving it empty would make the follow-up due in 7 days, and Due would stay empty today.

### 3. Contact and book the follow-up

Sign out. Sign in as `s27.desk@x.test`.

1. Follow-ups. Due is the view that opens. Ada is there: Due today, Scheduled. This is proof shot 1.
2. Mark contacted. The same row stays in Due, now Contacted, still Due today. This is proof shot 2.
3. Book visit. The form opens on Type Consultation and the first clinician. Leave the type as Consultation. Choose Clinician Synthetic Clinician. Date today. After that clinician is selected, the Scaling visit's time is gone. Pick another open time. Book.
4. Open Ada, then Care. The line reads Follow-up due today, Booked. This is proof shot 3.

### 4. Close the follow-up, then the recall

1. Still as Synthetic Desk, Recalls, then All open. Ada's row is Recall type Scaling, Timing Upcoming, Status Scheduled. Due hides it, because it is six months out. This is proof shot 4.
2. Sign out. Sign in as `s27.clinician@x.test`. Calendar. On the Consultation row: Arrived, Start, Complete. Leave Follow-up date empty. Yes (Keep leaves the visit in progress). That visit shows Completed. Completing it closes the booked follow-up. Because root canal is still open, Care shows a new follow-up due 7 days out, Scheduled.
3. Sign out. Sign in as `s27.desk@x.test`. Recalls, All open. Mark contacted on Ada's Scaling row, then Book visit. The form opens on Consultation and the first clinician. Choose Type Scaling and Clinician Synthetic Clinician. Date today. Pick a free time. Book.
4. Sign out. Sign in as `s27.clinician@x.test`. Calendar. On the new Scaling row: Arrived, Start, Complete. Leave Follow-up date empty. Yes. The row shows Completed. The booked recall closes and a new Scaling recall is written, six months from today. Recalls, All open, shows that new row as Scheduled.

### 5. Timeline and the day

Still as Synthetic Clinician.

1. Open Ada, then Timeline. The list is paged, newest first. Page 1 starts with Recall created (Scaling, six months out), Recall completed, and Follow-up updated (due 7 days out), then the visit steps. Later pages hold the care session and Patient registered. This is proof shot 5.
2. Calendar, today. Three rows for Ada, each Completed: the first Scaling visit, the Consultation booked from the follow-up, and the Scaling visit booked from the recall. This is proof shot 6.
