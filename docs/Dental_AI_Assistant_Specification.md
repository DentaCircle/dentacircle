# AI Clinic Practice Assistant — Product & MVP Specification

**Document status:** Working product specification  
**Version:** 1.0  
**Date:** 2026-09-29  
**Scope:** Generic clinic platform applicable to dental, dermatology, ophthalmology, physiotherapy, general practice, diagnostics-oriented clinics, and other outpatient clinics.

---

## 1. Product Overview

The product is a clinic operations and patient-coordination platform designed to reduce administrative workload and give clinicians a clear operational view of the clinic.

The long-term concept is an **AI-assisted clinic operating layer**. It should initially avoid diagnosis and treatment decisions and instead focus on:

- Patient coordination
- Appointment management
- Follow-ups and recalls
- Incomplete care/treatment tracking
- Patient communication
- Clinician/doctor daily assistance
- Inventory and medicine management
- Lab/external work tracking
- Patient reports and documents
- Clinic analytics
- Operational alerts and reminders

The MVP should prove that these workflows can be connected into one coherent system.

The initial implementation should be:

- Low/zero cost
- Local-first
- AI-assisted during development
- Clean and maintainable
- Easy to evolve into a production SaaS
- Independent of Azure, PostgreSQL, WhatsApp, and external AI providers initially

---

# 2. Product Vision

## 2.1 Core problem

Clinic staff often manage patient coordination, appointments, care schedules, documents, inventory, laboratory work, reminders, and reporting through a mixture of paper, spreadsheets, phone calls, messaging applications, and separate software systems.

The product should turn those disconnected tasks into a **single operational workflow**.

## 2.2 Long-term vision

A clinician should be able to open the application in the morning and immediately understand:

- What is happening today
- Which patients need attention
- Which follow-ups are overdue
- Which patients have incomplete care
- Which recalls are due
- Which reports/documents need attention
- What laboratory/external work is pending
- Which inventory/medicine items are running low
- Which items are approaching expiry
- What the clinic's operational and financial trends look like
- Which patient communication tasks remain unresolved

The platform should eventually be capable of taking action rather than merely presenting information.

Example:

```text
Follow-up due
    ↓
System identifies patient
    ↓
Coordinator receives task
    ↓
Patient is contacted
    ↓
Patient responds
    ↓
Available appointments are found
    ↓
Appointment is booked/rescheduled
    ↓
Follow-up status is updated
    ↓
Dashboard and analytics update
```

Initially this workflow can be manual or simulated. Later it can be automated with AI and communication integrations.

---

# 3. Product Principles

## 3.1 Workflow-first

Optimize for complete clinic workflows rather than merely providing CRUD screens.

## 3.2 AI should not control business truth

LLMs should interpret, summarize, draft, and assist. Deterministic application services should validate and execute important operations such as:

- Booking appointments
- Rescheduling
- Cancelling
- Updating care/treatment status
- Creating follow-ups
- Updating stock
- Recording inventory transactions

## 3.3 Clinical safety boundary

The MVP should not:

- Diagnose patients
- Recommend treatment
- Prescribe medication
- Interpret medical findings as a clinician
- Make autonomous clinical decisions

A future AI layer can assist with administrative and summarization tasks while escalating clinical questions to a clinician.

## 3.4 External services must be replaceable

The core system should not directly depend on a specific AI provider, WhatsApp, Azure, PostgreSQL, a specific telephony provider, or a specific storage provider.

These should be integrations behind interfaces.

## 3.5 Modular monolith first

Start with one backend application with strong internal module boundaries. Do not start with microservices.

---

# 4. Target Users and Roles

## 4.1 Clinician / Doctor

Typical capabilities:

- View dashboard
- View patients
- View patient history
- Review appointments
- Review care/treatment
- View follow-ups
- View recalls
- Review reports/documents
- Review lab/external work status
- View messages
- View operational analytics
- Perform clinician-specific updates

## 4.2 Receptionist / Coordinator

Typical capabilities:

- Add/search patients
- Schedule appointments
- Reschedule/cancel
- Check in patients
- Mark arrivals/completions/no-shows
- Manage follow-up queues
- Manage recall queues
- Send/draft patient communications
- View patient records
- Create reminders

## 4.3 Inventory/Admin User

Typical capabilities:

- Manage materials
- Manage medicines
- Record stock
- Record restocking
- View batches
- View expiry
- Review consumption
- Review expenditure
- Maintain suppliers later
- View inventory reports

