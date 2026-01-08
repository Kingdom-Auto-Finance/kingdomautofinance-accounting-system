# Kingdom Auto Finance Accounting System

**Complete Guide for Operations, Finance, and Future Contributors**

---

## 🚀 Quick Start

**What This System Does:**
- Imports amortization schedules from Google Sheets into Supabase database
- Fetches bank payments from Google Sheets and processes them against loan schedules
- Calculates principal, interest, and late fees collected each month
- Generates CSV reports for the accounting team to enter into QuickBooks

**Monthly Workflow (5 minutes):**
1. Access the Streamlit UI (password: `Kingdom2025!$$`)
2. Click **"Generate Report"** in the main section
3. Select date range: First to last day of previous month (e.g., Dec 1 - Dec 31)
4. Click **"Generate Summary Report"**
5. Download the CSV file
6. Send to CFO/accounting team for QuickBooks entry

**When to Run Maintenance Operations:**
- **Fetch All Payments:** Once per week or month (pulls new payments from Google Sheets)
- **Process Payments:** Immediately after fetching (applies payments to loan schedules)
- **Import Amortization Schedules:** Only when adding new loans

---

## 📋 Table of Contents

1. [Business Context](#business-context)
2. [System Overview](#system-overview)
3. [How It Works (Data Flow)](#how-it-works-data-flow)
4. [Pain Points Explained](#pain-points-explained)
5. [Monthly Operations Workflow](#monthly-operations-workflow)
6. [Special Scenarios](#special-scenarios)
7. [Current Reports](#current-reports)
8. [Future Roadmap](#future-roadmap)
9. [Configuration & Access](#configuration--access)

---

## Business Context

### Why This System Exists

Kingdom Auto Finance provides vehicle financing to customers. Each loan has an **amortization schedule** that breaks down monthly payments into:
- **Principal** (loan paydown)
- **Interest** (cost of borrowing)
- **Late Fees** (penalties for missed payments)

Previously, all payment tracking was done manually in Google Sheets, which was:
- Time-consuming and error-prone
- Difficult to track partial payments
- Hard to generate accurate monthly reports
- Not scalable as the loan portfolio grew

This system **automates the entire process** from payment receipt to accounting reports.

### Accounting Requirements

**Cash Basis Accounting:**
- Kingdom Auto Finance recognizes revenue when payments are **collected**, not when they're earned
- A payment received on January 31st counts in January, even if processed in February
- The `payment_date` field (date received at bank) determines the accounting period

**Monthly Reporting Cycle:**
- **During Month:** Bank payments are manually entered into Google Sheets as they arrive
- **End of Month:** System processes all payments and generates reports
- **By 5th of Next Month:** Accounting team receives summary report for the previous calendar month
- **Accounting Entry:** CFO or assistant manually enters totals (principal, interest, fees) into QuickBooks

### Source of Truth

Understanding the data flow hierarchy:
1. **Google Sheets (Source)** - Bank payments are manually entered here as they're received
2. **Supabase (Processor)** - Database processes payments according to amortization rules
3. **CSV Reports (Output)** - Exported data for accounting team to use in QuickBooks

There's no conflict between Sheets and Supabase because they serve different purposes: Sheets is the input, Supabase is the processing engine, reports are the output.

---

## System Overview

### What the System Does

```
Bank Payment → Google Sheets → Fetch → Supabase → Process → Report → QuickBooks
```

**Step-by-Step:**
1. **Manual Entry:** When a customer makes a payment, it's recorded in Google Sheets
2. **Fetch Payments:** System pulls new payments from Google Sheets into Supabase `payments_log` table
3. **Process Payments:** System applies each payment to the correct loan's amortization schedule using business rules
4. **Generate Reports:** System calculates total principal, interest, and fees for a date range
5. **Accounting Entry:** CFO downloads CSV and manually enters amounts into QuickBooks

### Key Components

**Files You Should Know About:**
- `ui.py` - Streamlit web dashboard (what users interact with)
- `src/main.py` - Command-line interface (runs operations behind the scenes)
- `src/payment_fetcher.py` - Fetches payments from Google Sheets
- `src/payment_processor.py` - Applies payments to schedules (most complex logic here)
- `src/reporting.py` - Generates CSV reports
- `src/bootstrap.py` - Imports new loan schedules (used when adding loans)
- `src/config.py` - Settings like late fees, grace periods

**Database Tables:**
- `payments_log` - All payments fetched from Google Sheets
- `schedule_{loan_id}` - One table per loan containing its amortization schedule
- `loans` - Master list of all active loans

**Google Sheets Used:**
- **Source Payments Sheet** - Where bank payments are manually entered
- **Amortization Schedules Folder** - One sheet per loan with payment schedule

---

## How It Works (Data Flow)

### Phase 1: Import Amortization Schedules (One-Time Setup)

**When:** Adding a new loan to the system

**What Happens:**
1. Create amortization schedule in Google Sheets (in the designated Drive folder)
2. Name the sheet with the loan ID (e.g., "ABC123")
3. Run **"Import Amortization Schedules"** in the UI
4. System discovers the new sheet and creates a `schedule_abc123` table in Supabase
5. Imports all scheduled payments (payment number, due date, scheduled amount, etc.)

**Why:** This gives the system the "blueprint" for what payments should look like for each loan.

### Phase 2: Fetch Payments (Weekly/Monthly)

**When:** Once per week or month, after new payments have been entered in Google Sheets

**What Happens:**
1. User clicks **"Fetch All Payments"** in UI
2. System reads all rows from the Google Sheets "Payments" tab
3. Compares against existing `payments_log` table in Supabase
4. Identifies new payments using composite key: (loan_id, payment_date, payment_amount)
5. Inserts only new payments (avoids duplicates)
6. Marks all new payments as `processed=False` (ready for processing)

**Why:** This brings bank payment data into the system for processing. Deduplication ensures each payment is only counted once.

**How Deduplication Works:**
- Each payment is uniquely identified by loan ID + date + amount
- If a payment with the same loan/date/amount already exists, it's skipped
- This prevents double-counting even if you run "Fetch" multiple times

### Phase 3: Process Payments (Immediately After Fetch)

**When:** Immediately after fetching, or anytime there are unprocessed payments

**What Happens:**
1. User clicks **"Process Payments"** in UI
2. System queries all payments where `processed=False`
3. For each payment (oldest first):
   - **Atomically claims** the payment (prevents concurrent processing)
   - Reads the loan's amortization schedule from `schedule_{loan_id}` table
   - Determines which scheduled payment(s) this applies to
   - Calculates allocation: Interest first, then late fees, then principal
   - Updates schedule rows with actual payment amounts
   - Propagates balance changes to subsequent payments
   - Marks payment as `processed=True` with timestamp
4. Reconciles: Verifies allocated amount equals payment amount
5. If mismatch: Reverts claim and logs error for manual review

**Why:** This is where the "magic" happens - the system applies business rules to allocate payments correctly across interest, principal, and fees.

**Key Business Rules:**
- **Tolerance:** $10 shortfall allowed (if payment is $490 and scheduled is $500, still marks as "Paid")
- **Threshold:** Payment must be ≥90% of scheduled amount to apply
- **Late Fees:** $25 flat fee if payment is more than 3 days after due date (grace period)
- **Forward Payments:** Can pay ahead up to 2 installments if excess is ≥50% of next payment
- **Curtailment:** Early payments >2× scheduled amount go as extra principal on last paid row

### Phase 4: Generate Reports (Monthly)

**When:** End of month, before delivering to accounting team

**What Happens:**
1. User clicks **"Generate Report"** in UI
2. Selects date range (e.g., Dec 1 - Dec 31, 2025)
3. Chooses report type (usually "Summary")
4. System queries all `schedule_{loan_id}` tables
5. Filters rows where `actualpaymentdate` is within the date range
6. Sums up: `principalpaid`, `interestpaid`, `latefee` across all loans
7. Outputs CSV file with totals

**Why:** This creates the deliverable for the accounting team - total cash collected during the period.

**Important:** The system uses `payment_date` (when received at bank), not `processed_at` (when entered in system), for accounting period assignment.

---

## Pain Points Explained

These are the most common confusion points when someone new looks at the system.

### 1. Partial Payments (Most Confusing)

**The Problem:**
A customer's scheduled payment is $500, but they make multiple small payments:
- Jan 5: $150
- Jan 12: $200
- Jan 18: $150

**What the System Does:**

**First Payment ($150):**
- System checks: Is this ≥90% of scheduled ($500)? No.
- System checks: Is this ≥$10 below scheduled? No.
- Action: Marks as "Partially Paid", applies $150 toward interest/principal
- Status: Payment row still shows as incomplete

**Second Payment ($200):**
- System calculates: Previous $150 + New $200 = $350 total
- System checks: Is $350 ≥90% of scheduled ($500)? No (only 70%)
- Action: Applies another $200, now $350 total applied
- Status: Still "Partially Paid"

**Third Payment ($150):**
- System calculates: $350 + $150 = $500 total
- System checks: Is $500 ≥90% of scheduled ($500)? Yes!
- Action: Marks payment row as "Paid", moves to next scheduled payment
- Status: "Paid" (or "Paid Late" if beyond grace period)

**Key Insight:** The system **accumulates** multiple payments toward a single scheduled payment until it reaches the threshold (≥90% or within $10).

**How It Tracks This:**
- The `actualpaymentamount` field on the schedule row accumulates each partial payment
- Each payment in `payments_log` is processed individually but applied to the same schedule row
- When the accumulated amount crosses the threshold, the system advances to the next row

### 2. Payment Identification & Deduplication

**The Problem:**
How does the system know if a payment is new or already processed?

**The Solution: Composite Key**

Each payment is uniquely identified by three fields together:
1. **loan_id** (which loan, e.g., "ABC123")
2. **payment_date** (when received, e.g., "2025-01-15")
3. **payment_amount** (how much, e.g., $500.00)

**Example Scenarios:**

| Loan ID | Date | Amount | New? | Reason |
|---------|------|--------|------|--------|
| ABC123 | 2025-01-15 | $500 | Yes | First time seeing this combination |
| ABC123 | 2025-01-15 | $500 | No | Exact duplicate (same loan, date, amount) |
| ABC123 | 2025-01-15 | $250 | Yes | Different amount, even though same date |
| ABC123 | 2025-01-20 | $500 | Yes | Different date, even though same amount |

**Why This Matters:**
- Prevents double-counting if you run "Fetch Payments" multiple times
- Allows multiple payments on the same date (as long as amounts differ)
- Ensures data integrity even with human error in Google Sheets

**Edge Case - True Duplicates:**
If a customer genuinely makes two identical $500 payments on the same day for the same loan, the system will only count one. This is rare but would need manual intervention.

### 3. Late Fee Logic

**The Rule:**
- If payment is received **more than 3 days after the due date**, charge a **$25 flat late fee**
- Late fee is charged **only once per scheduled payment** (won't charge multiple times for the same payment)

**Example:**

**Scenario 1: On-Time Payment**
- Due Date: Jan 15, 2025
- Payment Date: Jan 17, 2025 (2 days late)
- Grace Period: 3 days
- Late Fee: $0 (within grace period)
- Status: "Paid"

**Scenario 2: Late Payment**
- Due Date: Jan 15, 2025
- Payment Date: Jan 20, 2025 (5 days late)
- Grace Period: 3 days
- Late Fee: $25 (exceeded grace period)
- Status: "Paid Late"

**Scenario 3: Partial Payment, Then Late**
- Due Date: Jan 15, 2025
- Payment 1: Jan 17 for $200 (partial, within grace)
- Payment 2: Jan 22 for $300 (completes payment, but now 7 days late)
- Late Fee: $25 (charged when the payment row is finally completed)
- Status: "Paid Late"

**How It's Calculated:**
1. System compares `payment_date` to `duedate`
2. If difference > 3 days, adds $25 to `latefee` field
3. Checks if `latefee` already has a value (prevents double-charging)
4. Reduces the amount going to principal by $25 (payment covers interest, then fee, then principal)

**Allocation Order:**
1. **Interest** (pre-filled in schedule, must be covered first)
2. **Late Fee** (if applicable, $25 flat)
3. **Principal** (remainder of payment)

---

## Monthly Operations Workflow

### Standard End-of-Month Process

**Timing:** Last day of month or first few days of next month

**Who:** CFO, CFO's assistant, or Finance team member

**Steps:**

#### 1. Ensure All Payments Are Entered (Throughout Month)
- As payments arrive at the bank, they're manually entered into Google Sheets
- Google Sheet: "Source Payments" (ID: `14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8`)
- Columns: LoanId, Date, Amount
- This should happen continuously, not just at month-end

#### 2. Access the System
- Navigate to Streamlit UI (Google Cloud Run URL)
- Enter password: `Kingdom2025!$$`

#### 3. Fetch New Payments (System Maintenance Section)
- Expand **"System Maintenance"** section at bottom of page
- Click **"Fetch All Payments"** button
- Wait for log to show completion (typically 10-30 seconds)
- Check for any warnings about missing loan schedules
- Click 📝 button to view detailed logs if needed

#### 4. Process Payments (System Maintenance Section)
- Click **"Process Payments"** button
- Wait for log to show completion (typically 30-60 seconds for 100+ payments)
- Check for any reconciliation errors
- If errors appear, note loan IDs for CFO review

#### 5. Generate Monthly Report (Main Section)
- Return to top of page
- **Date From:** First day of previous month (e.g., 2025-12-01)
- **Date To:** Last day of previous month (e.g., 2025-12-31)
- Select **"Summary"** from report type dropdown
- Click **"Generate Summary Report"**

#### 6. Review and Download
- Report appears in the page showing:
  - Total Principal Paid
  - Total Interest Paid
  - Total Late Fees Collected
  - (These are the three numbers accounting needs)
- Click **"Download CSV"** button
- Save file with descriptive name (e.g., `kingdom_summary_december_2025.csv`)

#### 7. Deliver to Accounting
- Email CSV to accounting team (or hand off directly)
- **Deadline:** By 5th of the month
- Accounting team manually enters the three totals into QuickBooks

### Troubleshooting During Monthly Process

**Issue: "Missing schedule for loan XYZ" warning**
- Cause: A payment was received for a loan that doesn't have an amortization schedule imported
- Fix: Either import the missing schedule or ignore if loan was paid off/closed
- Impact: Payment won't be included in reports until schedule is imported

**Issue: "Reconciliation error for payment ID 123"**
- Cause: System couldn't allocate the full payment amount (math doesn't add up)
- Fix: CFO needs to manually review in Supabase - likely a data entry error in Google Sheets
- Impact: Payment remains unprocessed and won't appear in reports

**Issue: Report totals seem low**
- Check: Did you run "Fetch Payments" first?
- Check: Did you run "Process Payments" after fetching?
- Check: Is the date range correct?
- Check: Are there unprocessed payments? (Look at "Process Payments" log)

---

## Special Scenarios

These scenarios happen occasionally and have specific handling procedures.

### Loan Payoffs

**What It Is:** Customer pays the entire remaining balance in one payment

**How System Handles It:**
- System detects payment amount is significantly larger than scheduled payment (curtailment rule: >2× scheduled)
- If payment is received **before the due date**, treats it as extra principal
- Applies payment to cover interest first, then applies all remaining to principal
- Updates ending balance to $0 (or near zero)
- Marks remaining unpaid rows as skipped
- Status: "Paid Off" or "Paid Off Late"

**Example:**
- Remaining balance: $5,000
- Scheduled payment: $500
- Customer pays: $5,200 (payoff amount)
- System applies: $50 interest + $5,000 principal = $5,050
- Excess $150 stays as extra principal on final row
- All future scheduled rows remain but show as unneeded

**No Manual Intervention Needed** - System handles automatically

### Refinances

**What It Is:** Customer refinances loan (new loan replaces old loan)

**How System Handles It:**
1. **Old Loan:** Simply stop entering payments in Google Sheets
   - System will show no new activity
   - Will not appear in future reports (no payments in date range)
   - Leave the data intact for historical records
   
2. **New Loan:** Treat as a new loan
   - Create new amortization schedule in Google Drive folder
   - Name it with new loan ID
   - Run "Import Amortization Schedules" to add to system
   - Start entering payments for new loan ID in Google Sheets

**Manual Steps Required:**
- CFO tracks that refinance occurred (outside this system)
- No data deletion needed in system - old loan just goes dormant

### Payment Reversals / Refunds

**What It Is:** Bank reverses a payment (NSF check, dispute, refund issued)

**How Often:** Once per quarter (rare)

**How System Handles It:** **Manually** (not automated)

**Manual Process:**
1. Identify the payment in Supabase `payments_log` table
2. Note which loan and schedule rows were affected
3. Option A: Delete the payment record (cleanest if caught early)
4. Option B: Add a negative payment entry to offset (if accounting already closed)
5. Re-run "Process Payments" to recalculate affected schedule
6. Verify loan balance is correct in schedule table

**Who Does This:** CFO or someone with Supabase database access

**Future Enhancement:** Add a "Reverse Payment" feature to UI (see Roadmap)

### Charge-Offs / Defaults

**What It Is:** Loan goes into default, company writes off the debt

**How System Handles It:** **Passively** (no special handling)

**Process:**
1. Stop entering payments for that loan in Google Sheets
2. Loan will show no activity in future reports
3. Historical data remains intact for audit trail
4. Loan schedule in Supabase stays as-is (frozen in time)

**Accounting Impact:**
- Loan won't appear in monthly reports (no payments in date range)
- Historical reports will still show past payments collected
- CFO handles write-off entry in QuickBooks separately

**No System Changes Needed** - Dormant loans naturally disappear from cash basis reports

### Manual Adjustments

**What It Is:** Data correction needed (wrong amount entered, date typo, etc.)

**How System Handles It:** **Manually** (not automated)

**Process:**
1. Identify the error (wrong payment amount, wrong date, wrong loan ID)
2. Access Supabase database directly
3. Locate the record in `payments_log` or `schedule_{loan_id}` table
4. Edit the field(s) directly in Supabase
5. If payment was already processed, may need to:
   - Set `processed=False` in `payments_log`
   - Revert changes in `schedule_{loan_id}` table
   - Re-run "Process Payments"

**Who Does This:** CFO (has Supabase credentials)

**Verification:**
- CFO is responsible for verifying data accuracy before sending to accounting
- If report numbers look wrong, CFO investigates before delivering

**Future Enhancement:** Add audit trail for manual changes (see Roadmap)

---

## Current Reports

### Summary Report (Primary)

**Purpose:** Monthly cash basis totals for QuickBooks entry

**When Used:** Every month by accounting team

**What It Shows:**
- Total Principal Paid
- Total Interest Paid
- Total Late Fees Collected
- For the specified date range (based on `payment_date`)

**Format:** CSV with single row of totals

**Example Output:**
```
Principal,Interest,LateFees
45000.00,12500.00,325.00
```

**How Accounting Uses It:**
- Open CSV in Excel
- Copy three numbers
- Create journal entry in QuickBooks:
  - Debit: Cash $57,825
  - Credit: Loan Principal $45,000
  - Credit: Interest Income $12,500
  - Credit: Late Fee Income $325

### Day-Breakdown Report (Supplementary)

**Purpose:** See daily cash flow during a period

**When Used:** Occasionally, when CFO wants to analyze cash patterns

**What It Shows:**
- Principal, Interest, Fees for **each day** in date range
- Multiple rows, one per payment date

**Example Output:**
```
PaymentDate,Principal,Interest,LateFees
2025-12-01,2500.00,800.00,0.00
2025-12-02,3200.00,950.00,25.00
2025-12-03,1800.00,600.00,0.00
...
```

**Use Cases:**
- Identify which days had high collection activity
- Spot patterns in customer payment behavior
- Cash flow forecasting

### Loan-Breakdown Report (Supplementary)

**Purpose:** See performance by individual loan

**When Used:** Occasionally, for loan portfolio analysis

**What It Shows:**
- Principal, Interest, Fees for **each loan** in date range
- Multiple rows, one per loan ID

**Example Output:**
```
LoanId,Principal,Interest,LateFees
ABC123,5000.00,1200.00,25.00
DEF456,3500.00,950.00,0.00
GHI789,2200.00,600.00,50.00
...
```

**Use Cases:**
- Identify which loans generate most revenue
- Spot problem loans (high late fees)
- Portfolio composition analysis

### Full-Breakdown Report (Supplementary)

**Purpose:** Most detailed view - combine loan and date

**When Used:** Rarely, for deep investigation

**What It Shows:**
- Principal, Interest, Fees for **each loan + date combination**
- Many rows (every payment broken out)

**Example Output:**
```
LoanId,PaymentDate,Principal,Interest,LateFees
ABC123,2025-12-05,500.00,150.00,0.00
ABC123,2025-12-20,500.00,150.00,0.00
DEF456,2025-12-03,350.00,95.00,25.00
...
```

**Use Cases:**
- Trace specific payment history
- Audit individual transactions
- Reconcile discrepancies

---

## Future Roadmap

### Phase 1: High Priority (Next 3-6 Months)

#### 1. Email Delivery of Reports
**Problem:** CFO has to remember to generate and download reports monthly
**Solution:** Automated email delivery
**Details:**
- Schedule: Run automatically on 1st of each month
- Generate summary report for previous month
- Email to: CFO, CFO's assistant, accounting team
- Include CSV attachment + summary in email body
- Configuration: Email addresses in config file

**Technical Approach:**
- Add email service integration (SendGrid or SMTP)
- Create scheduled job (cron or Cloud Scheduler)
- Add email template for reports
- Include error notifications if generation fails

#### 2. Discrepancy Resolution Process
**Problem:** When reconciliation errors occur, no documented process to fix them
**Solution:** Formal resolution workflow
**Details:**
- Document common discrepancy types and fixes
- Create checklist for CFO to follow
- Add logging of resolution actions
- Consider UI button for "Mark as Reviewed" for errors

**Documentation Needed:**
- What causes reconciliation errors?
- How to identify the root cause?
- Step-by-step fix procedures
- When to manually adjust vs re-process?

#### 3. Manual Adjustment Audit Trail
**Problem:** Direct Supabase edits leave no record of who changed what
**Solution:** Track all manual changes
**Details:**
- Add `audit_log` table capturing:
  - Who made the change (user ID or name)
  - When (timestamp)
  - What changed (table, record ID, old value, new value)
  - Why (notes field for explanation)
- CFO enters reason when making manual adjustments
- Generate "Changes Report" for auditors

**Technical Approach:**
- Create audit log table in Supabase
- Add triggers to track changes on key tables
- Build UI form for entering manual adjustments (instead of direct DB edits)
- Add "View Audit Trail" report in UI

### Phase 2: Medium Priority (6-12 Months)

#### 4. Accrual Basis Reporting
**Problem:** Currently only cash basis (payments received), may need accrual for GAAP compliance
**Solution:** Track both earned and collected interest
**Details:**
- Add "Interest Earned" report (based on `scheduledinterest` field)
- Add "Interest Collected" report (based on `interestpaid` field)
- Show variance between earned and collected
- Support both cash and accrual accounting methods

**Use Case:**
- GAAP financial statements require accrual basis
- Investors want to see earned revenue, not just collected
- Better matches revenue to periods

#### 5. Enhanced Reports with Additional Data
**Problem:** Accounting team may need more context than just principal/interest/fees
**Solution:** Add optional fields to reports
**Details:**
- Loan balances (beginning, ending for period)
- Payment counts (number of payments, number of customers)
- Customer names (for transaction-level reports)
- Payment methods (if tracked)
- Loan statuses (active, paid off, defaulted)

**Technical Approach:**
- Add optional columns to report generation
- Allow user to select which fields to include
- Consider separate "Detailed Report" vs "Summary Report"

#### 6. Data Validation Before Accounting Handoff
**Problem:** CFO manually checks data accuracy - could be automated
**Solution:** Automated validation checklist
**Details:**
- Run checks before generating report:
  - Any unprocessed payments?
  - Any reconciliation errors?
  - Any missing schedules?
  - Balance totals match expected ranges?
- Display validation results in UI
- Require CFO to acknowledge any warnings before downloading
- "Sign off" button to confirm data accuracy

**Validation Rules:**
- All payments in date range are processed
- No reconciliation errors in period
- Total payments match expected volume (flag if unusually high/low)
- All loans have schedules imported

### Phase 3: Future (12+ Months)

#### 7. Direct QuickBooks Integration
**Problem:** Manual data entry into QuickBooks is time-consuming and error-prone
**Solution:** API integration to post journal entries automatically
**Details:**
- Connect to QuickBooks API
- Automatically create journal entries for monthly totals
- Map principal/interest/fees to correct QB accounts
- Provide reconciliation report (system vs QB)

**Benefits:**
- Eliminates manual entry errors
- Faster month-end close
- Real-time accounting (could post daily if desired)

**Challenges:**
- QuickBooks API complexity
- Account mapping configuration
- Error handling if posting fails

#### 8. Audit Trail Access for External Auditors
**Problem:** Auditors may need to verify payment data and calculations
**Solution:** Read-only access for auditors
**Details:**
- Create auditor user role with restricted permissions
- Provide reports showing:
  - All payments received in period
  - How each payment was allocated
  - Ending balances for all loans
  - Calculation methodology documentation
- Include transaction-level details (payment ID, date, amounts)

**Technical Approach:**
- Add user authentication system (replace simple password)
- Role-based access control (RBAC)
- Auditor role: Read-only, no processing/editing
- Export full transaction log for auditor review

#### 9. Automated Discrepancy Detection and Alerts
**Problem:** Errors only discovered when generating reports
**Solution:** Real-time monitoring and alerts
**Details:**
- After each "Process Payments" run, check for:
  - Reconciliation errors
  - Unusually large payments (potential data entry errors)
  - Missing schedules for new loan IDs
  - Loans with no activity for 60+ days
- Send alerts to CFO via email or Slack
- Include details and suggested actions

**Alert Types:**
- Critical: Reconciliation error (needs immediate attention)
- Warning: Missing schedule (may need import)
- Info: Loan payoff detected (FYI)

---

## Configuration & Access

### System Access

**Streamlit UI:**
- URL: (Google Cloud Run deployment URL)
- Password: `Kingdom2025!$$`
- Users: CFO, CFO's assistant, Finance team
- Browser: Any modern browser (Chrome, Firefox, Safari)

**Supabase Database:**
- URL: `https://puwcyhbjchkfvvaccacg.supabase.co`
- Access: CFO only (service role key required)
- Use: Manual adjustments, data investigation
- Dashboard: Supabase web interface for direct table access

**Google Sheets:**
- Source Payments Sheet: [Link](https://docs.google.com/spreadsheets/d/14aPTzhbjpRXXTjzLWbOtj5ZFiNhbWAGmgmXzkwkAvU8)
- Amortization Schedules Folder: [Link](https://drive.google.com/drive/folders/1u5nAuQVIRosLsZgPPuPLmRriGRyQf60s)
- Access: Finance team (for data entry)

### Financial Settings

**Late Fees:**
- Amount: $25 flat fee
- Grace Period: 3 days after due date
- Charged: Once per scheduled payment
- Change: Edit `DEFAULT_LATE_FEE` in `src/config.py`

**Payment Processing Rules:**
- Tolerance: $10 shortfall allowed
- Threshold: Payment must be ≥90% of scheduled
- Max Forward Payments: 2 installments ahead
- Curtailment: Payment >2× scheduled → extra principal
- Change: Edit constants in `src/payment_processor.py`

**Accrual Accounting:**
- Method: Cash basis (recognize when collected)
- Period Assignment: Based on `payment_date` field
- Change: (Future enhancement - see Roadmap Phase 2)

### Data Retention

**Forever (Permanent):**
- All payment records in `payments_log`
- All schedule tables (`schedule_{loan_id}`)
- All loan records in `loans` table
- Rationale: Audit trail, historical analysis, compliance

**No Automatic Deletion:**
- Closed loans remain in database
- Paid-off loans show in historical reports
- Defaulted loans preserved for records

**Backup:**
- Supabase provides automatic daily backups
- CFO should periodically export critical data to CSV for offline storage

### Environment Variables

**Required for System Operation:**
```
SUPABASE_URL="https://puwcyhbjchkfvvaccacg.supabase.co"
SUPABASE_SERVICE_ROLE_KEY="<secret_key>"
GOOGLE_SERVICE_ACCOUNT_JSON='{"type": "service_account", ...}'
```

**Optional (have defaults in config.py):**
```
SOURCE_PAYMENTS_SHEET_ID
PAYMENTS_LOG_SHEET_ID
DAILY_SUMMARY_REPORT_SHEET_ID
AMORTIZATION_SCHEDULES_FOLDER_ID
```

### Logs

**Location:** `logs/` directory
**Format:** Date-stamped log files
**Contents:** 
- All operations (fetch, process, report)
- Errors and warnings
- Reconciliation issues
- Missing schedules

**Retention:** Keep indefinitely, or archive annually

---

## Frequently Asked Questions

**Q: How do I add a new loan to the system?**
A: Create the amortization schedule in Google Sheets in the Schedules folder, name it with the loan ID, then run "Import Amortization Schedules" in the UI.

**Q: What if I run "Fetch Payments" twice by mistake?**
A: No problem! The system deduplicates automatically. Each payment is only counted once.

**Q: Why don't I see a loan in my report?**
A: Either no payments were received during the date range, or the loan's schedule hasn't been imported yet.

**Q: Can I delete old loan data?**
A: Not recommended. Keep all data for audit trail and historical analysis. Closed loans don't impact current reports anyway.

**Q: What if a payment doesn't reconcile?**
A: The system will log an error and leave the payment unprocessed. CFO should review the payment details in Supabase and fix any data entry errors, then re-run "Process Payments."

**Q: How do I know if all payments were processed?**
A: Check the "Process Payments" log. It should show "0 payments to process" when done. If unprocessed payments remain, investigate errors.

**Q: Can I generate reports for any date range?**
A: Yes! The system supports any date range, not just calendar months. Useful for fiscal periods or mid-month reporting.

**Q: What happens if two people try to process payments at the same time?**
A: The system uses atomic locking - each payment is claimed by one process. Safe for concurrent use, though not typical workflow.

**Q: Where do I find the password?**
A: It's in this document (`Kingdom2025!$$`) and should be shared only with authorized finance team members.

**Q: How long does processing take?**
A: Fetch: ~10-30 seconds. Process: ~30-60 seconds for 100 payments. Report generation: ~5-10 seconds. Total workflow: Under 2 minutes.

---

## Contact & Support

**Primary Contact:** Gustavo Camilo (System Owner)

**For Questions About:**
- System operation → CFO or Finance Team Lead
- Data accuracy → CFO (data validation authority)
- Technical issues → Gustavo Camilo or Development Team
- Accounting requirements → Accounting Team or CFO

**Issue Reporting:**
- Document errors in logs/
- Screenshot any UI errors
- Note loan IDs and payment dates involved
- Send to system owner for investigation

---

## Document Version

**Last Updated:** January 8, 2026
**System Version:** Production
**Next Review:** Quarterly or when major features added

---

*This documentation is intended to provide complete context for anyone joining the Kingdom Auto Finance team or working on this system. If anything is unclear or you have suggestions for improvement, please contact the system owner.*
