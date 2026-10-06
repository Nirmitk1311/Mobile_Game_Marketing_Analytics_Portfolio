"""Run the reproducible synthetic-data portfolio pipeline."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def run(script: str, *args: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "src" / script), *args], check=True, cwd=ROOT)


if __name__ == "__main__":
    run("generate_synthetic_data.py", "--output", "data/synthetic")
    run("analyze_marketing.py", "--data", "data/synthetic", "--output", "outputs/analysis")
    run("weekly_review.py", "--data", "data/synthetic", "--analysis", "outputs/analysis", "--output", "outputs/weekly")
    run("make_charts.py", "--analysis", "outputs/analysis", "--output", "outputs/charts")
    run("build_reports.py", "--analysis", "outputs/analysis", "--charts", "outputs/charts", "--output", "outputs/reports")
    print("Pipeline complete. Excel dashboards are included as curated portfolio outputs.")
