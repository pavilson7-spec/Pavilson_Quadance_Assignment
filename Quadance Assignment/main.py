import csv
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from datetime import datetime
from pathlib import Path

SUPPORTED_DATE_FORMATS = (
    "%Y-%m-%d",  # ISO 8601 hyphen (e.g., 2026-09-02)
    "%Y/%m/%d",  # ISO 8601 slash (e.g., 2026/09/04)
    "%d/%m/%Y",  # Day-Month-Year slash (e.g., 03/09/2026)
    "%d-%m-%Y",  # Day-Month-Year hyphen (e.g., 05-09-2026)
)

VALID_STATUSES = {"paid", "pending", "cancelled", "refund"}


CURRENCY_SYMBOLS = ("$", "\u20ac", "\u00a3", "\u00a5", "\u20b9")


def _decimal_part_is_valid(decimal_part: str) -> bool:
    """Money values may include one or two decimal places, but not more."""
    return decimal_part.isdigit() and 1 <= len(decimal_part) <= 2


def normalize_customer_name(raw_name: str) -> tuple[str, list[str]]:
    """
    Normalizes customer name by stripping surrounding whitespace,
    collapsing internal whitespace, and applying consistent title capitalization
    while preserving apostrophes, hyphens, and Unicode characters.
    Returns (normalized_name, issues).
    """
    cleaned = raw_name.strip()
    if not cleaned:
        return "", ["MISSING_CUSTOMER_NAME"]

    tokens = cleaned.split()
    normalized_tokens = []
    for token in tokens:
        hyphen_parts = token.split("-")
        norm_hyphen_parts = []
        for h_part in hyphen_parts:
            apostrophe_parts = h_part.split("'")
            norm_apostrophe_parts = [p.capitalize() for p in apostrophe_parts]
            norm_hyphen_parts.append("'".join(norm_apostrophe_parts))
        normalized_tokens.append("-".join(norm_hyphen_parts))

    normalized = " ".join(normalized_tokens)
    return normalized, []


def normalize_date(raw_date: str) -> tuple[str, list[str]]:
    """
    Parses and normalizes dates to YYYY-MM-DD using supported formats.
    Rejects impossible dates, malformed strings, and unsupported formats.
    Returns (normalized_date_str, issues).
    """
    cleaned = raw_date.strip()
    if not cleaned:
        return "", ["MISSING_TRANSACTION_DATE"]

    for fmt in SUPPORTED_DATE_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            # Confidently interpreted date in YYYY-MM-DD format
            return dt.strftime("%Y-%m-%d"), []
        except ValueError:
            pass

    return "", ["INVALID_TRANSACTION_DATE"]