## 4.4 Clinic Administrator

Typical capabilities:

- Clinic-wide administration
- User/role management
- Settings
- Analytics
- Financial/operational reporting
- Inventory administration

A clinician may also be the clinic administrator.

---

# 5. MVP Scope

The MVP should contain these functional areas:

1. Dashboard / Clinic Overview
2. Patients
3. Patient Details
4. Appointments
5. Treatments / Care Plans
6. Patient Reports / Documents
7. Follow-ups
8. Recalls
9. Lab / External Work Tracking
10. Inventory
11. Medicines
12. Messages
13. Reminders
14. Reports / Analytics
15. Billing & Invoices — lightweight
16. Settings
17. Authentication / Login
18. Role-based access

Some modules may share UI workflows.

---

# 6. Dashboard / Clinic Overview

The dashboard is the primary clinician/admin landing page.

## 6.1 Example

```text
Good morning, Doctor

Today's Appointments       18
Follow-ups                  3
Incomplete Care             4
Recall Due                  2
Missed Calls                2

Inventory
Material A                 12% remaining
Gloves                      ~5 days remaining

Expiry
Item B                      expires in 45 days

Pending Lab Work            3
Pending Reports             4

Operational Snapshot
Appointments this month   126
Completed                  94
No-shows                    6
```

## 6.2 Dashboard sections

### Today's appointments

Show:

- Time
- Patient
- Appointment type
- Assigned clinician
- Room/location if applicable
- Status

Statuses:

- Scheduled
- Confirmed
- Arrived
- In progress
- Completed
- Cancelled
- No-show

### Patient attention

Examples:

- Follow-up due
- Follow-up overdue
- Recall due
- Incomplete care
- Unresolved patient communication
- Missed appointment
- Pending document/report

### Inventory attention

Examples:

- Low stock
- Below minimum threshold
- Expiring soon
- Out of stock

### Lab/work attention

Examples:

- Pending collection
- Collected, awaiting result/work
- Ready for review
- Overdue

### Quick actions

- Add patient
- Book appointment
- Record care/treatment
- Add follow-up
- Upload report
- Record stock
- Send message

## 6.3 Dashboard behavior

Every important metric should be clickable. For example, clicking **3 patients need follow-up** should open the exact list of those patients.

---

# 7. Patients

## 7.1 Patient list

Required:

- Search by name
- Search by phone
- Search by patient ID
- Status filter
- Basic sorting
- Pagination

Suggested columns:

- Patient ID
- Name
- Phone
- Date of birth / age
- Last visit
- Next appointment
- Patient status
- Pending attention

## 7.2 Patient actions

- View
- Edit
- Book appointment
- Add care/treatment
- Add follow-up
- Upload report
- View documents
- View messages

---

# 8. Patient Details

Patient details should be the central longitudinal record.

## 8.1 Overview

```text
Patient Name
Patient ID
Phone
Date of birth / Age
Gender where applicable
Contact information
Status
```

## 8.2 Suggested tabs

- Overview
- Care / Treatment
- Appointments
- Follow-ups
- Recalls
- Reports / Documents
- Lab / External Work
- Messages
- Billing
- Timeline

Not every role needs every tab.

## 8.3 Patient timeline

Example:

```text
12 Sep
Consultation completed

13 Sep
Report uploaded

14 Sep
Follow-up created

18 Sep
Patient contacted

20 Sep
Appointment booked

28 Sep
Follow-up completed
```

The timeline should let the clinician understand the patient's history quickly.

---

# 9. Patient Reports / Documents

This is a **required MVP feature**.

## 9.1 Purpose

Patient clinical documents should remain attached to the patient record so that the clinician can retrieve them when the patient returns.

## 9.2 Document types

Examples:

- Scan reports
- Imaging reports
- Laboratory reports
- Referral documents
- External specialist reports
- Uploaded PDFs
- Images
- Other clinical documents

## 9.3 MVP functionality

- Upload document
- Attach document to patient
- Add document type
- Add document date
- Add optional description
- View/download document
- Associate with an appointment
- Associate with a follow-up where applicable
- Display document in patient history/timeline

Example:

```text
Patient
  ↓
Reports / Documents

15 Sep 2026
MRI Report
[Open]

18 Sep 2026
Blood Test Report
[Open]

22 Sep 2026
External Specialist Report
[Open]
```

## 9.4 Follow-up relationship

A follow-up can reference relevant documents.

Example:

