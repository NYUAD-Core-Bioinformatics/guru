#!/usr/bin/env python3
#usage: sample_validation.py [-h] [-t THRESHOLD] input_file
#Default value is 50K

import csv
import argparse

parser = argparse.ArgumentParser()

parser.add_argument("input_file", help="Path to multiqc_general_stats.txt")
parser.add_argument("-t", "--threshold", type=float, default=50000)

args = parser.parse_args()

sample_col = "Sample"
count_col = "FastQC_mqc-generalstats-fastqc-total_sequences"

with open(args.input_file) as f:
    reader = csv.DictReader(f, delimiter="\t")

    print(f"\nThreshold: {args.threshold}\n")

    for row in reader:
        sample = row[sample_col]
        total_seq = float(row[count_col])

        if "R1" in sample or "R2" in sample:

            if total_seq < args.threshold:
                print(f"❌ - {sample}")
            else:
                print(f"✅ - {sample}")
