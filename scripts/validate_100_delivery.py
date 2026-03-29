"""Validate 100% delivery rate across all difficulty levels.

Run: python scripts/validate_100_delivery.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

# Ensure project root is on path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import get_settings
from src.config.constants import OVERSHOOT_BY_DIFFICULTY, REVIEW_THRESHOLD_BY_DIFFICULTY
from src.api.schemas import (
    GenerationRequest, GameType, DifficultyLevel, DocScope,
)
from src.graph.builder import compile_graph
from src.graph.state import MAX_REVIEW_ITERATIONS


def make_request(
    topic: str,
    num_questions: int = 10,
    difficulty: str = "comprehension",
) -> GenerationRequest:
    return GenerationRequest(
        user_id="validate_100",
        topic=topic,
        game_types=[GameType.QUIZ],
        num_questions=num_questions,
        difficulty=DifficultyLevel(difficulty),
        doc_scope=DocScope.SYSTEM,
    )


async def run_pipeline(request: GenerationRequest) -> dict:
    app = compile_graph()
    initial_state = {
        "request": request,
        "doc_scope": request.doc_scope.value,
        "iteration_count": 0,
        "rejected_items": [],
        "reviewed_items": [],
        "errors": [],
    }
    t0 = time.time()
    result = await app.ainvoke(initial_state)
    elapsed = time.time() - t0
    return {**result, "_elapsed": elapsed}


async def main():
    settings = get_settings()
    print("=" * 70)
    print("PIPELINE 100% DELIVERY VALIDATION")
    print("=" * 70)
    print(f"Gen model:  {settings.generation_model} @ {settings.generation_model_location or settings.gcp_location}")
    print(f"Rev model:  {settings.review_model} @ {settings.review_model_location}")
    print(f"Max iters:  {MAX_REVIEW_ITERATIONS}")
    print(f"Overshoot:  {OVERSHOOT_BY_DIFFICULTY}")
    print(f"Thresholds: {REVIEW_THRESHOLD_BY_DIFFICULTY}")
    print()

    TOPIC = "Phản ứng oxi hóa khử"
    NUM_Q = 10
    DIFFS = ["recall", "comprehension", "application", "high_application"]

    results = {}
    for diff in DIFFS:
        print(f"\n{'='*60}")
        print(f"Testing: {diff} | topic={TOPIC} | num_q={NUM_Q}")
        print(f"  overshoot={OVERSHOOT_BY_DIFFICULTY[diff]}x, threshold={REVIEW_THRESHOLD_BY_DIFFICULTY[diff]}")
        print(f"{'='*60}")

        req = make_request(TOPIC, num_questions=NUM_Q, difficulty=diff)
        res = await run_pipeline(req)

        out = res.get("final_output")
        errors = res.get("errors", [])
        elapsed = res.get("_elapsed", 0)
        iterations = res.get("iteration_count", 0)
        reviewed = res.get("reviewed_items", [])
        rejected = res.get("rejected_items", [])

        if not out:
            print(f"  ❌ No output! Errors: {errors}")
            results[diff] = {"delivery": 0, "quiz": 0, "elapsed": elapsed}
            continue

        m = out.metadata
        quiz_count = len(out.content.quiz)
        delivery_pct = quiz_count / NUM_Q * 100
        pass_rate = m.total_passed_review / m.total_generated * 100 if m.total_generated > 0 else 0

        results[diff] = {
            "delivery": delivery_pct,
            "quiz": quiz_count,
            "generated": m.total_generated,
            "passed": m.total_passed_review,
            "rejected": m.total_rejected,
            "iterations": iterations,
            "elapsed": elapsed,
            "pass_rate": pass_rate,
        }

        status = "✅" if quiz_count >= NUM_Q else "❌"
        print(f"  {status} delivery={quiz_count}/{NUM_Q} ({delivery_pct:.0f}%)")
        print(f"  generated={m.total_generated}, passed={m.total_passed_review}, rejected={m.total_rejected}")
        print(f"  pass_rate={pass_rate:.1f}%, iterations={iterations}, time={elapsed:.1f}s")

        if errors:
            print(f"  ⚠️ errors: {errors}")

        # Sample question
        if out.content.quiz:
            q = out.content.quiz[0]
            print(f"  Sample: {q.question[:150]}")

    # Final summary
    print(f"\n{'='*70}")
    print("FINAL SUMMARY")
    print(f"{'='*70}")
    print(f"{'Difficulty':<20} {'Delivery':>10} {'PassRate':>10} {'Gen':>5} {'Pass':>5} {'Rej':>5} {'Iter':>5} {'Time':>8}")
    print("-" * 70)

    all_100 = True
    for diff in DIFFS:
        r = results[diff]
        dlv = f"{r['quiz']}/{NUM_Q}"
        pr = f"{r.get('pass_rate', 0):.1f}%"
        gen = r.get("generated", "-")
        pas = r.get("passed", "-")
        rej = r.get("rejected", "-")
        it = r.get("iterations", "-")
        t = f"{r['elapsed']:.1f}s"
        mark = "✅" if r["delivery"] >= 100 else "❌"
        print(f"{diff:<20} {dlv:>10} {pr:>10} {gen:>5} {pas:>5} {rej:>5} {it:>5} {t:>8} {mark}")
        if r["delivery"] < 100:
            all_100 = False

    total_time = sum(r["elapsed"] for r in results.values())
    print(f"\nTotal time: {total_time:.0f}s ({total_time/60:.1f}min)")

    if all_100:
        print("\n🎉 ALL DIFFICULTY LEVELS ACHIEVED 100% DELIVERY!")
    else:
        failed = [d for d in DIFFS if results[d]["delivery"] < 100]
        print(f"\n❌ FAILED: {', '.join(failed)}")

    return all_100


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