```text
Follow-up
28 Sep 2026

Reason:
Review external report

Documents:
- MRI Report — 15 Sep
- Lab Report — 18 Sep
```

When the patient returns, the clinician should be able to open the patient record and see:

- Previous visits
- Follow-ups
- Relevant reports
- Care/treatment history
- Appointments
- Timeline

---

# 10. Appointments

Appointments are a core workflow.

## 10.1 Required functionality

- Calendar
- Day view
- Week view
- Create appointment
- Reschedule
- Cancel
- Mark confirmed
- Mark arrived
- Mark in progress
- Mark completed
- Mark no-show

## 10.2 Appointment data

- Patient
- Clinician
- Date
- Start time
- End time
- Appointment type
- Status
- Notes
- Room/resource if applicable

## 10.3 Booking flow

```text
Patient selected
      ↓
Appointment type
      ↓
Available slot
      ↓
Booking confirmation
      ↓
Appointment created
```

The MVP can use manually configured schedules.

---

# 11. Treatments / Care Plans

Use generic terminology so the platform can support different clinic types.

The module may represent:

- Treatment
- Procedure
- Care plan
- Session
- Clinical service

## 11.1 MVP capabilities

- Create care/treatment plan
- Add procedures/services
- Set planned status
- Mark started
- Mark completed
- Mark cancelled
- Track multiple sessions
- Record simple notes
- Track incomplete care

## 11.2 Example

```text
Care Plan: Plan A

Service 1
Completed

Service 2
In progress

Service 3
Pending
```

## 11.3 Incomplete-care workflow

```text
Care item pending
      ↓
Patient appears in attention queue
      ↓
Coordinator contacts patient
      ↓
Appointment booked
      ↓
Care status updated
```

---

# 12. Follow-ups

Follow-ups are one of the most important coordination features.

## 12.1 Fields

- Patient
- Reason
- Related appointment
- Related treatment/care
- Due date
- Status
- Priority
- Assigned staff member
- Notes
- Related reports/documents
- Completion date

## 12.2 Statuses

- Scheduled
- Due
- Contacted
- Patient responded
- Appointment booked
- Completed
- Overdue
- Cancelled

## 12.3 Actions

- Contact patient
- Schedule appointment
- Complete follow-up
- Reschedule
- Add note
- Escalate

---

# 13. Recalls

Recalls represent periodic or recurring patient visits.

Examples:

- Routine check
- Periodic review
- Preventive visit
- Monitoring visit
- Reassessment

## 13.1 MVP

- Recall due date
- Recall type
- Patient
- Last visit
- Status
- Contact status
- Appointment status

## 13.2 Recall statuses

- Upcoming
- Due
- Contacted
- Booked
- Completed
- Overdue
- Unable to contact

## 13.3 Example

```text
Recall due this week: 8

4 contacted
2 booked
1 awaiting response
1 overdue
```

---

# 14. Lab / External Work Tracking

A dedicated **Lab** tab should exist for clinics that use external laboratory or service workflows.

## 14.1 Required fields

- Patient name
- Work/request name
- Description
- Requested date
- Expected date/time
- Status
- Notes
- Related appointment/treatment

## 14.2 Required statuses

At minimum:

- Pending
- Collected

Optional future statuses:

- Sent
- In progress
- Ready
- Received
- Delivered
- Cancelled

## 14.3 Example

```text
LAB

Patient         Work                 Expected       Status

John Smith      External test        28 Sep         Pending
Asha Kumar      Custom device         29 Sep         Collected
David Paul      Specialist report     30 Sep         Pending
```

The lab workflow should connect to the patient record.

```text
Patient
  ↓
Lab work
  ↓
Status updated
  ↓
Document/report attached
  ↓
Follow-up created
```

---

# 15. Inventory

Inventory should be generic enough to support:

- Clinical materials
- Consumables
- Supplies
- Medicines
- Equipment-related consumables

## 15.1 Inventory item fields

- Name
- Category
- Unit
- Current quantity
- Minimum threshold
- Reorder threshold
- Batch
- Expiry date
- Supplier (optional MVP field)
- Purchase cost
- Status

## 15.2 Medicines

Medicines can use the same inventory engine.

Example:

```text
Medicines

Item              Stock     Unit       Expiry      Status
Medicine A        120       tablets    Nov 2026    OK
Medicine B         12       bottles    Oct 2026    Low
Medicine C          0       packs      --          Out of stock
```

