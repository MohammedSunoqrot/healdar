"""
Healdar evaluation harness.

Measures the things that actually matter for a regulatory assistant, so that
changes to the model, the chunking or the embeddings are measured rather than
guessed at.

    python eval/run_eval.py                 # retrieval only -- fast, no API cost
    python eval/run_eval.py --full          # also generate answers (uses Groq)
    python eval/run_eval.py --json out.json # machine-readable report

Metrics
-------
retrieval
    hit-rate      an expected source document appears in the retrieved set
    refusal       off-topic questions retrieve nothing (the headline safety
                  property: five irrelevant passages become a confident wrong
                  answer, so retrieving nothing is the correct behaviour)
    diversity     cross-jurisdiction questions surface more than one body

generation (--full)
    citation-validity   every [Source N] in the answer maps to a real source
    grounding           each cited passage shares meaningful vocabulary with
                        the sentence citing it
    term-coverage       expected key terms appear in the answer
    refusal             off-topic questions produce no_context

Exit code is non-zero when any metric falls below its threshold, so this can
gate CI.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config
import retrieval
import vectorstore

GOLDEN = Path(__file__).resolve().parent / "golden.jsonl"

# A run is considered a pass when every metric clears its floor.
THRESHOLDS = {
    "retrieval_hit_rate": 0.80,
    "refusal_rate":       1.00,   # refusing off-topic questions is not optional
    "diversity_rate":     0.80,
    "citation_validity":  1.00,   # a dangling citation is always a bug
    "grounding_rate":     0.70,
    "term_coverage":      0.70,
}


@dataclass
class Case:
    id: str
    question: str
    jurisdiction: str = "all"
    expect_docs: list[str] = field(default_factory=list)
    expect_terms: list[str] = field(default_factory=list)
    expect_no_context: bool = False
    min_jurisdictions: int = 0
    # Documented, deliberate failure: kept in the set as a target for the next
    # retrieval improvement rather than quietly deleted to keep the score green.
    known_gap: bool = False
    note: str = ""


def load_cases(path: Path = GOLDEN) -> list[Case]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(Case(**json.loads(line)))
    return cases


# ---------------------------------------------------------------------------
# Retrieval metrics
# ---------------------------------------------------------------------------

def eval_retrieval(cases: list[Case], retriever, jurisdiction_map) -> dict:
    hits, hit_total = 0, 0
    refusals, refusal_total = 0, 0
    diverse, diverse_total = 0, 0
    failures: list[dict] = []

    for case in cases:
        jx_values = jurisdiction_map.get(case.jurisdiction, [])
        result = retriever.search(case.question, jx_values)
        got_docs = [p.filename for p in result.passages]
        got_jx = {p.jurisdiction for p in result.passages}

        if case.expect_no_context:
            refusal_total += 1
            if not result.passages:
                refusals += 1
            else:
                failures.append({
                    "id": case.id, "metric": "refusal",
                    "detail": f"expected no match, got {len(got_docs)} passages "
                              f"(best distance {result.best_distance:.3f}): "
                              f"{got_docs[:3]}",
                })
            continue

        if case.expect_docs:
            hit_total += 1
            if any(any(exp.lower() in d.lower() for d in got_docs)
                   for exp in case.expect_docs):
                hits += 1
            else:
                failures.append({
                    "id": case.id, "metric": "hit_rate",
                    "detail": f"expected one of {case.expect_docs}, got {got_docs}",
                })

        if case.min_jurisdictions:
            diverse_total += 1
            if len(got_jx) >= case.min_jurisdictions:
                diverse += 1
            else:
                failures.append({
                    "id": case.id, "metric": "diversity",
                    "detail": f"expected >={case.min_jurisdictions} jurisdictions, "
                              f"got {sorted(got_jx)}",
                })

    def rate(n, d):
        return round(n / d, 3) if d else 1.0

    return {
        "retrieval_hit_rate": rate(hits, hit_total),
        "refusal_rate":       rate(refusals, refusal_total),
        "diversity_rate":     rate(diverse, diverse_total),
        "counts": {
            "hit": f"{hits}/{hit_total}",
            "refusal": f"{refusals}/{refusal_total}",
            "diversity": f"{diverse}/{diverse_total}",
        },
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Generation metrics
# ---------------------------------------------------------------------------

# Models emit typographic dashes (U+2011 non-breaking hyphen, en/em dashes) and
# smart quotes. Normalising them keeps "post-market" matching "post‑market",
# which otherwise shows up as a content failure that is really an encoding one.
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")
_QUOTES = {ord("‘"): "'", ord("’"): "'",
           ord("“"): '"', ord("”"): '"'}


def normalise(text: str) -> str:
    """Fold typographic punctuation to ASCII and lowercase."""
    return text.translate({**_DASHES, **_QUOTES}).lower()


_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "is",
    "are", "be", "as", "by", "that", "this", "it", "its", "from", "at", "must",
    "shall", "should", "may", "not", "which", "any", "all", "such", "these",
}


def _content_words(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z][a-z0-9\-]{3,}", normalise(text))
        if w not in _STOP
    }


def _sentences_with_citations(answer: str) -> list[tuple[str, set[int]]]:
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        nums = {int(n) for n in config.CITATION_RE.findall(sentence)}
        if nums:
            out.append((config.CITATION_RE.sub("", sentence), nums))
    return out


def eval_generation(cases: list[Case], rag, delay: float = 0.0) -> dict:
    cited_ok, cited_total = 0, 0
    grounded_ok, grounded_total = 0, 0
    terms_ok, terms_total = 0, 0
    refusals, refusal_total = 0, 0
    failures: list[dict] = []
    latencies: list[int] = []

    for case in cases:
        if delay:
            time.sleep(delay)
        t0 = time.perf_counter()
        try:
            answer = rag.ask(case.question, jurisdiction=case.jurisdiction)
        except Exception as exc:
            failures.append({"id": case.id, "metric": "error",
                             "detail": f"{type(exc).__name__}: {exc}"})
            continue
        latencies.append(int((time.perf_counter() - t0) * 1000))

        if case.expect_no_context:
            refusal_total += 1
            if answer.no_context:
                refusals += 1
            else:
                failures.append({
                    "id": case.id, "metric": "refusal",
                    "detail": f"answered an off-topic question: "
                              f"{answer.answer[:120]!r}",
                })
            continue

        if answer.no_context:
            failures.append({"id": case.id, "metric": "no_context",
                             "detail": "expected an answer, got no_context"})
            continue

        # Citation validity: no reference may point past the source list.
        cited_total += 1
        cited = {int(n) for n in config.CITATION_RE.findall(answer.answer)}
        dangling = [n for n in cited if not 1 <= n <= len(answer.sources)]
        if dangling:
            failures.append({
                "id": case.id, "metric": "citation_validity",
                "detail": f"citations {dangling} have no matching source "
                          f"(only {len(answer.sources)} available)",
            })
        else:
            cited_ok += 1

        # Grounding: a cited sentence should share vocabulary with its source.
        for sentence, nums in _sentences_with_citations(answer.answer):
            valid = [n for n in nums if 1 <= n <= len(answer.sources)]
            if not valid:
                continue
            grounded_total += 1
            claim = _content_words(sentence)
            support = set()
            for n in valid:
                support |= _content_words(answer.sources[n - 1].get("text", ""))
            if not claim or len(claim & support) / len(claim) >= 0.25:
                grounded_ok += 1
            else:
                failures.append({
                    "id": case.id, "metric": "grounding",
                    "detail": f"low overlap with cited source: {sentence[:100]!r}",
                })

        # Term coverage: did the answer mention what it should have?
        if case.expect_terms:
            terms_total += 1
            low = normalise(answer.answer)
            missing = [t for t in case.expect_terms if normalise(t) not in low]
            if missing:
                failures.append({"id": case.id, "metric": "term_coverage",
                                 "detail": f"missing terms {missing}"})
            else:
                terms_ok += 1

    def rate(n, d):
        return round(n / d, 3) if d else 1.0

    latencies.sort()
    return {
        "citation_validity": rate(cited_ok, cited_total),
        "grounding_rate":    rate(grounded_ok, grounded_total),
        "term_coverage":     rate(terms_ok, terms_total),
        "refusal_rate":      rate(refusals, refusal_total),
        "latency_ms_median": latencies[len(latencies) // 2] if latencies else None,
        "counts": {
            "citation": f"{cited_ok}/{cited_total}",
            "grounding": f"{grounded_ok}/{grounded_total}",
            "terms": f"{terms_ok}/{terms_total}",
            "refusal": f"{refusals}/{refusal_total}",
        },
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

# Metric name -> the key its "n/total" tally is stored under.
_COUNT_KEY = {
    "retrieval_hit_rate": "hit",
    "refusal_rate":       "refusal",
    "diversity_rate":     "diversity",
    "citation_validity":  "citation",
    "grounding_rate":     "grounding",
    "term_coverage":      "terms",
}


def report(title: str, metrics: dict) -> bool:
    print(f"\n{'=' * 68}\n  {title}\n{'=' * 68}")
    ok = True
    for key, value in metrics.items():
        if key in ("failures", "counts", "latency_ms_median"):
            continue
        if not isinstance(value, (int, float)):
            continue
        floor = THRESHOLDS.get(key)
        counts = metrics.get("counts", {}).get(_COUNT_KEY.get(key, ""), "")
        if floor is None:
            print(f"  {key:22} {value}")
            continue
        passed = value >= floor
        ok &= passed
        mark = "PASS" if passed else "FAIL"
        print(f"  {key:22} {value:>6.1%}  (floor {floor:.0%})  {mark}  {counts}")

    if metrics.get("latency_ms_median") is not None:
        print(f"  {'latency_ms_median':22} {metrics['latency_ms_median']}")

    failures = metrics.get("failures", [])
    if failures:
        print(f"\n  {len(failures)} failure(s):")
        for f in failures[:25]:
            print(f"    [{f['metric']}] {f['id']}: {f['detail']}")
        if len(failures) > 25:
            print(f"    ... and {len(failures) - 25} more")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Healdar.")
    parser.add_argument("--full", action="store_true",
                        help="also generate answers (requires GROQ_API_KEY)")
    parser.add_argument("--json", type=Path, help="write a JSON report here")
    parser.add_argument("--golden", type=Path, default=GOLDEN)
    parser.add_argument("--delay", type=float, default=1.0,
                        help="seconds to wait between generated answers")
    args = parser.parse_args()

    cases = load_cases(args.golden)
    print(f"Loaded {len(cases)} cases from {args.golden.name}")
    print(f"Config: top_k={config.TOP_K} max_distance={config.MAX_DISTANCE} "
          f"hybrid={config.HYBRID_SEARCH} answer_model={config.GROQ_MODEL_ANSWER}")

    from rag_pipeline import JURISDICTION_MAP

    collection = vectorstore.load_collection()
    retriever = retrieval.Retriever(collection)

    results = {"retrieval": eval_retrieval(cases, retriever, JURISDICTION_MAP)}
    ok = report("RETRIEVAL", results["retrieval"])

    if args.full:
        from rag_pipeline import HealdarRAG

        rag = HealdarRAG()
        results["generation"] = eval_generation(cases, rag, delay=args.delay)
        ok &= report("GENERATION", results["generation"])

    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nJSON report written to {args.json}")

    print(f"\n{'OVERALL: PASS' if ok else 'OVERALL: FAIL'}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
