#!/usr/bin/env bash
# Download CRESCENDDI — Clinically-Relevant Adverse Drug-Drug Interactions
# reference set (Lavertu et al., Nature Scientific Data 2022). License: CC0.
#
# Files (5 Excel sheets, ~3 MB total):
#   Data Record 1 — Positive Controls       (10,286 DDI positives)
#   Data Record 2 — Negative Controls         ( 4,544 DDI negatives)
#   Data Record 3 — Single-drug ADRs           (large, single-drug ADE/indication)
#   Data Record 4 — Drug mappings (RxNorm/OHDSI ingredients)
#   Data Record 5 — Event mappings (MedDRA)
#
# Output: scripts/crescenddi/*.xlsx
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/crescenddi"
mkdir -p "$DEST"

declare -a FILES=(
  "https://ndownloader.figshare.com/files/28584873|Data_Record_1_Positive_Controls.xlsx"
  "https://ndownloader.figshare.com/files/28584876|Data_Record_2_Negative_Controls.xlsx"
  "https://ndownloader.figshare.com/files/28584870|Data_Record_3_Single_drug_ADRs.xlsx"
  "https://ndownloader.figshare.com/files/28584879|Data_Record_4_Drug_mappings.xlsx"
  "https://ndownloader.figshare.com/files/28584882|Data_Record_5_Event_mappings.xlsx"
)

for entry in "${FILES[@]}"; do
  url="${entry%|*}"
  name="${entry#*|}"
  out="$DEST/$name"
  if [[ -s "$out" ]]; then
    echo "✓ $name (cached)"
    continue
  fi
  echo "  ↓ $name"
  curl -fsSL "$url" -o "$out"
done

echo
echo "All 5 files in $DEST:"
ls -la "$DEST"
echo
echo "Quick stats (requires pandas + openpyxl):"
python3 - <<'PY'
try:
    import pandas as pd
except ImportError:
    print("  (pip install pandas openpyxl to inspect)")
    raise SystemExit(0)
import os, glob
for f in sorted(glob.glob("scripts/crescenddi/*.xlsx")):
    try:
        sheets = pd.ExcelFile(f).sheet_names
        rows = sum(pd.read_excel(f, sheet_name=s).shape[0] for s in sheets)
        print(f"  {os.path.basename(f):50s}  sheets={sheets}  rows≈{rows}")
    except Exception as e:
        print(f"  {os.path.basename(f)}: {e}")
PY
