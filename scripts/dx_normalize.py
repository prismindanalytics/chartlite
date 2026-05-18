#!/usr/bin/env python3
"""
Post-hoc diagnosis normalization experiment.

For every raw_generations/<model>__<mode>__enc<NNN>.json, take the LLM's
extracted `diagnoses` list, apply one of three normalization strategies to
map each string to a canonical BODHI condition name (or keep unchanged if
confident), rewrite the extraction, and re-run the CDSS evaluation to
measure how Arm 2 + Arm 3 change.

Strategies:
  fuzzy     — RapidFuzz / difflib match against BODHI condition names + ICD-10
              description index. Cheap but blind to semantic similarity.
  embedding — Ollama `nomic-embed-text` cosine similarity between the
              extracted string and pre-embedded BODHI condition names.
  llm       — An on-device LLM (qwen3.5:0.8b by default) re-reads the
              transcript + the extracted diagnoses list + a pre-filtered
              shortlist of BODHI candidates, and picks the best match.

Each strategy writes scored results to:
  scripts/bodhi_normalized/<strategy>__<model>__<mode>__enc<NNN>.json

Usage:
  python3 scripts/dx_normalize.py --strategy fuzzy --model qwen3.5:0.8b
  python3 scripts/dx_normalize.py --strategy embedding --model qwen3.5:0.8b
  python3 scripts/dx_normalize.py --strategy llm --model qwen3.5:0.8b
  python3 scripts/dx_normalize.py --strategy all
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
import math
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
RAW_DIR = REPO / "scripts" / "bodhi_raw_generations"
NORM_DIR = REPO / "scripts" / "bodhi_normalized"
BODHI_DIR = REPO / "app" / "src" / "main" / "assets" / "bodhi"
ICD10_PATH = REPO / "app" / "src" / "main" / "assets" / "icd10" / "phc_top300.json"

OLLAMA_URL = "http://localhost:11434"
sys.path.insert(0, str(REPO / "scripts"))
import benchmark_bodhi as bb  # CDSS, ClinicalData, etc.


# ═══════════════════════════════════════════════════════════════════════════
# Shared data loading
# ═══════════════════════════════════════════════════════════════════════════

def load_bodhi_conditions() -> list[dict]:
    with open(BODHI_DIR / "bodhi_conditions.json") as f:
        conds = json.load(f)
    # Filter to just clinical conditions that could be extracted as dx
    return [c for c in conds if c.get("conceptType") != "FamilyHistory"]


def load_icd10_index() -> list[str]:
    """Return ICD-10 code descriptions as a flat string list."""
    with open(ICD10_PATH) as f:
        data = json.load(f)
    names = []
    # Structure is nested dict — walk it
    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str): names.append(v)
                else: walk(v)
        elif isinstance(o, list):
            for x in o: walk(x)
    walk(data)
    return [n for n in names if len(n) > 3 and not n.replace(".", "").isdigit()]


# ═══════════════════════════════════════════════════════════════════════════
# Strategy 1 — FUZZY
# ═══════════════════════════════════════════════════════════════════════════

class FuzzyNormalizer:
    def __init__(self):
        self.conds = load_bodhi_conditions()
        self.cond_names = [c["name"] for c in self.conds]
        self.icd10 = load_icd10_index()
        self.all_terms = list(set(self.cond_names + self.icd10))
        print(f"  [fuzzy] BODHI conds: {len(self.cond_names)}, ICD-10: {len(self.icd10)}, combined: {len(self.all_terms)}")

    def normalize(self, dx_str: str, transcript: str = "") -> tuple[str, float]:
        """Return (best BODHI condition name, score). 0 = no match."""
        q = dx_str.lower().strip()
        if not q:
            return dx_str, 0.0

        # 1. Exact or substring match in BODHI condition names (highest priority)
        for name in self.cond_names:
            nl = name.lower()
            if q == nl:
                return name, 1.0
            if q in nl or nl in q:
                return name, 0.9

        # 2. Substring match in ICD-10 descriptions
        for descr in self.icd10:
            dl = descr.lower()
            if q == dl or q in dl or dl in q:
                # ICD-10 match — try to map back to BODHI
                best_b = self._best_bodhi_for(descr)
                if best_b:
                    return best_b, 0.7
                return descr, 0.6

        # 3. Fuzzy ratio against BODHI names
        best = None; best_score = 0
        for name in self.cond_names:
            r = difflib.SequenceMatcher(None, q, name.lower()).ratio()
            if r > best_score:
                best_score = r; best = name

        if best_score < 0.55:
            return dx_str, 0.0   # keep original
        return best, best_score

    def _best_bodhi_for(self, icd10_desc: str) -> str | None:
        ql = icd10_desc.lower()
        for name in self.cond_names:
            if name.lower() in ql or ql in name.lower():
                return name
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Strategy 2 — EMBEDDING (nomic-embed-text via Ollama)
# ═══════════════════════════════════════════════════════════════════════════

class EmbeddingNormalizer:
    EMBED_MODEL = "nomic-embed-text"

    def __init__(self):
        import requests
        self.requests = requests
        self.conds = load_bodhi_conditions()
        self.cond_names = [c["name"] for c in self.conds]
        print(f"  [embedding] Pre-embedding {len(self.cond_names)} BODHI condition names…")
        self.cond_vecs = [self._embed(n) for n in self.cond_names]
        print(f"  [embedding] Done; vector dim {len(self.cond_vecs[0]) if self.cond_vecs else 0}")

    def _embed(self, text: str) -> list[float]:
        r = self.requests.post(f"{OLLAMA_URL}/api/embeddings", json={
            "model": self.EMBED_MODEL,
            "prompt": text,
        }, timeout=30)
        r.raise_for_status()
        return r.json()["embedding"]

    @staticmethod
    def _cos(a, b):
        if not a or not b: return 0.0
        na = math.sqrt(sum(x*x for x in a))
        nb = math.sqrt(sum(x*x for x in b))
        if na == 0 or nb == 0: return 0.0
        return sum(x*y for x, y in zip(a, b)) / (na * nb)

    def normalize(self, dx_str: str, transcript: str = "") -> tuple[str, float]:
        if not dx_str.strip(): return dx_str, 0.0
        try:
            qv = self._embed(dx_str)
        except Exception:
            return dx_str, 0.0
        best_i = 0; best_s = -1
        for i, v in enumerate(self.cond_vecs):
            s = self._cos(qv, v)
            if s > best_s: best_s = s; best_i = i
        if best_s < 0.55:
            return dx_str, best_s
        return self.cond_names[best_i], best_s


# ═══════════════════════════════════════════════════════════════════════════
# Strategy 3 — LLM MENU-PICK  (Qwen 0.8B re-reads findings and picks from BODHI list)
# ═══════════════════════════════════════════════════════════════════════════

class LLMMenuNormalizer:
    def __init__(self, helper_model: str = "qwen3.5:0.8b"):
        import requests
        self.requests = requests
        self.helper_model = helper_model
        self.conds = load_bodhi_conditions()
        self.cond_names = [c["name"] for c in self.conds]
        # Pre-bucket condition names by first letter for fast shortlisting (optional)
        print(f"  [llm-menu] helper model: {helper_model}, BODHI candidates: {len(self.cond_names)}")

    def _shortlist(self, transcript: str, n: int = 80) -> list[str]:
        """Fast keyword-based shortlisting — avoid sending 779 conditions to the LLM."""
        t = transcript.lower()
        scored = []
        for name in self.cond_names:
            nl = name.lower()
            # If any 4+ letter token from the name appears in transcript, include
            words = [w for w in re.split(r"\W+", nl) if len(w) >= 4]
            score = sum(1 for w in words if w in t)
            scored.append((score, name))
        scored.sort(key=lambda x: -x[0])
        # Always include all cond names with score > 0; pad to n
        picks = [s[1] for s in scored if s[0] > 0][:n]
        if len(picks) < n:
            picks.extend(s[1] for s in scored[len(picks):n])
        return picks

    def normalize(self, dx_str: str, transcript: str = "") -> tuple[str, float]:
        if not dx_str.strip() and not transcript.strip():
            return dx_str, 0.0
        shortlist = self._shortlist(transcript, n=80)
        menu = "\n".join(f"- {n}" for n in shortlist)
        prompt = f"""Given the clinical transcript below and the extracted-diagnosis candidate, identify the single best-matching standard diagnosis from the menu. Pick "none" if no menu item applies. Output JSON ONLY.

