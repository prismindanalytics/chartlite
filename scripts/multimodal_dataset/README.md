# Multimodal clinical artifact dataset

Test cases for `scripts/benchmark_multimodal.py`. Eight artifact types,
public-domain or synthetic images only, no PHI.

## Structure

```
multimodal_dataset/
├── README.md          (this file)
├── manifest.json      (case list with ground truth)
└── images/            (the actual JPEGs / PNGs)
```

## Adding a case

1. Drop the image into `images/` with a descriptive name.
2. Append an entry to `manifest.json` of this shape:

```json
{
  "id": "med_amox_001",
  "image_path": "scripts/multimodal_dataset/images/amox_500mg.jpg",
  "expected_content_type": "medication_package",
  "expected_fields": {
    "medications": [
      {"name": "amoxicillin", "dose": "500 mg"}
    ]
  },
  "source": "Wikimedia Commons (public domain)",
  "source_url": "https://commons.wikimedia.org/wiki/...",
  "notes": "Generic amoxicillin capsule pack, clear label, indoor lighting"
}
```

`image_path` is relative to the repo root.

The eight valid `expected_content_type` values:

| Type | Example expected_fields |
|---|---|
| `lab_report` | `{"investigations": [{"test": "Hemoglobin", "result": "9.2", "unit": "g/dL"}]}` |
| `rdt_cassette` | `{"rdt": {"test_type": "malaria", "result": "positive"}}` |
| `vital_device` | `{"vitals": [{"name": "blood pressure", "value": "138/82", "unit": "mmHg"}]}` |
| `medication_package` | `{"medications": [{"name": "amoxicillin", "dose": "500 mg"}]}` |
| `referral_letter` | `{"referral": {"diagnosis": "PUD", "reason": "endoscopy"}}` |
| `vaccine_card` | `{"immunizations": [{"vaccine": "BCG", "dose_number": 1}]}` |
| `handwritten_prescription` | `{"medications": [{"name": "amoxicillin", "dose": "500 mg", "freq": "TID"}]}` |
| `discharge_summary` | `{"discharge": {"dx": ["pneumonia"], "follow_up": "1 week"}}` |

## Sourcing constraints

- **Public-domain or CC-licensed only.** Wikimedia Commons, WHO open
  templates, public pharmacy product photos, synthetic generation.
- **No real patient data.** Names, IDs, faces blurred. Vaccine cards
  must be blank templates or use synthetic data.
- **Real-world conditions.** Mid-tier phone capture, mixed lighting,
  occasional glare or partial framing — that is what the on-device flow
  actually faces.

## Target sample sizes

The methodology aims for ~105 images across the eight types:

| Type | n target | Source |
|---|---|---|
| `medication_package` | 20 | OTC bottles, public pharmacy stock |
| `lab_report` | 15 | WHO open templates, synthetic |
| `vaccine_card` | 15 | WHO Yellow Card open templates |
| `handwritten_prescription` | 15 | Public clinical-pharmacy training images |
| `vital_device` | 10 | Stock photos of BP cuffs, pulse-ox |
| `referral_letter` | 10 | Synthetic |
| `rdt_cassette` | 10 | Open malaria / HIV RDT references |
| `discharge_summary` | 10 | Synthetic |

The current `manifest.json` ships a smaller seed set; it grows as
cases are collected.

## Running the benchmark

```bash
# Smoke test on a few cases with one model
python3 scripts/benchmark_multimodal.py --models gemma4-e4b --limit 5 --concurrency 1

# Full sweep across all vision-capable models
python3 scripts/benchmark_multimodal.py --concurrency 2
```

Outputs:
- `scripts/multimodal_raw/<model>__<case>.json` — per-(model, case) cached run
- `scripts/multimodal_results.json` — aggregate per-model + per-type metrics

The raw cache is the canonical record. Re-runs are idempotent unless
`--force` is passed.