def normalize_amount(raw_amount: str) -> tuple[Decimal | None, str, list[str]]:
    """
    Normalizes monetary amount into Decimal and a two-decimal place string.
    Distinguishes regional formats (1,234.56 vs 1.234,56), handles currency symbols,
    accounting parentheses for negatives, and checks for non-finite, negative,
    and zero values. Single-separator values with exactly three digits after the
    separator, such as 1,234 and 1.234, are interpreted as thousands-grouped
    integers; one or two trailing digits are interpreted as decimal places.
    Returns (amount_decimal, normalized_amount_str, issues).
    """
    cleaned = raw_amount.strip().strip('"').strip("'").strip()
    if not cleaned:
        return None, "", ["MISSING_AMOUNT"]

    is_negative = False

    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()

    for symbol in CURRENCY_SYMBOLS:
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.strip()

    if cleaned.startswith("-"):
        is_negative = True
        cleaned = cleaned[1:].strip()
    elif cleaned.endswith("-"):
        is_negative = True
        cleaned = cleaned[:-1].strip()
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:].strip()

    if not cleaned:
        return None, "", ["INVALID_AMOUNT"]

    if cleaned.lower() in ("nan", "infinity", "+infinity", "-infinity", "inf", "+inf", "-inf"):
        return None, "", ["INVALID_AMOUNT"]

    has_comma = "," in cleaned
    has_dot = "." in cleaned
    canonical_str = None

    if has_comma and has_dot:
        last_comma = cleaned.rfind(",")
        last_dot = cleaned.rfind(".")

        if last_comma < last_dot:
            if cleaned.count(".") != 1:
                return None, "", ["INVALID_AMOUNT"]
            integer_part, decimal_part = cleaned.split(".")
            groups = integer_part.split(",")
            if not groups[0].isdigit() or not (1 <= len(groups[0]) <= 3):
                return None, "", ["INVALID_AMOUNT"]
            for grp in groups[1:]:
                if not grp.isdigit() or len(grp) != 3:
                    return None, "", ["INVALID_AMOUNT"]
            if not _decimal_part_is_valid(decimal_part):
                return None, "", ["INVALID_AMOUNT"]
            canonical_str = "".join(groups) + "." + decimal_part
        elif last_dot < last_comma:
            if cleaned.count(",") != 1:
                return None, "", ["INVALID_AMOUNT"]
            integer_part, decimal_part = cleaned.split(",")
            groups = integer_part.split(".")
            if not groups[0].isdigit() or not (1 <= len(groups[0]) <= 3):
                return None, "", ["INVALID_AMOUNT"]
            for grp in groups[1:]:
                if not grp.isdigit() or len(grp) != 3:
                    return None, "", ["INVALID_AMOUNT"]
            if not _decimal_part_is_valid(decimal_part):
                return None, "", ["INVALID_AMOUNT"]
            canonical_str = "".join(groups) + "." + decimal_part
        else:
            return None, "", ["INVALID_AMOUNT"]

    elif has_comma:
        comma_count = cleaned.count(",")
        if comma_count == 1:
            left, right = cleaned.split(",")
            if not left.isdigit() or not right.isdigit():
                return None, "", ["INVALID_AMOUNT"]
            if len(right) == 3 and 1 <= len(left) <= 3 and left != "0":
                canonical_str = left + right
            else:
                if not _decimal_part_is_valid(right):
                    return None, "", ["INVALID_AMOUNT"]
                canonical_str = left + "." + right
        else:
            groups = cleaned.split(",")
            if not groups[0].isdigit() or not (1 <= len(groups[0]) <= 3):
                return None, "", ["INVALID_AMOUNT"]
            for grp in groups[1:]:
                if not grp.isdigit() or len(grp) != 3:
                    return None, "", ["INVALID_AMOUNT"]
            canonical_str = "".join(groups)

    elif has_dot:
        dot_count = cleaned.count(".")
        if dot_count == 1:
            left, right = cleaned.split(".")
            if not left.isdigit() or not right.isdigit():
                return None, "", ["INVALID_AMOUNT"]
            if len(right) == 3 and 1 <= len(left) <= 3 and left != "0":
                # European-style thousands separator: e.g., 1.234 -> 1234.00
                canonical_str = left + right
            else:
                if not _decimal_part_is_valid(right):
                    return None, "", ["INVALID_AMOUNT"]
                canonical_str = left + "." + right
        else:
            # Multiple dots: European thousands separators (e.g. 1.234.567)
            groups = cleaned.split(".")
            if not groups[0].isdigit() or not (1 <= len(groups[0]) <= 3):
                return None, "", ["INVALID_AMOUNT"]
            for grp in groups[1:]:
                if not grp.isdigit() or len(grp) != 3:
                    return None, "", ["INVALID_AMOUNT"]
            canonical_str = "".join(groups)

    else:
        # Digits only
        if not cleaned.isdigit():
            return None, "", ["INVALID_AMOUNT"]
        canonical_str = cleaned

    if is_negative:
        canonical_str = "-" + canonical_str

    try:
        val = Decimal(canonical_str)
    except (InvalidOperation, ValueError):
        return None, "", ["INVALID_AMOUNT"]

    if not val.is_finite():
        return None, "", ["INVALID_AMOUNT"]

    issues = []
    if val < 0:
        issues.append("NEGATIVE_AMOUNT")
    elif val == 0:
        issues.append("ZERO_AMOUNT")

    normalized_str = f"{val:.2f}"
    return val, normalized_str, issues


def normalize_status(raw_status: str) -> tuple[str, list[str]]:
    """
    Normalizes transaction status to lowercase and checks against canonical set.
    Returns (normalized_status, issues).
    """
    cleaned = raw_status.strip().lower()
    if not cleaned:
        return "", ["MISSING_STATUS"]
    if cleaned not in VALID_STATUSES:
        return "", ["UNKNOWN_STATUS"]
    return cleaned, []


def normalize_transaction_id(raw_id: str) -> tuple[str, list[str]]:
    """
    Normalizes transaction ID by stripping whitespace. Blank IDs are flagged
    as missing data rather than duplicate IDs.
    Returns (normalized_id, issues).
    """
    cleaned = raw_id.strip()
    if not cleaned:
        return "", ["MISSING_TRANSACTION_ID"]
    return cleaned, []


