# Challenge 1 — Messy Transactions Normalizer & Validator

## 1. Project Purpose

This project is a high-reliability financial data processing pipeline engineered exclusively using the Python standard library. It reads and processes financial transaction records from an input CSV file (`input.csv`), cleans and normalizes messy data fields (customer names, dates, monetary amounts, and statuses), performs field-level validation, flags duplicate records (repeated transaction IDs and potential duplicate real-world transactions), and generates two reconciled output files:
1. `cleaned.csv` — Full record-level normalized dataset with explicit validation issues and duplicate classifications.
2. `report.json` — Aggregated audit summary with reconciled row counts, issue distributions, and exact decimal financial metrics.

---

## 2. Required Python Version

- **Python 3.10+** (Tested and verified on Python 3.10.0 using the Python Standard Library only; zero external dependencies required).

---

## 3. Project File Structure

```text
Quadance Assignment/
│
├── input.csv          # Original source input CSV (preserved unchanged)
├── main.py           # Core executable application for normalization and validation
├── test_solution.py  # Comprehensive test suite covering unit & integration edge cases
├── cleaned.csv       # Generated output: normalized records with audit issues
├── report.json       # Generated output: audit summary and reconciled financials
└── README.md         # Documentation, assumptions, run instructions, and tested edge cases
```

---

## 4. Run Instructions

### Execution
To execute the pipeline and automatically generate `cleaned.csv` and `report.json`:

```bash
python main.py
```

Optional CLI arguments allow specifying custom input and output paths:
```bash
python main.py [input_csv] [output_csv] [report_json]
```

### Automated Tests
To run the standard-library unittest test suite covering all functional components, edge cases, and financial reconciliations:

```bash
python test_solution.py
```

---

## 5. Input CSV Expectations & Supported Formats

The pipeline processes CSV records containing the following expected columns:
- `transaction_id`: Unique transaction identifier (e.g., `TX0001`).
- `customer_name`: Customer name (may contain whitespace irregularities, inconsistent casing, hyphens, or apostrophes).
- `amount`: Monetary transaction amount (supports US/UK and European formats, comma/dot separators, currency symbols, and accounting negatives).
- `transaction_date`: Date string in an ISO or day-first calendar format.
- `status`: Transaction status (`paid`, `pending`, `cancelled`, or `refund`).
- `order_id`: Commercial order reference (e.g., `ORD004`).

### Supported Formats & Normalization Rules

| Field | Supported Formats / Rules | Example Inputs | Normalized Output |
| :--- | :--- | :--- | :--- |
| **Customer Name** | UTF-8 strings. Trims outer whitespace, collapses internal whitespace, applies title casing while preserving hyphens (`Jean-Luc`), apostrophes (`O'Connor`, `D'Angelo`), and Unicode characters (`Renée`). Blank/empty is rejected. | `"  priya   menon  "`, `"o'connor"`, `"jean-luc"`, `"AARAV SHAH"` | `"Priya Menon"`, `"O'Connor"`, `"Jean-Luc"`, `"Aarav Shah"` |
| **Transaction Date** | Supported formats: `YYYY-MM-DD`, `YYYY/MM/DD`, `DD/MM/YYYY`, `DD-MM-YYYY`. Normalized strictly to `YYYY-MM-DD`. Impossible calendar dates and ambiguous/unsupported formats are rejected. | `"03/09/2026"`, `"2026/09/04"`, `"05-09-2026"`, `"2026-15-08"` | `"2026-09-03"`, `"2026-09-04"`, `"2026-09-05"`, `""` (`INVALID_TRANSACTION_DATE`) |
| **Amount** | Distinguishes US (`1,234.56`) and European (`1.234,56`) formats, currency symbols (`$`, `€`, `£`, `¥`, `₹`), accounting parentheses `(1,234.56)`. Single-separator values with exactly three trailing digits (`1,234`, `1.234`) are documented as thousands-grouped integers. Decimal amounts may use one or two decimal places. Uses `decimal.Decimal` with 2 decimal places. Negative, zero, non-finite, over-precise, and malformed values are flagged. | `"237"`, `"1,470.00"`, `"1.470,00"`, `"1,234"`, `"1.234"`, `"(1,234.56)"`, `"0"`, `"-250"`, `"N/A"` | `"237.00"`, `"1470.00"`, `"1470.00"`, `"1234.00"`, `"1234.00"`, `"-1234.56"` (flagged), `"0.00"` (flagged), `"-250.00"` (flagged), `""` (flagged) |
| **Status** | Canonical set: `paid`, `pending`, `cancelled`, `refund`. Normalized to lowercase; surrounding whitespace trimmed. Unrecognized values flagged as `UNKNOWN_STATUS`. | `"PAID"`, `" paid "`, `"pending"`, `"completed"` | `"paid"`, `"paid"`, `"pending"`, `""` (`UNKNOWN_STATUS`) |
| **Transaction ID** | Non-empty alphanumeric string. Trims whitespace. Blank IDs flagged as `MISSING_TRANSACTION_ID`. | `"TX0001"`, `"   "` | `"TX0001"`, `""` (`MISSING_TRANSACTION_ID`) |