No separate technical inventory system is necessary unless future requirements justify it.

---

# 16. Inventory Consumption

A key MVP feature is linking services/procedures to expected resource usage.

## 16.1 Example

```text
Service: Procedure A

Resource A     1 unit
Resource B     0.5 unit
Resource C     2 units
```

When the service is marked completed:

```text
Service completed
       ↓
Consumption rules
       ↓
Inventory transactions
       ↓
Stock reduced
       ↓
Threshold checked
       ↓
Alert generated if needed
```

## 16.2 Important rule

Inventory changes should be represented as transactions. Do not simply overwrite current quantity without recording why it changed.

Example transaction types:

- Restock
- Procedure consumption
- Manual adjustment
- Damaged stock
- Expired stock
- Transfer
- Correction

---

# 17. Restocking

Required MVP workflow:

```text
Select item
↓
Enter quantity
↓
Batch
↓
Expiry
↓
Cost
↓
Save restock
```

Example:

```text
Item: Resource A
Quantity: 50
Batch: B-2026-09
Expiry: 15 Mar 2027
Cost: ₹4,500
```

The system records the transaction and updates stock.

---

# 18. Inventory Alerts

Required:

- Low stock
- Out of stock
- Expiring soon
- Expired

Dashboard examples:

```text
Resource A
12% remaining
Low stock

Resource B
~5 days remaining

Resource C
Expires in 45 days
```

---

# 19. Messages

The MVP should contain a messaging interface even if external messaging is not yet integrated.

## 19.1 MVP approach

Use a simulated/internal messaging system.

Example:

```text
Patient:
I need to reschedule my appointment.

Clinic:
The following slots are available:

30 Sep 4:30 PM
01 Oct 11:00 AM
01 Oct 3:30 PM
```

This proves the workflow without paying for a messaging provider.

## 19.2 Future integrations

Potential channels:

- WhatsApp
- SMS
- Email
- Voice/telephony
- Other messaging channels

Use a messaging abstraction:

```text
MessagingService

DemoMessagingProvider
WhatsAppProvider
SMSProvider
EmailProvider
```

---

# 20. Reminders

Reminders can apply to:

- Appointments
- Follow-ups
- Recalls
- Lab work
- Report review
- Inventory
- Expiry
- Administrative tasks

## 20.1 Reminder model

- Type
- Related object
- Due date
- Priority
- Assignee
- Status
- Delivery method
- Created date
- Completed date

## 20.2 Statuses

- Scheduled
- Sent
- Completed
- Overdue
- Cancelled

---

# 21. Billing & Invoices

Billing should remain lightweight in the MVP.

## 21.1 MVP

- Create invoice
- Patient
- Service
- Amount
- Status
- Mark paid
- View invoice
- Basic summary

## 21.2 Excluded from MVP

- Full accounting system
- GST/tax engine
- Tax filing
- Insurance claims
- Accounting software integrations
- Advanced payment reconciliation

---

# 22. Clinic Analytics

Analytics should be generated from operational data already stored in the application.

## 22.1 Footfall / appointment analytics

Metrics:

- Appointments
- Completed
- Cancelled
- No-show
- New patients
- Returning patients
- Daily/weekly/monthly trend

## 22.2 Care analytics

Examples:

- Care items started
- Care items completed
- Pending care
- Completion rate
- Average time between sessions

## 22.3 Patient behavior analytics

Examples:

- Recall response
- No-show rate
- Cancellation rate
- Reactivation
- Follow-up completion
- Time to next appointment

## 22.4 Financial analytics

MVP-level metrics:

- Revenue recorded
- Material/medicine expenditure
- Number of invoices
- Paid/pending/overdue amounts
- Average visit value where applicable

## 22.5 Inventory analytics

Examples:

- Material usage
- Medicine usage
- Expenditure
- Most-used resources
- Low-stock frequency
- Expiry losses

---

# 23. Authentication and Roles

The MVP should support basic login.

Roles:

- Clinician
- Receptionist
- Inventory/Admin
- Clinic Admin

Role permissions should be explicit.

Example:

```text
Receptionist
  Patients
  Appointments
  Messages
  Follow-ups
  Recalls

Clinician
  Patients
  Appointments
  Care/Treatment
  Reports
  Follow-ups
  Lab
  Analytics

Inventory/Admin
  Inventory
  Medicines
  Reports
```

A single user may have multiple roles.

---

# 24. Settings

MVP settings:

- Clinic name
- Clinic contact details
- Working hours
- Appointment duration defaults
- Follow-up defaults
- Recall defaults
- Inventory thresholds
- Notification preferences
- User/role management

Future settings can include:

- Messaging provider
- AI provider
- Telephony
- Payment provider
- Storage provider

---

# 25. Core End-to-End Workflow

This is the most important demonstration scenario.

```text
Patient books/attends appointment
        ↓
Appointment status → Arrived
        ↓
Clinician records care/treatment
        ↓
Treatment/service completed
        ↓
Inventory consumption recorded
        ↓
Stock updated
        ↓
Follow-up automatically created
        ↓
Recall date calculated where applicable
        ↓
Patient leaves
        ↓
Follow-up becomes due
        ↓
Coordinator sees patient in queue
        ↓
Patient contacted
        ↓
Patient selects available slot
        ↓
Appointment booked
        ↓
Patient record updated
        ↓
Dashboard updates
        ↓
Analytics update
```

The MVP should make this workflow work end-to-end with deterministic logic.

---

# 26. AI Strategy

AI is intentionally not required for the zero-cost MVP.

## 26.1 Initial implementation

Use:

- Deterministic rules
- Templates
- Structured workflows
- Simulated message interactions

Examples:

```text
Follow-up due
→ create task

Appointment request
→ check available slots

Procedure complete
→ consume resources

Low stock
→ create alert
```

## 26.2 Later AI features

### AI Patient Coordinator

- Understand patient messages
- Extract intent
- Answer routine questions
- Find appointments
- Reschedule/cancel
- Send reminders
- Escalate uncertain cases

### AI Doctor/Clinic Assistant

- Summarize the day
- Prioritize attention items
- Summarize patient history
- Summarize recent reports/documents
- Draft follow-up messages

### AI Inventory Assistant

- Explain inventory trends
- Forecast demand
- Draft purchase recommendations

### AI Practice Assistant

- Summarize operations
- Identify anomalies
- Generate management summaries

---

# 27. AI Safety Architecture

The AI must not have unrestricted database access.

Use controlled tools/functions, for example:

```text
get_patient()
get_patient_history()
get_available_slots()
create_appointment()
reschedule_appointment()
cancel_appointment()
create_followup()
get_recall_status()
get_inventory_status()
create_inventory_task()
attach_document()
search_patient_reports()
escalate_to_human()
```

The AI chooses an allowed action, the application validates it, and the domain/service layer performs the operation.

---

# 28. Future Communication Integrations

Potential integrations:

- WhatsApp
- SMS
- Email
- Voice/telephony

The application should use an abstraction such as:

```python
class MessagingProvider:
    send_message(...)
    receive_message(...)
```

Current implementation:

```text
DemoMessagingProvider
```

Future implementations:

```text
WhatsAppProvider
SMSProvider
EmailProvider
```

---

# 29. Future Call / Landline Workflow

Later feature: a patient calls outside clinic hours and the clinic phone cannot be answered.

Potential workflow:

```text
Clinic phone
      ↓
Telephony provider
      ↓
After-hours routing
      ↓
Voicemail / speech-to-text
      ↓
Message to clinic/doctor
      ↓
Patient record / callback task
```

This should not be implemented initially. The product should expose a future integration boundary for telephony.

Even though this is a later feature, it could be useful to add a feature of sending message/alert to the clinician if there are calls to the clinic in after hours, and be shown in the dashboard for the MVP. 
---

# 30. Future Tax / Accounting Workflow

Later:

```text
Billing data
     ↓
Financial aggregation
     ↓
Tax-related records
     ↓
Export / submission documents
```

Tax submission should not be part of the initial MVP. The MVP should only record enough structured data that it can be added later.

---

# 31. Architecture

## 31.1 High-level MVP architecture

```text
                   Browser
                     |
                  Next.js
                     |
                  REST API
                     |
                  FastAPI
                     |
        +------------+-------------+
        |            |             |
     Services     Domain      Integrations
        |            |             |
        +------------+-------------+
                     |
                Repositories
                     |
                   SQLite
```

## 31.2 Future production architecture

```text
Next.js
   |
FastAPI
   |
PostgreSQL
   |
+-----------------------------+
| Blob Storage                |
| Messaging                   |
| AI                          |
| Queue / Worker              |
| Telephony                   |
| Payments                   |
+-----------------------------+
```

---

# 32. Repository Architecture

A monorepo is recommended for the MVP because a single developer is building multiple closely related applications for one product.

