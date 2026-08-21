"""
Download Indian Supreme Court Judgments raw dataset (2021-2025) from AWS Open Data Registry.
Bucket: s3://indian-supreme-court-judgments/
No AWS credentials required (--no-sign-request).

Expected Output Directory Structure:
  indian-sc-data/
    data/
      2021/
        english.tar (or individual PDF files)
      ...
    metadata/
      2021/
        metadata.parquet
      ...
"""

import os
import sys
import subprocess
import shutil

YEARS = [2021, 2022, 2023, 2024, 2025]
S3_BUCKET = "s3://indian-supreme-court-judgments"

def check_aws_cli():
    return shutil.which("aws") is not None

def download_dataset(target_dir="indian-sc-data", dry_run=False):
    print(f"=== Indian Supreme Court Judgments Raw Data Downloader ===")
    print(f"Target Directory: {os.path.abspath(target_dir)}")
    print(f"Years: {YEARS}")
    print(f"Source S3 Bucket: {S3_BUCKET}")
    print("Estimated Download Size: ~15-20 GB total across 2021-2025\n")

    if not check_aws_cli():
        print("❌ Error: 'aws' CLI tool is not installed or not in PATH.")
        print("Please install AWS CLI or run the following command directly:")
        print("  brew install awscli  # macOS")
        print("  or refer to https://aws.amazon.com/cli/")
        sys.exit(1)

    for year in YEARS:
        data_dir = os.path.join(target_dir, "data", str(year))
        meta_dir = os.path.join(target_dir, "metadata", str(year))
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(meta_dir, exist_ok=True)

        data_s3 = f"{S3_BUCKET}/data/tar/year={year}/english/"
        meta_s3 = f"{S3_BUCKET}/metadata/parquet/year={year}/"

        print(f"\n--- Processing Year {year} ---")
        cmd_data = ["aws", "s3", "cp", data_s3, data_dir + "/", "--recursive", "--no-sign-request"]
        cmd_meta = ["aws", "s3", "cp", meta_s3, meta_dir + "/", "--recursive", "--no-sign-request"]

        if dry_run:
            cmd_data.append("--dryrun")
            cmd_meta.append("--dryrun")

        print(f"Downloading Data (S3 → {data_dir})...")
        print(f"  Command: {' '.join(cmd_data)}")
        res_data = subprocess.run(cmd_data)
        if res_data.returncode != 0:
            print(f"⚠️ Warning: Data sync for {year} returned non-zero code {res_data.returncode}")

        print(f"Downloading Metadata (S3 → {meta_dir})...")
        print(f"  Command: {' '.join(cmd_meta)}")
        res_meta = subprocess.run(cmd_meta)
        if res_meta.returncode != 0:
            print(f"⚠️ Warning: Metadata sync for {year} returned non-zero code {res_meta.returncode}")

    print("\n✅ Dataset download process completed.")

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "--dryrun" in sys.argv
    download_dataset(dry_run=dry_run)