---

## 6. Documented Assumptions

### 1. Customer Name Normalization
- Original names are preserved untouched in `customer_name`.
- Normalized names (`customer_name_normalized`) are deterministic: leading/trailing whitespace removed, consecutive whitespace collapsed to a single space, and word segments capitalized across hyphens and apostrophes.
- Blank or whitespace-only names are flagged with `MISSING_CUSTOMER_NAME` and marked invalid (`is_valid: false`).
- Similarly spelled or phonetic names are never merged or guessed.

### 2. Date Interpretation Convention
- Inspection of `input.csv` reveals a clear date pattern: transactions cycle through days 02, 03, 04, 05, 06, and 07 of September 2026 across records (`2026-09-02`, `03/09/2026`, `2026/09/04`, `05-09-2026`, `2026-09-06`, `07/09/2026`). Furthermore, order `ORD081` contains duplicate records on `2026-09-03` (`TX0070`) and `03/09/2026` (`TX0071`).
- Therefore, dates ending with a 4-digit year follow the day-first convention (`DD/MM/YYYY` and `DD-MM-YYYY`). ISO dates (`YYYY-MM-DD` and `YYYY/MM/DD`) are standard.
- The pipeline never guesses between `DD/MM/YYYY` and `MM/DD/YYYY`. Formats with 2-digit years or ambiguous month-first conventions without explicit metadata are rejected.
- Impossible dates such as `2026-15-08` (month 15), impossible leap dates (e.g., `2025-02-29`), and non-date strings (`not a date`) are rejected with `INVALID_TRANSACTION_DATE`.

### 3. Treatment of Zero and Negative Amounts
- Legitimate transactions must represent positive monetary value ($> 0$).
- Zero amounts (`0`) are flagged with `ZERO_AMOUNT`.
- Negative amounts (`-250`) and accounting parentheses `(250)` are parsed as negative Decimals and flagged with `NEGATIVE_AMOUNT`. As demonstrated by transaction `TX0069` (where an order refund is represented as positive `1200` with status `refund`), refunds in this schema are indicated by status, not negative signs.
- Ambiguous single-separator values are handled deterministically and documented: `1,234` and `1.234` are treated as thousands-grouped integers (`1234.00`). Values with one or two digits after a single separator are treated as decimal amounts (`50,5` -> `50.50`, `50.55` -> `50.55`). Values with unsupported precision, such as `1234.567`, are rejected with `INVALID_AMOUNT`.
- Invalid amounts are never silently converted to zero.
- Non-finite numbers (`NaN`, `Infinity`) and unparseable strings (`N/A`, `oops`) are flagged with `INVALID_AMOUNT`.
- All monetary arithmetic utilizes Python's standard-library `decimal.Decimal` to eliminate binary floating-point rounding errors.

### 4. Status Normalization
- The canonical status set is strictly: `paid`, `pending`, `cancelled`, `refund`.
- Normalized statuses are lowercase. Unknown values are never silently coerced to `paid` and are recorded as `UNKNOWN_STATUS`.
- Missing statuses are flagged as `MISSING_STATUS`.

### 5. Row Validity vs Duplicate Classification
- Row validity (`is_valid`) evaluates independent field-level integrity (valid ID, name, date, positive amount, status).
- Duplicate classification is tracked independently from row-level field validity:
  - If a row's fields are valid, it remains `is_valid: true`, but carries duplicate classification metadata.
  - Every row from `input.csv` is preserved in `cleaned.csv`. No rows are merged, omitted, or deleted.
- Total input rows strictly reconcile: $\text{input\_rows} = \text{valid\_rows} + \text{invalid\_rows}$.

### 6. Duplicate Detection Mechanisms
The pipeline implements two distinct duplicate mechanisms:
1. **Repeated Transaction IDs (Mechanism A):**
   - Detects repeated non-blank IDs (e.g., `TX0008` appearing at rows 8 and 65; `TX0015` appearing at rows 15 and 66).
   - All occurrences (including the first) are flagged with `is_repeated_id: true` and classified with `repeated_id`, noting their occurrence index (e.g. `repeated_id:TX0008;occurrence:1/2`).
   - Blank IDs are treated as missing data (`MISSING_TRANSACTION_ID`), never grouped as duplicate IDs.