def process_transactions(rows: list[dict]) -> tuple[list[dict], dict]:
    """
    Performs full field normalization, row validation, duplicate detection,
    and metrics calculation on raw CSV dictionary rows.
    """
    records = []

    for idx, r in enumerate(rows, start=1):
        raw_id = r.get("transaction_id", "")
        raw_name = r.get("customer_name", "")
        raw_amount = r.get("amount", "")
        raw_date = r.get("transaction_date", "")
        raw_status = r.get("status", "")
        raw_order = r.get("order_id", "")

        issues = []

        norm_id, id_issues = normalize_transaction_id(raw_id)
        issues.extend(id_issues)

        norm_name, name_issues = normalize_customer_name(raw_name)
        issues.extend(name_issues)

        amt_dec, norm_amount, amt_issues = normalize_amount(raw_amount)
        issues.extend(amt_issues)

        norm_date, date_issues = normalize_date(raw_date)
        issues.extend(date_issues)

        norm_status, status_issues = normalize_status(raw_status)
        issues.extend(status_issues)

        is_valid = len(issues) == 0

        records.append({
            "row_index": idx,
            "transaction_id": raw_id,
            "transaction_id_normalized": norm_id,
            "customer_name": raw_name,
            "customer_name_normalized": norm_name,
            "amount": raw_amount,
            "amount_decimal": amt_dec,
            "amount_normalized": norm_amount,
            "transaction_date": raw_date,
            "transaction_date_normalized": norm_date,
            "status": raw_status,
            "status_normalized": norm_status,
            "order_id": raw_order,
            "order_id_normalized": raw_order.strip(),
            "is_valid": is_valid,
            "validation_issues": issues,
            "is_repeated_id": False,
            "is_repeated_id_collision": False,
            "is_potential_duplicate": False,
            "is_potential_duplicate_exclusion": False,
            "duplicate_classification": "none",
            "duplicate_reference": "",
        })

    id_counts = Counter()
    for rec in records:
        tid = rec["transaction_id_normalized"]
        if tid:
            id_counts[tid] += 1

    repeated_id_set = {tid for tid, count in id_counts.items() if count > 1}
    repeated_id_occurrences = defaultdict(list)

    for rec in records:
        tid = rec["transaction_id_normalized"]
        if tid in repeated_id_set:
            rec["is_repeated_id"] = True
            repeated_id_occurrences[tid].append(rec)

    for tid, occ_list in repeated_id_occurrences.items():
        total_occ = len(occ_list)
        for seq, rec in enumerate(occ_list, start=1):
            role = "primary" if seq == 1 else "duplicate_occurrence"
            ref = f"repeated_id:{tid};occurrence:{seq}/{total_occ};{role}"
            rec["duplicate_reference"] = ref
            rec["is_repeated_id_collision"] = seq > 1

   
    candidate_groups = defaultdict(list)
    for rec in records:
        if (
            rec["customer_name_normalized"]
            and rec["transaction_date_normalized"]
            and rec["amount_normalized"]
            and rec["status_normalized"]
            and rec["transaction_id_normalized"]
            and rec["amount_decimal"] is not None
            and rec["amount_decimal"] > 0
        ):
            key = (
                rec["customer_name_normalized"],
                rec["transaction_date_normalized"],
                rec["amount_normalized"],
                rec["order_id_normalized"],
                rec["status_normalized"],
            )
            candidate_groups[key].append(rec)

    pot_dup_groups = []
    
    for key in sorted(candidate_groups.keys(), key=lambda k: (k[0], k[1], k[2], k[3], k[4])):
        group = candidate_groups[key]
        if len(group) > 1:
            distinct_ids = {r["transaction_id_normalized"] for r in group}
            if len(distinct_ids) > 1:
                pot_dup_groups.append(group)

    pot_dup_group_details = []
    for g_idx, group in enumerate(pot_dup_groups, start=1):
        first_rec = group[0]
        first_tid = first_rec["transaction_id_normalized"] or f"row_{first_rec['row_index']}"
        other_tids = [r["transaction_id_normalized"] or f"row_{r['row_index']}" for r in group[1:]]

        pot_dup_group_details.append({
            "group_id": g_idx,
            "customer_name": first_rec["customer_name_normalized"],
            "transaction_date": first_rec["transaction_date_normalized"],
            "amount": first_rec["amount_normalized"],
            "order_id": first_rec["order_id_normalized"],
            "status": first_rec["status_normalized"],
            "first_occurrence_transaction_id": first_tid,
            "duplicate_transaction_ids": other_tids,
            "total_rows_in_group": len(group),
        })

        for seq, rec in enumerate(group):
            rec["is_potential_duplicate"] = True
            if seq == 0:
                pot_ref = f"potential_dup_group:{g_idx};original"
            else:
                pot_ref = f"potential_dup_group:{g_idx};duplicate_of:{first_tid}"
                rec["is_potential_duplicate_exclusion"] = True

            if rec["duplicate_reference"]:
                rec["duplicate_reference"] += f";{pot_ref}"
            else:
                rec["duplicate_reference"] = pot_ref

    
    for rec in records:
        classes = []
        if rec["is_repeated_id"]:
            classes.append("repeated_id")
        if rec["is_potential_duplicate"]:
            classes.append("potential_duplicate")
        rec["duplicate_classification"] = ";".join(classes) if classes else "none"

    
    input_rows_count = len(records)
    valid_rows_count = sum(1 for r in records if r["is_valid"])
    invalid_rows_count = sum(1 for r in records if not r["is_valid"])

    repeated_id_affected_rows = sum(1 for r in records if r["is_repeated_id"])
    pot_dup_affected_rows = sum(1 for r in records if r["is_potential_duplicate"])

    issue_counter = Counter()
    for r in records:
        for issue in r["validation_issues"]:
            issue_counter[issue] += 1

    
    valid_paid_records = [
        r for r in records if r["is_valid"] and r["status_normalized"] == "paid"
    ]
    gross_paid_revenue = sum(
        (r["amount_decimal"] for r in valid_paid_records), Decimal("0.00")
    )

    
    pot_dup_excluded = [
        r for r in valid_paid_records
        if r["is_potential_duplicate_exclusion"]
    ]
    pot_dup_deduction = sum(
        (r["amount_decimal"] for r in pot_dup_excluded), Decimal("0.00")
    )

    repeated_id_excluded = [
        r for r in valid_paid_records
        if r["is_repeated_id_collision"]
    ]
    repeated_id_deduction = sum(
        (r["amount_decimal"] for r in repeated_id_excluded), Decimal("0.00")
    )

    
    unique_excluded_dict = {}
    for r in pot_dup_excluded:
        unique_excluded_dict[r["row_index"]] = r
    for r in repeated_id_excluded:
        unique_excluded_dict[r["row_index"]] = r

    unique_excluded_duplicate_records = [
        unique_excluded_dict[idx] for idx in sorted(unique_excluded_dict.keys())
    ]
    unique_excluded_duplicate_amount = sum(
        (r["amount_decimal"] for r in unique_excluded_duplicate_records), Decimal("0.00")
    )
    unique_excluded_duplicate_count = len(unique_excluded_duplicate_records)

    excluded_row_indices = set(unique_excluded_dict.keys())
    net_dedup_paid_records = [
        r for r in valid_paid_records if r["row_index"] not in excluded_row_indices
    ]
    net_dedup_revenue = sum(
        (r["amount_decimal"] for r in net_dedup_paid_records), Decimal("0.00")
    )

    report_data = {
        "summary": {
            "input_rows": input_rows_count,
            "valid_rows": valid_rows_count,
            "invalid_rows": invalid_rows_count,
            "reconciliation_check": (
                f"input_rows == valid_rows + invalid_rows "
                f"({input_rows_count} == {valid_rows_count} + {invalid_rows_count})"
            ),
        },
        "input_rows": input_rows_count,
        "valid_rows": valid_rows_count,
        "invalid_rows": invalid_rows_count,
        "duplicate_transaction_id_counts": {
            "unique_repeated_ids": len(repeated_id_set),
            "affected_rows": repeated_id_affected_rows,
            "repeated_occurrences": repeated_id_affected_rows - len(repeated_id_set),
            "details": {
                tid: {
                    "count": len(repeated_id_occurrences[tid]),
                    "row_indices": [r["row_index"] for r in repeated_id_occurrences[tid]],
                }
                for tid in sorted(repeated_id_set)
            },
        },
        "potential_duplicate_group_counts": {
            "duplicate_groups": len(pot_dup_groups),
            "affected_rows": pot_dup_affected_rows,
            "repeated_occurrences": pot_dup_affected_rows - len(pot_dup_groups),
            "matching_criteria": [
                "normalized_customer_name",
                "normalized_transaction_date",
                "normalized_amount",
                "order_id",
                "normalized_status",
            ],
            "groups": pot_dup_group_details,
        },
        "validation_issues_summary": dict(sorted(issue_counter.items())),
        "total_revenue": f"{net_dedup_revenue:.2f}",
        "revenue_policy": (
            "Deduplicated valid paid transactions: sums normalized amounts for all valid records "
            "(is_valid == true) with normalized status 'paid', retaining the primary (first observed) "
            "transaction and strictly excluding duplicate occurrences (subsequent potential duplicates "
            "and subsequent repeated transaction ID collisions) to prevent double-counting."
        ),
        "financial_breakdown": {
            "gross_valid_paid_amount": f"{gross_paid_revenue:.2f}",
            "gross_valid_paid_count": len(valid_paid_records),
            "deductions": {
                "potential_duplicate_occurrences_amount": f"{pot_dup_deduction:.2f}",
                "potential_duplicate_occurrences_count": len(pot_dup_excluded),
                "repeated_id_collision_occurrences_amount": f"{repeated_id_deduction:.2f}",
                "repeated_id_collision_occurrences_count": len(repeated_id_excluded),
                "unique_combined_duplicate_exclusions_amount": f"{unique_excluded_duplicate_amount:.2f}",
                "unique_combined_duplicate_exclusions_count": unique_excluded_duplicate_count,
                "total_excluded_duplicate_amount": f"{unique_excluded_duplicate_amount:.2f}",
                "total_excluded_duplicate_count": unique_excluded_duplicate_count,
            },
            "net_deduplicated_revenue": f"{net_dedup_revenue:.2f}",
            "net_deduplicated_count": len(net_dedup_paid_records),
            "reconciliation_formula": (
                f"gross_valid_paid_amount ({gross_paid_revenue:.2f}) - "
                f"unique_combined_duplicate_exclusions_amount ({unique_excluded_duplicate_amount:.2f}) == "
                f"net_deduplicated_revenue ({net_dedup_revenue:.2f})"
            ),
        },
    }

    return records, report_data