```text
clinic-assistant/
│
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── dashboard/
│   │   │   ├── patients/
│   │   │   ├── appointments/
│   │   │   ├── care/
│   │   │   ├── inventory/
│   │   │   ├── lab/
│   │   │   ├── reports/
│   │   │   ├── messages/
│   │   │   └── analytics/
│   │   └── ...
│   │
│   └── api/
│       ├── app/
│       │   ├── api/
│       │   ├── domain/
│       │   ├── services/
│       │   ├── repositories/
│       │   ├── models/
│       │   ├── schemas/
│       │   ├── integrations/
│       │   │   ├── ai/
│       │   │   ├── messaging/
│       │   │   ├── storage/
│       │   │   ├── telephony/
│       │   │   └── payments/
│       │   └── core/
│       ├── migrations/
│       └── tests/
│
├── docs/
├── scripts/
├── docker-compose.yml
├── README.md
└── .gitignore
```

The frontend and backend remain separate applications even though they live in one Git repository.

---

# 33. Recommended Technology Stack

## Frontend

- Next.js
- TypeScript
- React
- Tailwind CSS or a component system
- Charting library as needed

## Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

## Database

- SQLite initially

## Testing

- Pytest
- Frontend unit/component tests
- API integration tests
- End-to-end tests for critical workflows

## Local development

- Docker Compose where useful
- Local filesystem for documents initially

## Version control

- Git
- GitHub

---

# 34. Database Strategy

Use SQLite for the zero-cost MVP.

The data-access layer should be designed so the application can later migrate to PostgreSQL without rewriting business logic.

```text
API
 ↓
Service
 ↓
Repository interface
 ↓
SQLite implementation
```

Later:

```text
API
 ↓
Service
 ↓
Repository interface
 ↓
PostgreSQL implementation
```

---

# 35. Initial Data Model

Suggested entities:

```text
Clinic
User
Role
UserRole

Patient
PatientContact
PatientStatus

Appointment
AppointmentStatus
AppointmentType

CarePlan
CareItem
CareSession

FollowUp
Recall

PatientDocument
DocumentType

LabWork
LabWorkStatus

InventoryItem
InventoryBatch
InventoryTransaction
InventoryCategory

ProcedureResourceRule

MessageThread
Message
Reminder

Invoice
InvoiceLine
Payment

AuditEvent
```

The exact model should be refined during implementation.

---

# 36. Important Data Relationships

```text
Clinic
  ├── Users
  ├── Patients
  ├── Appointments
  ├── Inventory
  └── Reports

Patient
  ├── Appointments
  ├── Care Plans
  ├── Follow-ups
  ├── Recalls
  ├── Documents
  ├── Lab Work
  ├── Messages
  ├── Invoices
  └── Timeline Events

Appointment
  ├── Patient
  ├── Clinician
  ├── Care/Treatment
  ├── Follow-up
  └── Documents

Care Item
  └── Resource Consumption

Inventory Item
  ├── Batches
  ├── Transactions
  └── Alerts
```

---

# 37. API Style

REST APIs initially.

Example endpoints:

```text
GET    /patients
POST   /patients
GET    /patients/{id}
PATCH  /patients/{id}

GET    /appointments
POST   /appointments
PATCH  /appointments/{id}
POST   /appointments/{id}/cancel

GET    /followups
POST   /followups
PATCH  /followups/{id}

GET    /recalls

GET    /inventory/items
POST   /inventory/items
POST   /inventory/items/{id}/restock
GET    /inventory/transactions

GET    /lab/work
POST   /lab/work
PATCH  /lab/work/{id}

GET    /patients/{id}/documents
POST   /patients/{id}/documents

GET    /messages
POST   /messages

GET    /dashboard
GET    /analytics
```

Endpoint naming should be finalized during implementation.

---

# 38. Frontend Navigation

Suggested navigation:

```text
Dashboard
Patients
Appointments
Care / Treatments
Lab
Inventory
Messages
Reminders
Reports
Billing
Settings
```

Patient-specific information should be accessible from the patient record rather than creating unnecessary duplicate screens.

---

# 39. UI Direction

The client reference screens indicate a polished clinic-dashboard style. The MVP should take inspiration from that structure without copying it exactly.

Desired characteristics:

- Desktop-first but responsive
- Clean left navigation
- Persistent search
- Clear cards
- Status badges
- Tables for operational data
- Calendar for appointments
- Timeline for patient history
- Quick actions
- Alerts/attention panels
- Charts for analytics
- Clear empty/loading/error states

