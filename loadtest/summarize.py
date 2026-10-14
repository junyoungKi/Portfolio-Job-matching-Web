"""
Print Locust ``--csv`` result files as a markdown table (p50, p95, RPS, failure rate).

    python loadtest/summarize.py loadtest/results/baseline-warm_stats.csv loadtest/results/fixed-warm_stats.csv
"""
import csv
import os
import sys


def rows(path):
    label = os.path.basename(path).replace("_stats.csv", "")
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            yield label, row


def main(paths):
    print("| Run | Endpoint | Requests | Failures | Failure rate | p50 (ms) | p95 (ms) | RPS |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for path in paths:
        for label, row in rows(path):
            total = int(row["Request Count"])
            failed = int(row["Failure Count"])
            rate = f"{100 * failed / total:.2f}%" if total else "n/a"
            name = "ALL (aggregated)" if row["Name"] == "Aggregated" else row["Name"]
            print(
                f"| {label} | {name} | {total} | {failed} | {rate} | "
                f"{float(row['50%']):.0f} | {float(row['95%']):.0f} | {float(row['Requests/s']):.2f} |"
            )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