def write_cleaned_csv(records: list[dict], output_path: Path) -> None:
    """
    Writes normalized records to cleaned.csv with standard UTF-8 encoding,
    RFC 4180 CSV escaping, and predictable column ordering.
    """
    fieldnames = [
        "transaction_id",
        "customer_name",
        "customer_name_normalized",
        "amount",
        "amount_normalized",
        "transaction_date",
        "transaction_date_normalized",
        "status",
        "status_normalized",
        "order_id",
        "is_valid",
        "validation_issues",
        "is_repeated_id",
        "is_potential_duplicate",
        "duplicate_classification",
        "duplicate_reference",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow({
                "transaction_id": rec["transaction_id"],
                "customer_name": rec["customer_name"],
                "customer_name_normalized": rec["customer_name_normalized"],
                "amount": rec["amount"],
                "amount_normalized": rec["amount_normalized"],
                "transaction_date": rec["transaction_date"],
                "transaction_date_normalized": rec["transaction_date_normalized"],
                "status": rec["status"],
                "status_normalized": rec["status_normalized"],
                "order_id": rec["order_id"],
                "is_valid": "true" if rec["is_valid"] else "false",
                "validation_issues": ";".join(rec["validation_issues"]),
                "is_repeated_id": "true" if rec["is_repeated_id"] else "false",
                "is_potential_duplicate": "true" if rec["is_potential_duplicate"] else "false",
                "duplicate_classification": rec["duplicate_classification"],
                "duplicate_reference": rec["duplicate_reference"],
            })


def write_report_json(report_data: dict, output_path: Path) -> None:
    """
    Writes report summary to report.json with formatted indentation.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)


def process_file(
    input_file: Path, output_csv: Path, output_json: Path
) -> tuple[int, int, int]:
    """
    Reads input CSV, processes transactions, and writes both output files.
    Handles empty and header-only CSVs safely.
    Returns (input_rows, valid_rows, invalid_rows).
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")

    rows = []
    with open(input_file, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            rows = list(reader)

    records, report_data = process_transactions(rows)

    write_cleaned_csv(records, output_csv)
    write_report_json(report_data, output_json)

    return (
        report_data["input_rows"],
        report_data["valid_rows"],
        report_data["invalid_rows"],
    )


def main():
    base_dir = Path(__file__).resolve().parent
    input_csv_path = base_dir / "input.csv"
    output_csv_path = base_dir / "cleaned.csv"
    report_json_path = base_dir / "report.json"

    # Allow custom CLI arguments if provided
    if len(sys.argv) > 1:
        input_csv_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_csv_path = Path(sys.argv[2])
    if len(sys.argv) > 3:
        report_json_path = Path(sys.argv[3])

    print(f"Reading input from: {input_csv_path}")
    total_in, total_valid, total_invalid = process_file(
        input_csv_path, output_csv_path, report_json_path
    )
    print(f"Processing complete:")
    print(f"  Input rows:   {total_in}")
    print(f"  Valid rows:   {total_valid}")
    print(f"  Invalid rows: {total_invalid}")
    print(f"  Reconciliation: {total_in} == {total_valid} + {total_invalid}")
    print(f"Generated:")
    print(f"  {output_csv_path}")
    print(f"  {report_json_path}")


if __name__ == "__main__":
    main()
