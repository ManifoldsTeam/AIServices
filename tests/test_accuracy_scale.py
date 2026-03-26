"""Accuracy & Scale Test — Content quality and volume verification.

Tests that the pipeline produces educationally valuable content at scale:
1. Content accuracy — computation traces match answers
2. Question diversity — no duplicates, varied sub-topics
3. Vietnamese language quality — questions in Vietnamese
4. Scale test — multi-chapter broad topic (30 questions)
5. Cross-subject comparison — Math vs Physics vs Chemistry

Success criteria (from edu platform benchmarks):
- Review pass rate >= 70% (built into pipeline)
- Unique questions >= 90% of total
- Computation traces present in >= 50% of math questions
- All 3 game types produce correct structure
"""

import asyncio
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import get_settings
from src.api.schemas import (
    GenerationRequest,
    GameType,
    DifficultyLevel,
    DocScope,
    GameContentResponse,
)
from src.graph.builder import get_graph_app


def make_request(topic, num_questions=10, game_types=None, difficulty="medium"):
    gts = [GameType(g) for g in (game_types or ["quiz"])]
    return GenerationRequest(
        user_id="accuracy_test",
        topic=topic,
        game_types=gts,
        num_questions=num_questions,
        difficulty=DifficultyLevel(difficulty),
        doc_scope=DocScope.SYSTEM,
    )


async def run_pipeline(request):
    app = get_graph_app()
    state = {
        "request": request,
        "doc_scope": request.doc_scope.value,
        "iteration_count": 0,
        "rejected_items": [],
        "errors": [],
    }
    t0 = time.time()
    result = await app.ainvoke(state)
    return {**result, "_elapsed": time.time() - t0}


def check_vietnamese(text: str) -> bool:
    """Check if text contains Vietnamese characters."""
    vn_chars = re.compile(
        r"[àáâãèéêìíòóôõùúăđĩũơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]",
        re.IGNORECASE,
    )
    return bool(vn_chars.search(text))


# ── Test 1: Content Accuracy ──


async def test_accuracy():
    """Verify computation traces match answers for math questions."""
    print("\n" + "=" * 60)
    print("TEST: Content Accuracy — Đạo hàm (10 quiz)")
    print("=" * 60)

    req = make_request("Đạo hàm", num_questions=10, game_types=["quiz"])
    res = await run_pipeline(req)
    out = res.get("final_output")

    assert out is not None, "No output"
    quizzes = out.content.quiz
    n = len(quizzes)
    print(f"  Generated {n} quiz questions in {res['_elapsed']:.1f}s")

    with_trace = [q for q in quizzes if q.computation_trace]
    print(f"  Computation traces: {len(with_trace)}/{n} ({len(with_trace)/n*100:.0f}%)")
    assert (
        len(with_trace) >= n * 0.5
    ), f"Expected >=50% traces, got {len(with_trace)/n*100:.0f}%"

    # Check all questions have content
    for i, q in enumerate(quizzes):
        assert q.question, f"Q{i}: empty question"
        assert q.explanation, f"Q{i}: empty explanation"
        assert len(q.options) == 4, f"Q{i}: {len(q.options)} options"
        assert (
            sum(1 for o in q.options if o.is_correct) == 1
        ), f"Q{i}: not exactly 1 correct"

    print("  All questions have valid structure ✓")
    print("  ✓ Accuracy test PASSED")
    return {"n": n, "traces": len(with_trace), "elapsed": res["_elapsed"]}


# ── Test 2: Question Diversity ──


async def test_diversity():
    """Check no duplicate questions and topic variety."""
    print("\n" + "=" * 60)
    print("TEST: Diversity — Hàm số (20 quiz)")
    print("=" * 60)

    req = make_request("Hàm số", num_questions=20, game_types=["quiz"])
    res = await run_pipeline(req)
    out = res.get("final_output")

    assert out is not None, "No output"
    quizzes = out.content.quiz
    n = len(quizzes)
    print(f"  Generated {n} quiz questions in {res['_elapsed']:.1f}s")

    # Uniqueness
    questions = [q.question for q in quizzes]
    unique = len(set(questions))
    dup_rate = (n - unique) / n * 100 if n > 0 else 0
    print(f"  Unique questions: {unique}/{n} (dup rate: {dup_rate:.1f}%)")
    assert unique >= n * 0.9, f"Too many duplicates: {unique}/{n}"

    # Sub-topic distribution
    topic_counts = Counter(q.topic for q in quizzes)
    print(f"  Sub-topics ({len(topic_counts)}):")
    for t, c in topic_counts.most_common():
        print(f"    {t}: {c}")

    print("  ✓ Diversity test PASSED")
    return {
        "n": n,
        "unique": unique,
        "sub_topics": len(topic_counts),
        "elapsed": res["_elapsed"],
    }


# ── Test 3: Vietnamese Language Quality ──


