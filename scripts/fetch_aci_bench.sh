#!/usr/bin/env bash
# Download ACI-Bench (Yim et al., Nature Scientific Data 2023) — the largest
# public dialogue→clinical-note benchmark. CC BY 4.0.
#
#   207 cases (TRAIN 67, VALID 20, TEST1+TEST2+TEST3 = 120)
#   Each case: full doctor-patient dialogue transcript + clinical note + metadata.
#
# Output: scripts/aci_bench/ — the unzipped corpus.
# Re-run safe: skips download if archive already present.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HERE/aci_bench"
ZIP="$DEST/aci-bench-2023.zip"
URL="https://ndownloader.figshare.com/files/41498793"

mkdir -p "$DEST"
if [[ ! -s "$ZIP" ]]; then
  echo "Downloading ACI-Bench (~1.3 MB) from figshare..."
  curl -fsSL "$URL" -o "$ZIP"
else
  echo "Archive already present: $ZIP"
fi
unzip -o -q "$ZIP" -d "$DEST"
echo "Files:"
find "$DEST" -maxdepth 4 -type f \( -name '*.csv' -o -name '*.json' -o -name '*.txt' -o -name '*.md' \) | head -25
echo
echo "Done. Inspect the unpacked files above to set DIALOGUE_FILE/NOTE_FILE in scripts/benchmark_aci.py."
