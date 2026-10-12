import unittest
import csv
import json
from decimal import Decimal
from pathlib import Path
import tempfile

from main import (
    normalize_customer_name,
    normalize_date,
    normalize_amount,
    normalize_status,
    normalize_transaction_id,
    process_transactions,
    process_file,
)

class TestTransactionProcessing(unittest.TestCase):

    def test_normal_valid_records(self):
        row = {
            "transaction_id": "TX9001",
            "customer_name": "Alice Walker",
            "amount": "250.75",
            "transaction_date": "2026-09-01",
            "status": "paid",
            "order_id": "ORD901",
        }
        records, report = process_transactions([row])
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertTrue(rec["is_valid"])
        self.assertEqual(rec["customer_name_normalized"], "Alice Walker")
        self.assertEqual(rec["amount_normalized"], "250.75")
        self.assertEqual(rec["transaction_date_normalized"], "2026-09-01")
        self.assertEqual(rec["status_normalized"], "paid")
        self.assertEqual(rec["validation_issues"], [])
        self.assertEqual(report["summary"]["valid_rows"], 1)
        self.assertEqual(report["summary"]["invalid_rows"], 0)
        self.assertEqual(report["total_revenue"], "250.75")

    def test_customer_name_normalization_and_unicode(self):
        name, issues = normalize_customer_name("  priya   menon  ")
        self.assertEqual(name, "Priya Menon")
        self.assertEqual(issues, [])

        name, issues = normalize_customer_name("AARAV SHAH")
        self.assertEqual(name, "Aarav Shah")
        self.assertEqual(issues, [])

        # Hyphenated names
        name, issues = normalize_customer_name("jean-luc picard")
        self.assertEqual(name, "Jean-Luc Picard")
        self.assertEqual(issues, [])

        name, issues = normalize_customer_name("o'connor")
        self.assertEqual(name, "O'Connor")
        self.assertEqual(issues, [])

        name, issues = normalize_customer_name("D'ANGELO")
        self.assertEqual(name, "D'Angelo")
        self.assertEqual(issues, [])

        name, issues = normalize_customer_name("renée dupont")
        self.assertEqual(name, "Renée Dupont")
        self.assertEqual(issues, [])

        name, issues = normalize_customer_name("")
        self.assertEqual(name, "")
        self.assertEqual(issues, ["MISSING_CUSTOMER_NAME"])

        name, issues = normalize_customer_name("    ")
        self.assertEqual(name, "")
        self.assertEqual(issues, ["MISSING_CUSTOMER_NAME"])

    def test_date_parsing_iso_dayfirst_and_impossible(self):
        d, issues = normalize_date("2026-09-02")
        self.assertEqual(d, "2026-09-02")
        self.assertEqual(issues, [])

        d, issues = normalize_date("2026/09/04")
        self.assertEqual(d, "2026-09-04")
        self.assertEqual(issues, [])

        d, issues = normalize_date("03/09/2026")
        self.assertEqual(d, "2026-09-03")
        self.assertEqual(issues, [])

        d, issues = normalize_date("05-09-2026")
        self.assertEqual(d, "2026-09-05")
        self.assertEqual(issues, [])

        d, issues = normalize_date("2026-15-08")
        self.assertEqual(d, "")
        self.assertEqual(issues, ["INVALID_TRANSACTION_DATE"])

        d, issues = normalize_date("2025-02-29")
        self.assertEqual(d, "")
        self.assertEqual(issues, ["INVALID_TRANSACTION_DATE"])

        d, issues = normalize_date("not a date")
        self.assertEqual(d, "")
        self.assertEqual(issues, ["INVALID_TRANSACTION_DATE"])

        d, issues = normalize_date("")
        self.assertEqual(d, "")
        self.assertEqual(issues, ["MISSING_TRANSACTION_DATE"])

        d, issues = normalize_date("03/09/26")
        self.assertEqual(d, "")
        self.assertEqual(issues, ["INVALID_TRANSACTION_DATE"])

    def test_us_and_european_amount_formats(self):
        val, s, issues = normalize_amount('"1,470.00"')
        self.assertEqual(val, Decimal("1470.00"))
        self.assertEqual(s, "1470.00")
        self.assertEqual(issues, [])

        val, s, issues = normalize_amount("$1,234.56")
        self.assertEqual(val, Decimal("1234.56"))
        self.assertEqual(s, "1234.56")
        self.assertEqual(issues, [])

        val, s, issues = normalize_amount("1.470,00")
        self.assertEqual(val, Decimal("1470.00"))
        self.assertEqual(s, "1470.00")
        self.assertEqual(issues, [])

        val, s, issues = normalize_amount("€ 1.234,56")
        self.assertEqual(val, Decimal("1234.56"))
        self.assertEqual(s, "1234.56")
        self.assertEqual(issues, [])

        val, s, issues = normalize_amount("1234,56")
        self.assertEqual(val, Decimal("1234.56"))
        self.assertEqual(s, "1234.56")
        self.assertEqual(issues, [])


        val, s, issues = normalize_amount("1,234")
        self.assertEqual(val, Decimal("1234"))
        self.assertEqual(s, "1234.00")
        self.assertEqual(issues, [])

        val, s, issues = normalize_amount("1.234")
        self.assertEqual(val, Decimal("1234"))
        self.assertEqual(s, "1234.00")
        self.assertEqual(issues, [])

        val, s, issues = normalize_amount("(1,234.56)")
        self.assertEqual(val, Decimal("-1234.56"))
        self.assertEqual(s, "-1234.56")
        self.assertEqual(issues, ["NEGATIVE_AMOUNT"])

        val, s, issues = normalize_amount("(€ 1.234,56)")
        self.assertEqual(val, Decimal("-1234.56"))
        self.assertEqual(s, "-1234.56")
        self.assertEqual(issues, ["NEGATIVE_AMOUNT"])

    def test_malformed_zero_and_negative_amounts(self):
        val, s, issues = normalize_amount("0")
        self.assertEqual(val, Decimal("0.00"))
        self.assertEqual(s, "0.00")
        self.assertEqual(issues, ["ZERO_AMOUNT"])

        val, s, issues = normalize_amount("$0.00")
        self.assertEqual(val, Decimal("0.00"))
        self.assertEqual(s, "0.00")
        self.assertEqual(issues, ["ZERO_AMOUNT"])

        val, s, issues = normalize_amount("-250")
        self.assertEqual(val, Decimal("-250.00"))
        self.assertEqual(s, "-250.00")
        self.assertEqual(issues, ["NEGATIVE_AMOUNT"])

        val, s, issues = normalize_amount("")
        self.assertIsNone(val)
        self.assertEqual(s, "")
        self.assertEqual(issues, ["MISSING_AMOUNT"])

        val, s, issues = normalize_amount("N/A")
        self.assertIsNone(val)
        self.assertEqual(issues, ["INVALID_AMOUNT"])

        val, s, issues = normalize_amount("oops")
        self.assertIsNone(val)
        self.assertEqual(issues, ["INVALID_AMOUNT"])

        val, s, issues = normalize_amount("NaN")
        self.assertIsNone(val)
        self.assertEqual(issues, ["INVALID_AMOUNT"])

        val, s, issues = normalize_amount("Infinity")
        self.assertIsNone(val)
        self.assertEqual(issues, ["INVALID_AMOUNT"])

        val, s, issues = normalize_amount("12.34.56")
        self.assertIsNone(val)
        self.assertEqual(issues, ["INVALID_AMOUNT"])

        val, s, issues = normalize_amount("1,23.45")
        self.assertIsNone(val)
        self.assertEqual(issues, ["INVALID_AMOUNT"])

        val, s, issues = normalize_amount("1234.567")
        self.assertIsNone(val)
        self.assertEqual(issues, ["INVALID_AMOUNT"])

    def test_status_normalization(self):
        for raw, expected in [
            ("PAID", "paid"),
            (" paid ", "paid"),
            ("PENDING", "pending"),
            ("cancelled", "cancelled"),
            ("refund", "refund"),
        ]:
            s, issues = normalize_status(raw)
            self.assertEqual(s, expected)
            self.assertEqual(issues, [])

        s, issues = normalize_status("completed")
        self.assertEqual(s, "")
        self.assertEqual(issues, ["UNKNOWN_STATUS"])

        s, issues = normalize_status("")
        self.assertEqual(s, "")
        self.assertEqual(issues, ["MISSING_STATUS"])

    def test_multiple_simultaneous_validation_errors(self):
        row = {
            "transaction_id": "",
            "customer_name": "  ",
            "amount": "invalid_num",
            "transaction_date": "bad_date",
            "status": "unknown_status",
            "order_id": "ORD999",
        }
        records, report = process_transactions([row])
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertFalse(rec["is_valid"])
        expected_issues = {
            "MISSING_TRANSACTION_ID",
            "MISSING_CUSTOMER_NAME",
            "INVALID_AMOUNT",
            "INVALID_TRANSACTION_DATE",
            "UNKNOWN_STATUS",
        }
        self.assertEqual(set(rec["validation_issues"]), expected_issues)
        self.assertEqual(report["summary"]["valid_rows"], 0)
        self.assertEqual(report["summary"]["invalid_rows"], 1)

    def test_repeated_transaction_id_detection(self):
        rows = [
            {"transaction_id": "TX100", "customer_name": "Alice", "amount": "100", "transaction_date": "2026-09-01", "status": "paid", "order_id": "ORD1"},
            {"transaction_id": "TX100", "customer_name": "Bob", "amount": "200", "transaction_date": "2026-09-02", "status": "paid", "order_id": "ORD2"},
            {"transaction_id": "TX101", "customer_name": "Charlie", "amount": "300", "transaction_date": "2026-09-03", "status": "paid", "order_id": "ORD3"},
        ]
        records, report = process_transactions(rows)
        self.assertEqual(report["duplicate_transaction_id_counts"]["unique_repeated_ids"], 1)
        self.assertEqual(report["duplicate_transaction_id_counts"]["affected_rows"], 2)
        self.assertEqual(report["duplicate_transaction_id_counts"]["repeated_occurrences"], 1)

        self.assertTrue(records[0]["is_repeated_id"])
        self.assertTrue(records[1]["is_repeated_id"])
        self.assertFalse(records[2]["is_repeated_id"])
        self.assertIn("occurrence:1/2", records[0]["duplicate_reference"])
        self.assertIn("occurrence:2/2", records[1]["duplicate_reference"])

    def test_potential_duplicates_with_different_ids(self):
        rows = [
            {"transaction_id": "TX201", "customer_name": "Meera Nair", "amount": "1200", "transaction_date": "2026-09-03", "status": "paid", "order_id": "ORD081"},
            {"transaction_id": "TX202", "customer_name": " Meera   Nair ", "amount": "1200.00", "transaction_date": "03/09/2026", "status": " paid ", "order_id": "ORD081"},
        ]
        records, report = process_transactions(rows)
        self.assertEqual(report["potential_duplicate_group_counts"]["duplicate_groups"], 1)
        self.assertEqual(report["potential_duplicate_group_counts"]["affected_rows"], 2)
        self.assertEqual(report["potential_duplicate_group_counts"]["repeated_occurrences"], 1)

        self.assertTrue(records[0]["is_potential_duplicate"])
        self.assertTrue(records[1]["is_potential_duplicate"])
        self.assertEqual(records[0]["duplicate_reference"], "potential_dup_group:1;original")
        self.assertEqual(records[1]["duplicate_reference"], "potential_dup_group:1;duplicate_of:TX201")
        self.assertEqual(report["total_revenue"], "1200.00")

    def test_missing_optional_fields_no_false_grouping(self):
        rows = [
            {"transaction_id": "TX301", "customer_name": "Alice", "amount": "100", "transaction_date": "2026-09-01", "status": "paid", "order_id": ""},
            {"transaction_id": "TX302", "customer_name": "Bob", "amount": "100", "transaction_date": "2026-09-01", "status": "paid", "order_id": ""},
        ]
        records, report = process_transactions(rows)
        self.assertEqual(report["potential_duplicate_group_counts"]["duplicate_groups"], 0)
        self.assertFalse(records[0]["is_potential_duplicate"])
        self.assertFalse(records[1]["is_potential_duplicate"])

    def test_empty_and_header_only_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            
            header_csv = Path(tmpdir) / "header_only.csv"
            header_csv.write_text("transaction_id,customer_name,amount,transaction_date,status,order_id\n", encoding="utf-8")
            cleaned_csv = Path(tmpdir) / "cleaned.csv"
            report_json = Path(tmpdir) / "report.json"

            in_rows, valid_rows, invalid_rows = process_file(header_csv, cleaned_csv, report_json)
            self.assertEqual(in_rows, 0)
            self.assertEqual(valid_rows, 0)
            self.assertEqual(invalid_rows, 0)

            with open(report_json, "r", encoding="utf-8") as f:
                rep = json.load(f)
            self.assertEqual(rep["input_rows"], 0)
            self.assertEqual(rep["total_revenue"], "0.00")

            
            empty_csv = Path(tmpdir) / "empty.csv"
            empty_csv.write_text("", encoding="utf-8")
            in_rows, valid_rows, invalid_rows = process_file(empty_csv, cleaned_csv, report_json)
            self.assertEqual(in_rows, 0)

    def test_revenue_calculations_and_non_paid_statuses(self):
        rows = [
            {"transaction_id": "TX401", "customer_name": "Alice", "amount": "100", "transaction_date": "2026-09-01", "status": "paid", "order_id": "ORD1"},
            {"transaction_id": "TX402", "customer_name": "Bob", "amount": "200", "transaction_date": "2026-09-01", "status": "pending", "order_id": "ORD2"},
            {"transaction_id": "TX403", "customer_name": "Charlie", "amount": "300", "transaction_date": "2026-09-01", "status": "cancelled", "order_id": "ORD3"},
            {"transaction_id": "TX404", "customer_name": "Diana", "amount": "400", "transaction_date": "2026-09-01", "status": "refund", "order_id": "ORD4"},
            
            {"transaction_id": "TX405", "customer_name": "Alice", "amount": "100", "transaction_date": "2026-09-01", "status": "paid", "order_id": "ORD1"},
        ]
        records, report = process_transactions(rows)
        
        self.assertEqual(report["financial_breakdown"]["gross_valid_paid_amount"], "200.00")
        self.assertEqual(report["financial_breakdown"]["deductions"]["potential_duplicate_occurrences_amount"], "100.00")
        self.assertEqual(report["total_revenue"], "100.00")

    def test_overlapping_duplicate_exclusions_count_once(self):
        rows = [
            {"transaction_id": "TX701", "customer_name": "Alice", "amount": "100", "transaction_date": "2026-09-01", "status": "paid", "order_id": "ORD1"},
            {"transaction_id": "TX702", "customer_name": "Alice", "amount": "100", "transaction_date": "2026-09-01", "status": "paid", "order_id": "ORD1"},
            {"transaction_id": "TX702", "customer_name": "Alice", "amount": "100", "transaction_date": "2026-09-01", "status": "paid", "order_id": "ORD1"},
        ]
        records, report = process_transactions(rows)
        deductions = report["financial_breakdown"]["deductions"]

        self.assertTrue(records[2]["is_repeated_id_collision"])
        self.assertTrue(records[2]["is_potential_duplicate_exclusion"])
        self.assertEqual(deductions["potential_duplicate_occurrences_count"], 2)
        self.assertEqual(deductions["repeated_id_collision_occurrences_count"], 1)
        self.assertEqual(deductions["unique_combined_duplicate_exclusions_count"], 2)
        self.assertEqual(deductions["total_excluded_duplicate_count"], 2)
        self.assertEqual(deductions["unique_combined_duplicate_exclusions_amount"], "200.00")
        self.assertEqual(report["total_revenue"], "100.00")

    def test_csv_quotes_commas_and_unicode_handling(self):
        row = {
            "transaction_id": "TX501",
            "customer_name": 'Renée "The Queen" Dupont',
            "amount": '"1,500.00"',
            "transaction_date": "2026-09-01",
            "status": "paid",
            "order_id": "ORD,SPECIAL,001",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            in_file = Path(tmpdir) / "special.csv"
            with open(in_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                writer.writeheader()
                writer.writerow(row)

            out_csv = Path(tmpdir) / "out.csv"
            out_json = Path(tmpdir) / "out.json"
            process_file(in_file, out_csv, out_json)

            with open(out_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                out_rows = list(reader)

            self.assertEqual(len(out_rows), 1)
            self.assertEqual(out_rows[0]["amount_normalized"], "1500.00")
            self.assertEqual(out_rows[0]["order_id"], "ORD,SPECIAL,001")
            self.assertTrue(out_rows[0]["is_valid"])

    def test_end_to_end_reconciliation_on_actual_input(self):
        base_dir = Path(__file__).resolve().parent
        input_csv = base_dir / "input.csv"
        self.assertTrue(input_csv.exists(), "input.csv must exist in project root")

        with tempfile.TemporaryDirectory() as tmpdir:
            cleaned_csv = Path(tmpdir) / "cleaned.csv"
            report_json = Path(tmpdir) / "report.json"

            in_rows, valid_rows, invalid_rows = process_file(input_csv, cleaned_csv, report_json)

            self.assertEqual(in_rows, 73)
            self.assertEqual(valid_rows, 59)
            self.assertEqual(invalid_rows, 14)
            self.assertEqual(in_rows, valid_rows + invalid_rows)

            with open(cleaned_csv, "r", encoding="utf-8") as f:
                lines = [l for l in f if l.strip()]
                self.assertEqual(len(lines), 74)

            with open(report_json, "r", encoding="utf-8") as f:
                rep = json.load(f)

            self.assertEqual(rep["input_rows"], 73)
            self.assertEqual(rep["valid_rows"], 59)
            self.assertEqual(rep["invalid_rows"], 14)
            self.assertEqual(rep["duplicate_transaction_id_counts"]["unique_repeated_ids"], 2)
            self.assertEqual(rep["duplicate_transaction_id_counts"]["affected_rows"], 4)
            self.assertEqual(rep["potential_duplicate_group_counts"]["duplicate_groups"], 1)
            self.assertEqual(rep["potential_duplicate_group_counts"]["affected_rows"], 2)

            
            gross = Decimal(rep["financial_breakdown"]["gross_valid_paid_amount"])
            deductions = Decimal(rep["financial_breakdown"]["deductions"]["total_excluded_duplicate_amount"])
            net = Decimal(rep["total_revenue"])
            self.assertEqual(gross - deductions, net)
            self.assertEqual(rep["total_revenue"], "85206.00")
            self.assertEqual(rep["financial_breakdown"]["gross_valid_paid_count"] - rep["financial_breakdown"]["deductions"]["total_excluded_duplicate_count"], rep["financial_breakdown"]["net_deduplicated_count"])


if __name__ == "__main__":
    unittest.main()