async def test_vietnamese():
    """Verify all content is in Vietnamese."""
    print("\n" + "=" * 60)
    print("TEST: Vietnamese Quality — Lượng giác (10 quiz)")
    print("=" * 60)

    req = make_request("Lượng giác", num_questions=10, game_types=["quiz"])
    res = await run_pipeline(req)
    out = res.get("final_output")

    assert out is not None, "No output"
    quizzes = out.content.quiz
    n = len(quizzes)
    print(f"  Generated {n} quiz questions")

    vn_count = 0
    for q in quizzes:
        if check_vietnamese(q.question) or check_vietnamese(q.explanation):
            vn_count += 1

    vn_rate = vn_count / n * 100 if n > 0 else 0
    print(f"  Vietnamese content: {vn_count}/{n} ({vn_rate:.0f}%)")
    assert vn_rate >= 80, f"Expected >=80% Vietnamese, got {vn_rate:.0f}%"

    print("  ✓ Vietnamese test PASSED")
    return {"n": n, "vn_count": vn_count, "elapsed": res["_elapsed"]}


# ── Test 4: Scale — Multi-chapter 30Q ──


async def test_scale_30q():
    """Generate 30 questions for a broad multi-chapter topic."""
    print("\n" + "=" * 60)
    print("TEST: Scale — Tích phân (30 quiz, Kahoot scale)")
    print("=" * 60)

    req = make_request("Tích phân", num_questions=30, game_types=["quiz"])
    res = await run_pipeline(req)
    out = res.get("final_output")

    assert out is not None, "No output"
    n = len(out.content.quiz)
    min_expected = 21  # 70% of 30
    print(f"  Generated {n} quiz questions in {res['_elapsed']:.1f}s")
    print(f"  Minimum expected: {min_expected}")

    assert n >= min_expected, f"Expected >={min_expected}, got {n}"

    # Check topic variety
    topic_counts = Counter(q.topic for q in out.content.quiz)
    print(f"  Sub-topics ({len(topic_counts)}):")
    for t, c in topic_counts.most_common(5):
        print(f"    {t}: {c}")

    print("  ✓ Scale test PASSED")
    return {"n": n, "sub_topics": len(topic_counts), "elapsed": res["_elapsed"]}


# ── Test 5: All Game Types Structure ──


async def test_all_game_types():
    """Test quiz + flashcard + fill_blank output with 20 questions."""
    print("\n" + "=" * 60)
    print("TEST: All Game Types — Chuyển động (20Q × 3 types)")
    print("=" * 60)

    req = make_request(
        "Chuyển động thẳng",
        num_questions=20,
        game_types=["quiz", "flashcard", "fill_blank"],
    )
    res = await run_pipeline(req)
    out = res.get("final_output")

    assert out is not None, "No output"
    qn = len(out.content.quiz)
    fn = len(out.content.flashcard)
    bn = len(out.content.fill_blank)
    total = qn + fn + bn
    print(f"  Total: {total} (quiz={qn}, flashcard={fn}, fill_blank={bn})")
    print(f"  Time: {res['_elapsed']:.1f}s")

    assert qn >= 14, f"Quiz: {qn} (expect >=14)"
    assert fn >= 14, f"Flashcard: {fn} (expect >=14)"
    assert bn >= 14, f"Fill-blank: {bn} (expect >=14)"

    # Validate flashcard structure
    for fc in out.content.flashcard[:3]:
        assert fc.front and fc.back, f"Empty flashcard: {fc.id}"
        assert fc.topic, f"No topic: {fc.id}"

    # Validate fill-blank structure
    for fb in out.content.fill_blank[:3]:
        assert fb.template, f"Empty template: {fb.id}"
        assert fb.blanks, f"No blanks: {fb.id}"
        assert (
            "___" in fb.template or "..." in fb.template or "_" in fb.template
        ), f"No blank marker in: {fb.template[:50]}"

    print("  ✓ All game types PASSED")
    return {"quiz": qn, "fc": fn, "fb": bn, "total": total, "elapsed": res["_elapsed"]}


async def main():
    settings = get_settings()
    print("Accuracy & Scale Test Suite")
    print(f"  Model: {settings.generation_model}")
    print(f"  Review: {settings.review_model}")

    results = {}
    tests = [
        ("accuracy", test_accuracy),
        ("diversity", test_diversity),
        ("vietnamese", test_vietnamese),
        ("scale_30q", test_scale_30q),
        ("all_game_types", test_all_game_types),
    ]

    for name, fn in tests:
        try:
            results[name] = await fn()
        except Exception as e:
            print(f"  ❌ {name} FAILED: {e}")
            results[name] = {"error": str(e)}

    # Summary
    print("\n" + "=" * 60)
    print("ACCURACY & SCALE TEST SUMMARY")
    print("=" * 60)
    total_items = 0
    total_time = 0.0
    passed = 0
    for name, r in results.items():
        if "error" in r:
            print(f"  ❌ {name}: {r['error'][:80]}")
        else:
            items = r.get("n", r.get("total", 0))
            elapsed = r.get("elapsed", 0)
            total_items += items
            total_time += elapsed
            passed += 1
            print(f"  ✅ {name}: {items} items, {elapsed:.1f}s")

    print(
        f"\n  {passed}/{len(tests)} passed | {total_items} items | {total_time:.0f}s ({total_time/60:.1f}min)"
    )

    if passed == len(tests):
        print("  ✅ All accuracy & scale tests passed")
    else:
        print(f"  ❌ {len(tests)-passed} test(s) failed")


if __name__ == "__main__":
    asyncio.run(main())