The application should feel like a real clinic operations system even though the initial implementation is local/demo-oriented.

---

# 40. Demo Data / Seeding

The demo should not require manually entering hundreds of records.

Create a seed-data generator.

Suggested dataset:

```text
100–200 patients
200–400 appointments
30–100 care plans
20–50 follow-ups
20–50 recalls
10–30 lab records
20–40 inventory items
100+ inventory transactions
Multiple documents/reports
Sample messages
Sample invoices
```

Seed data should generate realistic relationships rather than isolated rows.

---

# 41. Primary Demo Scenario

The primary demo should prove the system is interconnected.

Example:

```text
1. Patient has appointment.
2. Patient arrives.
3. Clinician records a service/care session.
4. Resource consumption is recorded.
5. Inventory is updated.
6. A follow-up is created.
7. A report is uploaded to the patient record.
8. The follow-up becomes due.
9. The patient appears in the coordinator queue.
10. Coordinator sends a simulated message.
11. Patient selects an available slot.
12. Appointment is booked.
13. Dashboard updates.
14. Analytics update.
```

This is more important than having many disconnected screens.

---

# 42. MVP Acceptance Criteria

## Patient coordination

- Search/create patient
- Book appointment
- Reschedule
- Cancel
- Mark arrived
- Mark completed
- Mark no-show
- Create follow-up
- Complete follow-up
- Create recall
- Track incomplete care
- View patient history

## Reports/documents

- Upload document
- Attach to patient
- View document from patient record
- Associate with relevant workflow
- View later during follow-up

## Lab

- Create lab work item
- Assign patient
- Enter expected time/date
- Set Pending/Collected
- View from lab dashboard and patient record

## Inventory

- Add inventory item
- Restock
- Record batch/expiry
- Record consumption
- Update stock
- Generate low-stock alert
- Generate expiry alert
- Track transactions

## Doctor assistant

- Morning dashboard
- Today's appointments
- Follow-up alerts
- Recall alerts
- Incomplete care alerts
- Inventory alerts
- Basic clinic metrics

## Analytics

- Footfall
- Appointment status
- Care/treatment completion
- Follow-up/recall metrics
- Inventory expenditure
- Basic financial metrics

## Roles

- Login
- At least 3 role profiles
- Restricted navigation/access where appropriate

---

# 43. Explicit MVP Non-Goals

Do not build initially:

- Clinical diagnosis
- Clinical decision support
- Treatment recommendation engine
- Prescription automation
- Full EMR
- Advanced medical charting
- X-ray/DICOM management
- Insurance claims
- Full accounting ERP
- Tax submission
- Automated WhatsApp
- Voice AI
- Automated phone routing
- Advanced AI agents
- Predictive inventory
- Multi-country regulatory support
- Native mobile applications
- Microservices
- Kubernetes
- Multi-region infrastructure
- High-scale distributed architecture

---

# 44. Cost Strategy

## Local MVP target

**₹0/month**

Use:

- Python
- FastAPI
- Next.js
- SQLite
- Local document storage
- GitHub
- Local development environment
- Simulated messaging
- Deterministic workflows

No paid AI API is required.

No paid cloud infrastructure is required.

If remote access becomes necessary, add the cheapest appropriate hosting only after the local MVP proves the workflow.

---

# 45. Deployment Path

## Stage 1 — Local demo

```text
Next.js
+
FastAPI
+
SQLite
+
Local files
```

## Stage 2 — Low-cost pilot

Possible:

```text
Next.js hosting
+
FastAPI hosting
+
Managed PostgreSQL
+
Object storage
```

## Stage 3 — Production

Possible Azure architecture:

```text
Next.js
       ↓
FastAPI
       ↓
Managed PostgreSQL
       ↓
Blob Storage
       ↓
Queue/Worker
       ↓
AI provider
       ↓
WhatsApp / SMS / Telephony
```

The product should remain portable between stages.

---

# 46. Development With AI

AI should be used as a development accelerator, not as an unattended developer.

Recommended process:

```text
Plan
 ↓
Design
 ↓
AI implementation
 ↓
Review generated code
 ↓
Run tests
 ↓
Run application
 ↓
Inspect behavior
 ↓
Refactor
 ↓
Commit
```

The developer remains responsible for:

- Architecture
- Business rules
- Security
- Data model
- API contracts
- Code review
- Testing
- Edge cases
- UX decisions

