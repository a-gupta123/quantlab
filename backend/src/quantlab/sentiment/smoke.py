"""Real-model smoke test: downloads (if needed) and runs FinBERT once.

    uv run --extra ml python -m quantlab.sentiment.smoke

Not part of normal CI because it downloads ~440 MB of weights.
"""

import json
import time

from quantlab.sentiment.model import get_classifier, model_status
from quantlab.sentiment.samples import SAMPLE_HEADLINES


def main() -> None:
    t0 = time.perf_counter()
    clf = get_classifier()
    load_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    results = clf.classify(SAMPLE_HEADLINES)
    infer_s = time.perf_counter() - t1
    for text, scores in zip(SAMPLE_HEADLINES, results, strict=True):
        label = max(scores, key=scores.get)
        print(f"{label:8s} {json.dumps({k: round(v, 3) for k, v in scores.items()})}  {text}")
    print(f"model={clf.model_name} revision={clf.revision} status={model_status()}")
    print(f"load {load_s:.1f}s, inference {infer_s:.2f}s for {len(results)} headlines")
    assert all(abs(sum(s.values()) - 1) < 1e-3 for s in results), "scores must sum to 1"


if __name__ == "__main__":
    main()