2. **Potential Duplicate Transactions (Mechanism B):**
   - Detects records representing the same underlying transaction across different IDs.
   - Matching criteria requires exact equality on all normalized fields: `customer_name_normalized`, `transaction_date_normalized`, `amount_normalized`, `status_normalized`, and `order_id`.
   - Identified in `input.csv`: `TX0070` and `TX0071` (Customer: `Meera Nair`, Date: `2026-09-03`, Amount: `1200.00`, Status: `paid`, Order ID: `ORD081`).
   - `TX0070` is marked as `original`, and `TX0071` is marked as `duplicate_of:TX0070`.
   - Missing optional fields are handled consistently; unrelated records are never grouped merely because optional fields are blank.

### 7. Revenue Calculation & Reconciliation Policy
- **Primary Deduplicated Revenue Rule (`total_revenue` = $85,206.00):**
  Sums normalized amounts for all valid records (`is_valid == true`) with status `paid`, retaining the primary (first observed) instance and strictly excluding duplicate occurrences:
  - Subsequent potential duplicate: `TX0071` ($1,200.00, duplicate of `TX0070`).
  - Subsequent repeated ID collision: `TX0008` row 65 ($1,196.00, collision with row 8).
  - Subsequent repeated ID collision: `TX0015` row 66 ($999.00, collision with row 15).
  Total duplicate deductions: $1,200.00 + $2,195.00 = $3,395.00 (3 transactions).
  Gross valid paid revenue: $88,601.00 (38 transactions).
  Net deduplicated revenue: $88,601.00 - $3,395.00 = $85,206.00 (35 transactions).
  Reconciliation check: $\text{gross} - \text{deductions} = \text{net}$ ($88,601.00 - 3,395.00 = 85,206.00$ and $38 - 3 = 35$).

---

## 7. Output File Descriptions

### `cleaned.csv`
Contains 73 data rows (one-to-one correspondence with `input.csv`) with the following column headers:
1. `transaction_id` — Original transaction ID.
2. `customer_name` — Original customer name.
3. `customer_name_normalized` — Cleaned, title-cased name.
4. `amount` — Original amount string.
5. `amount_normalized` — Normalized 2-decimal string.
6. `transaction_date` — Original date string.
7. `transaction_date_normalized` — Normalized `YYYY-MM-DD` date string.
8. `status` — Original status string.
9. `status_normalized` — Normalized lowercase canonical status.
10. `order_id` — Original order ID.
11. `is_valid` — Boolean string (`true` or `false`).
12. `validation_issues` — Semicolon-delimited list of detected field validation issues (empty if valid).
13. `is_repeated_id` — Boolean string (`true` or `false`).
14. `is_potential_duplicate` — Boolean string (`true` or `false`).
15. `duplicate_classification` — Classification label (`none`, `repeated_id`, `potential_duplicate`, or `repeated_id;potential_duplicate`).
16. `duplicate_reference` — Detailed audit reference (e.g., `repeated_id:TX0008;occurrence:1/2`, `potential_dup_group:1;duplicate_of:TX0070`).

### `report.json`
Structured JSON report providing full audit and financial reconciliation:
- `input_rows`: 73
- `valid_rows`: 59
- `invalid_rows`: 14
- `reconciliation_check`: `73 == 59 + 14`
- `duplicate_transaction_id_counts`:
  - `unique_repeated_ids`: 2 (`TX0008`, `TX0015`)
  - `affected_rows`: 4
  - `repeated_occurrences`: 2
- `potential_duplicate_group_counts`:
  - `duplicate_groups`: 1 (Meera Nair / ORD081 / $1,200.00)
  - `affected_rows`: 2 (`TX0070`, `TX0071`)
  - `repeated_occurrences`: 1
- `validation_issues_summary`: Count of each detected issue (`INVALID_AMOUNT`: 4, `INVALID_TRANSACTION_DATE`: 4, `MISSING_AMOUNT`: 2, `NEGATIVE_AMOUNT`: 2, `MISSING_CUSTOMER_NAME`: 1, `ZERO_AMOUNT`: 1).
- `total_revenue`: `"85206.00"` (exact decimal string).
- `financial_breakdown`: Itemized reconciliation showing gross valid paid revenue ($88,601.00), deductions ($3,395.00), net revenue ($85,206.00), and transaction counts.
- `financial_breakdown.deductions`: Includes category-specific duplicate deductions plus `unique_combined_duplicate_exclusions_*` and `total_excluded_duplicate_*`; the combined/total values are based on unique row identities so an overlapping duplicate row is deducted once.

---

## 8. Executed and Verified Edge Cases

The following edge cases are implemented, tested, and actively verified in `test_solution.py`:

| Test Case | Input Values | Expected Result | Verification Status |
| :--- | :--- | :--- | :--- |
| **Normal Valid Records** | Standard fields, valid format | `is_valid: true`, exact normalized outputs | Verified (`test_normal_valid_records`) |
| **European Amount Format** | `amount: "1.470,00"`, `"€ 1.234,56"` | `amount_normalized: "1470.00"`, `"1234.56"`, `is_valid: true` | Verified (`test_us_and_european_amount_formats`) |
| **US Amount Format** | `amount: '"1,470.00"'`, `"$1,234.56"` | `amount_normalized: "1470.00"`, `"1234.56"`, `is_valid: true` | Verified (`test_us_and_european_amount_formats`) |
| **Ambiguous Single Separators** | `amount: "1,234"`, `"1.234"` | Both documented as thousands-grouped and normalized to `"1234.00"` | Verified (`test_us_and_european_amount_formats`) |
| **Accounting Negatives** | `amount: "(1,234.56)"`, `"(€ 1.234,56)"` | `amount_normalized: "-1234.56"`, flagged `NEGATIVE_AMOUNT` | Verified (`test_us_and_european_amount_formats`) |
| **Zero & Negative Amounts** | `amount: "0"`, `amount: "-250"` | Flagged `ZERO_AMOUNT` and `NEGATIVE_AMOUNT` | Verified (`test_malformed_zero_and_negative_amounts`) |
| **Non-Numeric / Non-Finite** | `amount: "N/A"`, `"NaN"`, `"Infinity"` | Flagged `INVALID_AMOUNT` | Verified (`test_malformed_zero_and_negative_amounts`) |
| **Names with Apostrophes & Hyphens** | `"jean-luc"`, `"o'connor"`, `"D'ANGELO"` | Normalized to `"Jean-Luc"`, `"O'Connor"`, `"D'Angelo"` | Verified (`test_customer_name_normalization_and_unicode`) |
| **Unicode Characters** | `"renée dupont"` | Normalized to `"Renée Dupont"` | Verified (`test_customer_name_normalization_and_unicode`) |
| **Impossible Calendar Date** | `transaction_date: "2026-15-08"`, `"2025-02-29"` | `is_valid: false`, `validation_issues: "INVALID_TRANSACTION_DATE"` | Verified (`test_date_parsing_iso_dayfirst_and_impossible`) |
| **Multiple Simultaneous Errors** | Blank ID, blank name, bad date, bad amount, unknown status | `is_valid: false`, all 5 distinct error codes captured | Verified (`test_multiple_simultaneous_validation_errors`) |
| **Repeated Transaction IDs** | Two records with `transaction_id: "TX100"` | Both flagged `is_repeated_id: true` with occurrence references | Verified (`test_repeated_transaction_id_detection`) |
| **Potential Duplicate Transactions** | `TX201` (`2026-09-03`, $1200) vs `TX202` (`03/09/2026`, $1200.00) | `TX201` marked `original`, `TX202` marked `duplicate_of:TX201`, deduplicated | Verified (`test_potential_duplicates_with_different_ids`) |
| **Missing Optional Fields** | Blank `order_id` across different customers | Unrelated transactions never falsely grouped | Verified (`test_missing_optional_fields_no_false_grouping`) |
| **Empty and Header-Only CSV** | 0-byte file and header-only CSV | Handled gracefully: 0 rows, 0 counts, no crashes | Verified (`test_empty_and_header_only_csv`) |
| **CSV Quotes, Commas, & Unicode** | `order_id: "ORD,SPECIAL,001"`, embedded quotes | Correct RFC 4180 escaping preserved in output CSV | Verified (`test_csv_quotes_commas_and_unicode_handling`) |
| **Financial Reconciliation** | Gross $88,601.00, Deductions $3,395.00, Net $85,206.00 | Exact penny and count reconciliation verified | Verified (`test_end_to_end_reconciliation_on_actual_input`) |
| **Overlapping Duplicate Flags** | One row is both a repeated-ID collision and potential duplicate | Category counts remain visible, but combined duplicate deductions count the row once | Verified (`test_overlapping_duplicate_exclusions_count_once`) |

---

## 9. Limitations & Ambiguity Handling

1. **Ambiguous Two-Digit Date Conventions:**
   Dates with two-digit years (e.g. `03/04/25`) or ambiguous slash formats where month and day could both be $\le 12$ without an established dataset convention are rejected rather than guessed.
2. **Missing Customer Names:**
   Records with blank customer names cannot be matched for potential duplicate transaction groups, as customer identity is an essential matching criterion.
3. **Transaction ID Collisions Across Different Customers:**
   In cases where identical transaction IDs are assigned to completely different customers (e.g., `TX0008` assigned to Neha Das and Aarav Shah), the system flags both as repeated ID conflicts. Because the authoritative primary record cannot be determined without upstream database logs, the report isolates these occurrences in `financial_breakdown`.