---

# 47. Estimated Development Effort

For one developer using AI while actively reviewing code:

## Full-time equivalent

Approximately **220–300 focused hours**, or roughly **6–8 weeks full-time**.

## Part-time equivalents

At ~20 hours/week: **11–15 weeks**.

At ~11–12 hours/week: **19–26 weeks**.

A convincing thin-slice demo can be produced earlier than the full MVP.

The exact time depends heavily on the level of polish, the amount of test coverage, and how many edge cases are discovered during implementation.

---

# 48. Suggested Implementation Phases

## Phase 0 — Foundation

- Repository setup
- Monorepo
- Next.js
- FastAPI
- SQLite
- SQLAlchemy
- Alembic
- Environment configuration
- Logging
- Error handling
- Basic UI shell
- Authentication skeleton

## Phase 1 — Patients and Appointments

- Patient CRUD
- Search
- Patient details
- Appointment model
- Calendar
- Booking
- Reschedule
- Cancel
- Status changes

## Phase 2 — Care + Follow-up + Recall

- Care plans
- Care items
- Sessions
- Incomplete care
- Follow-ups
- Recall rules
- Patient timeline

## Phase 3 — Reports + Lab

- Document upload
- Patient documents
- Document viewer
- Lab records
- Lab status
- Follow-up/document relationships

## Phase 4 — Inventory

- Inventory items
- Categories
- Batches
- Expiry
- Restock
- Transactions
- Consumption
- Procedure/resource rules
- Medicine inventory
- Alerts

## Phase 5 — Dashboard + Analytics

- Dashboard metrics
- Attention queues
- Inventory alerts
- Footfall charts
- Care metrics
- Follow-up metrics
- Basic financial metrics

## Phase 6 — Messaging + Reminders

- Simulated inbox
- Patient communication
- Reminder engine
- Reminder states
- Patient coordination flow

## Phase 7 — Polish / Hardening

- RBAC
- Validation
- Error states
- Empty states
- Audit logging
- Tests
- Seed data
- UI polish
- Demo script
- Documentation

---

# 49. Future Roadmap

## AI

- AI patient coordinator
- AI message classification
- AI appointment handling
- AI patient summaries
- AI report/document summarization
- AI clinic assistant
- AI inventory assistant

## Communications

- WhatsApp
- SMS
- Email
- Telephony
- After-hours call diversion
- Voicemail transcription

## Operations

- Supplier management
- Purchase orders
- Inventory forecasting
- Resource cost analysis
- Multi-location clinics

## Financial

- Payment gateway
- Accounting integration
- Tax document generation
- Tax submission workflows

## Platform

- Multi-clinic SaaS
- Subscription billing
- Advanced RBAC
- Audit/compliance tooling
- Enterprise deployment options
- Mobile apps

---

# 50. Architectural Evolution Rule

Do not prematurely optimize for scale.

Expected progression:

```text
Local modular monolith
        ↓
Hosted modular monolith
        ↓
PostgreSQL + object storage
        ↓
Background worker / queue
        ↓
AI + communications integrations
        ↓
Scale individual components only when justified
```

The architecture should make this progression possible without a rewrite.

---

# 51. Final MVP Definition

The MVP is a **generic clinic operations and patient-coordination platform** with:

- Patient management
- Appointment management
- Care/treatment tracking
- Follow-ups
- Recalls
- Incomplete care tracking
- Patient reports/documents
- Lab/external-work tracking
- Inventory and medicines
- Resource consumption
- Messages
- Reminders
- Dashboard
- Clinic analytics
- Basic billing
- Authentication and roles

The MVP should be:

- Local-first
- Zero-cost to run during development
- Built as a modular monolith
- Monorepo-based
- Python + FastAPI backend
- Next.js + TypeScript frontend
- SQLite initially
- PostgreSQL-ready
- Integration-ready for AI, messaging, storage, payments, and telephony
- Safe by default around clinical decision-making
- Focused on demonstrating connected operational workflows

The most important success criterion is not the number of screens.

It is whether the system can demonstrate:

```text
Patient
  ↓
Appointment
  ↓
Care
  ↓
Resource usage
  ↓
Inventory update
  ↓
Report/document
  ↓
Follow-up
  ↓
Communication
  ↓
Next appointment
  ↓
Dashboard
  ↓
Analytics
```

That connected workflow is the foundation for the eventual AI-powered clinic assistant.