TRANSCRIPT (may describe findings without naming the diagnosis):
{transcript[:2000]}

EXTRACTED DIAGNOSIS CANDIDATE: "{dx_str}"

MENU (choose one, or "none"):
{menu}

Output format: {{"diagnosis": "exact menu item or none", "confidence": 0-1}}
"""
        try:
            r = self.requests.post(f"{OLLAMA_URL}/api/chat", json={
                "model": self.helper_model, "stream": False,
                "options": {"temperature": 0.1, "num_predict": 200},
                "messages": [
                    {"role": "system", "content": "You match clinical findings to standard diagnoses. Output JSON only."},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "<think>\n</think>\n"},
                ],
            }, timeout=60)
            r.raise_for_status()
            txt = r.json().get("message", {}).get("content", "")
            m = re.search(r"\{[\s\S]*\}", txt)
            if not m: return dx_str, 0.0
            parsed = json.loads(m.group())
            pick = parsed.get("diagnosis", "").strip()
            conf = float(parsed.get("confidence", 0) or 0)
            if pick.lower() in ("none", "", "null"): return dx_str, 0.0
            # Validate it's in our menu
            for c in self.cond_names:
                if c.lower() == pick.lower():
                    return c, conf
            # Allow partial match
            for c in shortlist:
                if pick.lower() in c.lower() or c.lower() in pick.lower():
                    return c, conf * 0.9
            return dx_str, 0.0
        except Exception as e:
            return dx_str, 0.0


# ═══════════════════════════════════════════════════════════════════════════
# Strategy 4 — BODHI-S symptom-graph inference (uses the 10,352 symptom→condition links)
# ═══════════════════════════════════════════════════════════════════════════

class BodhiSNormalizer:
    """Parse BODHI-S structured symptom tokens, match against transcript,
    rank candidate conditions by aggregated likelihood × strongPredictor weight."""

    def __init__(self):
        with open(os.path.join(BODHI_DIR, "bodhi_symptoms.json")) as f:
            self.syms = json.load(f)
        with open(os.path.join(BODHI_DIR, "bodhi_conditions.json")) as f:
            conds = json.load(f)
        self.cond_name = {c["snomedId"]: c["name"] for c in conds}
        # Filter out FamilyHistory (we don't want 'H/O Pneumonia' type outputs)
        self.valid_snomeds = {c["snomedId"] for c in conds if c.get("conceptType") != "FamilyHistory"}

        # Pre-parse every symptom pattern into (base, [(token, value), ...])
        self.patterns = []  # list of (snomed, base, mods, likelihood, strong)
        for snomed, sym_list in self.syms.items():
            if snomed not in self.valid_snomeds: continue
            for s in sym_list:
                text = (s.get("name") or "").lower()
                if not text: continue
                base, mods = self._parse(text)
                if base:
                    self.patterns.append((snomed, base, mods,
                                          s.get("likelihood", 0.5),
                                          s.get("strongPredictor", False)))
        print(f"  [bodhi-s] parsed {len(self.patterns)} symptom patterns across "
              f"{len(set(p[0] for p in self.patterns))} conditions")

    @staticmethod
    def _parse(text: str):
        """Split 'abdominal pain <loc> upper abdomen <char> epigastric' into
        base='abdominal pain' and mods=[('loc','upper abdomen'), ('char','epigastric')]."""
        parts = re.split(r"<(\w+)>", text)
        base = parts[0].strip()
        mods = []
        for i in range(1, len(parts) - 1, 2):
            tok = parts[i].strip()
            val = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if val:
                mods.append((tok, val))
        return base, mods

    @staticmethod
    def _phrase_hit(phrase: str, transcript: str) -> float:
        """Return confidence that a BODHI phrase is present in transcript.
        Exact substring = 1.0; all words individually present = 0.7; partial = fraction."""
        if not phrase: return 0.0
        if phrase in transcript: return 1.0
        words = [w for w in re.split(r"\W+", phrase) if len(w) >= 3]
        if not words: return 0.0
        hits = sum(1 for w in words if w in transcript)
        if hits == len(words): return 0.7
        if hits >= max(1, len(words) // 2): return 0.4
        return 0.0

    def _score_pattern(self, base, mods, transcript):
        """Return 0-1 match score for one BODHI-S pattern vs transcript."""
        base_hit = self._phrase_hit(base, transcript)
        if base_hit == 0: return 0.0
        if not mods: return 0.5 * base_hit   # base-only match — moderate
        mod_hits = [self._phrase_hit(val, transcript) for tok, val in mods]
        # Require at least one modifier present for high confidence
        max_mod = max(mod_hits) if mod_hits else 0
        avg_mod = sum(mod_hits) / len(mod_hits) if mod_hits else 0
        return base_hit * (0.5 + 0.5 * max_mod) * (0.7 + 0.3 * avg_mod)

    def normalize(self, dx_str: str, transcript: str = "") -> tuple[str, float]:
        t = transcript.lower()
        if not t: return dx_str, 0.0

        # Accumulate scores per condition
        from collections import defaultdict
        votes = defaultdict(float)
        strong_counts = defaultdict(int)
        hit_examples = defaultdict(list)

        for snomed, base, mods, lik, strong in self.patterns:
            match = self._score_pattern(base, mods, t)
            if match == 0: continue
            weight = match * lik * (1.8 if strong else 1.0)
            votes[snomed] += weight
            if strong and match >= 0.5: strong_counts[snomed] += 1
            if match >= 0.6: hit_examples[snomed].append((base, round(match, 2)))

        if not votes: return dx_str, 0.0

        # Penalize too-generic matches (base only, weak likelihoods): require total score > threshold
        ranked = sorted(votes.items(), key=lambda x: -x[1])
        top_snomed, top_score = ranked[0]

        # Confidence heuristic:
        # - strong prediction threshold: ≥1 strongPredictor match AND score ≥ 1.5
        # - moderate threshold: score ≥ 2.5 (multiple evidence points)
        if strong_counts[top_snomed] >= 1 and top_score >= 1.0:
            conf = min(0.95, 0.5 + top_score / 10)
        elif top_score >= 2.5:
            conf = min(0.8, 0.4 + top_score / 15)
        else:
            return dx_str, top_score / 10   # below threshold, keep original

        # Make sure it's a real disease (filter out misc/lifestyle junk if needed)
        name = self.cond_name.get(top_snomed)
        if not name: return dx_str, 0.0
        return name, conf


# ═══════════════════════════════════════════════════════════════════════════
# Strategy 5 — HYBRID  (BODHI-S generates candidates, LLM picks final)
# ═══════════════════════════════════════════════════════════════════════════

class HybridBodhiSLLMNormalizer:
    """BODHI-S generates a ranked shortlist of candidate conditions based on
    symptom→condition graph signal. Then the LLM picks the final match."""

    def __init__(self, helper_model: str = "qwen3.5:0.8b"):
        import requests
        self.requests = requests
        self.helper_model = helper_model
        self.bodhi_s = BodhiSNormalizer()
        print(f"  [hybrid] BODHI-S + LLM ({helper_model})")

    def _bodhi_candidates(self, transcript: str, topk: int = 10) -> list[tuple[str, float, int]]:
        """Return top-K BODHI-S candidate conditions with scores + strongPredictor counts."""
        from collections import defaultdict
        t = transcript.lower()
        votes = defaultdict(float)
        strong = defaultdict(int)
        for snomed, base, mods, lik, is_strong in self.bodhi_s.patterns:
            match = self.bodhi_s._score_pattern(base, mods, t)
            if match == 0: continue
            w = match * lik * (1.8 if is_strong else 1.0)
            votes[snomed] += w
            if is_strong and match >= 0.5: strong[snomed] += 1
        ranked = sorted(votes.items(), key=lambda x: -x[1])[:topk]
        out = []
        for snomed, score in ranked:
            name = self.bodhi_s.cond_name.get(snomed)
            if name: out.append((name, score, strong[snomed]))
        return out

    def normalize(self, dx_str: str, transcript: str = "") -> tuple[str, float]:
        if not transcript.strip():
            return dx_str, 0.0

        # Get BODHI-S candidates
        candidates = self._bodhi_candidates(transcript, topk=10)
        if not candidates:
            return dx_str, 0.0

        # If BODHI-S gives a very high-confidence single answer, use it
        top_name, top_score, top_strong = candidates[0]
        if top_strong >= 2 and top_score >= 2.0:
            return top_name, 0.9

        # Otherwise, let LLM pick from BODHI-S shortlist
        menu = "\n".join(f"- {n}  (BODHI-S score {s:.1f}, strongPred={sp})" for n, s, sp in candidates)
        prompt = f"""BODHI's symptom graph suggests these candidate diagnoses based on findings in the transcript. Pick the single best-matching diagnosis, or "none" if none fit.

TRANSCRIPT:
{transcript[:1800]}

EXTRACTED DIAGNOSIS CANDIDATE: "{dx_str}"

BODHI-S CANDIDATES (ranked by symptom-graph evidence):
{menu}

Output JSON: {{"diagnosis": "exact candidate name or none", "confidence": 0-1}}
"""
        try:
            r = self.requests.post(f"{OLLAMA_URL}/api/chat", json={
                "model": self.helper_model, "stream": False,
                "options": {"temperature": 0.1, "num_predict": 200},
                "messages": [
                    {"role": "system", "content": "You match findings to the most likely diagnosis from a candidate list grounded in a clinical knowledge graph. Output JSON only."},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "<think>\n</think>\n"},
                ],
            }, timeout=60)
            r.raise_for_status()
            txt = r.json().get("message", {}).get("content", "")
            m = re.search(r"\{[\s\S]*\}", txt)
            if not m: return top_name, 0.5   # fallback: top BODHI-S candidate
            parsed = json.loads(m.group())
            pick = parsed.get("diagnosis", "").strip()
            conf = float(parsed.get("confidence", 0) or 0)
            if pick.lower() in ("none", "", "null"):
                # LLM rejected all BODHI-S candidates — keep original
                return dx_str, 0.0
            # Validate pick is in our candidate list
            for name, s, sp in candidates:
                if name.lower() == pick.lower():
                    return name, conf
            # Partial match
            for name, s, sp in candidates:
                if pick.lower() in name.lower() or name.lower() in pick.lower():
                    return name, conf * 0.9
            # Fallback to top BODHI-S candidate
            return top_name, 0.5
        except Exception:
            return top_name, 0.5


# ═══════════════════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════════════════

def normalize_file(path: Path, normalizer, strategy_name: str, cdss,
                   bodhi_cond_names_lower: set | None = None) -> dict:
    """For BODHI-S and embedding strategies, we guard against clobbering good
    extractions: if the original dx is already close to a BODHI condition name
    (fuzzy >= 0.85), keep it. Otherwise, try to normalize or append."""
    data = json.loads(path.read_text())
    extracted = (data.get("extraction", {}).get("parsed") or {})
    orig_dx = list(extracted.get("diagnoses") or [])
    transcript = data.get("transcript", "")

    if bodhi_cond_names_lower is None:
        bodhi_cond_names_lower = {c["name"].lower() for c in load_bodhi_conditions()}

    def already_bodhi_ok(dx: str) -> bool:
        """Does this dx already match (or come very close to) a BODHI condition?"""
        dxl = dx.lower().strip()
        if not dxl: return False
        if dxl in bodhi_cond_names_lower: return True
        # Token overlap — dx already contains a full BODHI name substring or vice versa
        for name in bodhi_cond_names_lower:
            if name in dxl or (len(dxl) > 4 and dxl in name):
                return True
        # Difflib close match
        import difflib
        best = max((difflib.SequenceMatcher(None, dxl, n).ratio() for n in bodhi_cond_names_lower), default=0)
        return best >= 0.85

    new_dx = []
    norm_log = []
    for dx in orig_dx:
        dx_str = str(dx)
        # GUARDRAIL: if dx already looks like a valid BODHI term, keep it
        if already_bodhi_ok(dx_str):
            new_dx.append(dx_str)
            continue
        best, score = normalizer.normalize(dx_str, transcript=transcript)
        if score >= 0.5 and best != dx_str:
            new_dx.append(best)
            norm_log.append({"from": dx_str, "to": best, "score": round(score, 3)})
        else:
            new_dx.append(dx_str)

    # If NO good dx after normalization, try pure-transcript inference
    if not any(already_bodhi_ok(d) for d in new_dx):
        best, score = normalizer.normalize("", transcript=transcript)
        if score >= 0.5:
            new_dx.append(best)
            norm_log.append({"from": "(empty)", "to": best, "score": round(score, 3)})

    # Rebuild extraction dict with new diagnoses
    new_ext = dict(extracted)
    new_ext["diagnoses"] = new_dx

    # Re-run CDSS
    allergies = data.get("ground_truth", {}).get("patient_allergies", []) or []
    vanilla_alerts, bodhi_alerts = cdss.evaluate(new_ext, allergies)
    arm3_alerts = vanilla_alerts + bodhi_alerts

    # Score arms
    expected = data.get("ground_truth", {}).get("expected_dangers", [])
    review_alerts = [bb.Alert(a["severity"], a["category"], a["message"])
                     for a in (data.get("clinical_review_arm1", {}) or {}).get("parsed_alerts", []) or []]
    a1 = bb.count_caught(review_alerts, expected)
    a2 = bb.count_caught(vanilla_alerts, expected)
    a3 = bb.count_caught(arm3_alerts, expected)
    total = len(expected)

    return {
        "strategy": strategy_name,
        "encounter_id": data["encounter_id"],
        "encounter_name": data["encounter_name"],
        "orig_dx": orig_dx,
        "new_dx": new_dx,
        "normalizations": norm_log,
        "orig_arm_caught": data.get("arm_caught", {}),
        "new_arm_caught": {"arm1": a1, "arm2": a2, "arm3": a3, "total": total},
        "new_vanilla_alerts": [{"severity": a.severity, "category": a.category, "message": a.message} for a in vanilla_alerts],
        "new_bodhi_alerts": [{"severity": a.severity, "category": a.category, "message": a.message} for a in bodhi_alerts],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strategy", choices=["fuzzy", "embedding", "llm", "bodhi-s", "hybrid", "all"], default="all")
    p.add_argument("--model", default="qwen3.5:0.8b", help="Target model to normalize")
    p.add_argument("--mode", default="conversation")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--helper-model", default="qwen3.5:0.8b", help="Helper LLM for menu-pick strategy")
    args = p.parse_args()

    strategies_to_run = ["fuzzy", "embedding", "llm", "bodhi-s", "hybrid"] if args.strategy == "all" else [args.strategy]
    NORM_DIR.mkdir(parents=True, exist_ok=True)

    # Load CDSS once
    clindat = bb.ClinicalData()
    cdss = bb.CDSS(clindat)

    # Find target files
    target_slug = args.model.replace(":", "-").replace("/", "-")
    files = sorted(RAW_DIR.glob(f"{target_slug}__{args.mode}__enc*.json"))
    if args.limit: files = files[:args.limit]
    print(f"Target files: {len(files)} for {args.model} {args.mode}")
    print()

    for strategy in strategies_to_run:
        print(f"═══ Strategy: {strategy} ═══")
        t0 = time.time()
        if strategy == "fuzzy":
            norm = FuzzyNormalizer()
        elif strategy == "embedding":
            norm = EmbeddingNormalizer()
        elif strategy == "llm":
            norm = LLMMenuNormalizer(helper_model=args.helper_model)
        elif strategy == "bodhi-s":
            norm = BodhiSNormalizer()
        elif strategy == "hybrid":
            norm = HybridBodhiSLLMNormalizer(helper_model=args.helper_model)

        total_a3_orig = 0
        total_a3_new = 0
        total_dangers = 0
        changes = 0
        for i, f in enumerate(files):
            res = normalize_file(f, norm, strategy, cdss)
            # Save
            out = NORM_DIR / f"{strategy}__{f.name}"
            out.write_text(json.dumps(res, indent=2))
            total_a3_orig += res["orig_arm_caught"].get("arm3", 0)
            total_a3_new += res["new_arm_caught"]["arm3"]
            total_dangers += res["new_arm_caught"]["total"]
            if res["normalizations"]: changes += 1

            if (i+1) % 10 == 0 or i == len(files)-1:
                pct = 100*(i+1)/len(files)
                print(f"  [{i+1:3d}/{len(files)}]  orig A3={total_a3_orig}/{total_dangers}  new A3={total_a3_new}/{total_dangers}  Δ=+{total_a3_new-total_a3_orig}  changes={changes}")
        elapsed = time.time() - t0
        print(f"  Done in {elapsed:.0f}s — total Arm 3 lift: +{total_a3_new - total_a3_orig}")
        print()


if __name__ == "__main__":
    main()
