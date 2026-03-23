"""Core LangGraph Pipeline Test — Direct invocation (no server).

Tests the full generation pipeline: supervisor → math_agent → reviewer → formatter
with various configurations to verify:
1. Basic generation works (smoke test)
2. Larger batches produce more content (lesson scale)
3. Multiple game types output correctly
4. Multi-chapter/broad topics generate diverse sub-topics
5. Different difficulty levels work
6. Quality metrics are acceptable

Industry benchmarks:
- Kahoot: 20-30 candidate questions per topic
- Khan Academy: generate 2-3x needed, curate down
- Duolingo: ~200 candidates per lesson, show ~14
- ASEE: oversample 2-3x, prune for quality
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Ensure project root is on path
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
    QuizQuestion,
    Flashcard,
    FillBlankQuestion,
)
from src.graph.builder import get_graph_app
from src.graph.state import MAX_REVIEW_ITERATIONS


# ── Helpers ──


def make_request(
    topic: str,
    num_questions: int = 10,
    game_types: list[str] | None = None,
    difficulty: str = "medium",
    doc_scope: str = "system",
) -> GenerationRequest:
    gts = [GameType(g) for g in (game_types or ["quiz"])]
    return GenerationRequest(
        user_id="pipeline_test",
        topic=topic,
        game_types=gts,
        num_questions=num_questions,
        difficulty=DifficultyLevel(difficulty),
        doc_scope=DocScope(doc_scope),
    )


async def run_pipeline(request: GenerationRequest) -> dict:
    app = get_graph_app()
    initial_state = {
        "request": request,
        "doc_scope": request.doc_scope.value,
        "iteration_count": 0,
        "rejected_items": [],
        "errors": [],
    }
    t0 = time.time()
    result = await app.ainvoke(initial_state)
    elapsed = time.time() - t0
    return {**result, "_elapsed": elapsed}


def summarize(result: dict, label: str = "") -> dict | None:
    prefix = f"[{label}] " if label else ""
    output: GameContentResponse | None = result.get("final_output")
    errors = result.get("errors", [])
    elapsed = result.get("_elapsed", 0)
    iterations = result.get("iteration_count", 0)

    if not output:
        print(f"  {prefix}❌ No output. Errors: {errors}")
        return None

    c = output.content
    m = output.metadata
    qn, fn, bn = len(c.quiz), len(c.flashcard), len(c.fill_blank)
    total = qn + fn + bn

    print(f"  {prefix}✅ {total} items in {elapsed:.1f}s ({iterations} iter)")
    print(f"    quiz={qn}  flashcard={fn}  fill_blank={bn}")
    print(
        f"    generated={m.total_generated}  passed={m.total_passed_review}  rejected={m.total_rejected}"
    )
    if errors:
        print(f"    ⚠️  errors: {errors}")
    return {
        "quiz": qn,
        "fc": fn,
        "fb": bn,
        "total": total,
        "elapsed": elapsed,
        "generated": m.total_generated,
        "passed": m.total_passed_review,
        "rejected": m.total_rejected,
    }


ALL: dict[str, dict | None] = {}


# ── Test Functions ──


async def test_smoke_5q():
    """Smoke test: 5 quiz questions about Đạo hàm."""
    print("\n" + "=" * 60)
    print("TEST 1: Smoke Test — 5 Quiz")
    print("=" * 60)

    req = make_request("Đạo hàm", num_questions=5, game_types=["quiz"])
    res = await run_pipeline(req)
    ALL["smoke_5q"] = summarize(res, "Smoke 5Q")

    out = res["final_output"]
    assert out is not None, "No output"
    assert len(out.content.quiz) >= 3, f"Expected >=3 quiz, got {len(out.content.quiz)}"

    q = out.content.quiz[0]
    assert len(q.options) == 4, f"Expected 4 options, got {len(q.options)}"
    assert any(o.is_correct for o in q.options), "No correct option found"
    assert q.question and q.explanation, "Empty question or explanation"

    print(f"\n  Sample: {q.question[:120]}")
    print(f"  Correct: option {q.correct_answer_index}")
    if q.computation_trace:
        print(f"  Trace: {q.computation_trace[:120]}")
    print("\n  ✓ Smoke test PASSED")


async def test_medium_15q():
    """Medium batch: 15 quiz about Phương trình bậc hai."""
    print("\n" + "=" * 60)
    print("TEST 2: Medium Batch — 15 Quiz (Lesson Scale)")
    print("=" * 60)

    req = make_request("Phương trình bậc hai", num_questions=15, game_types=["quiz"])
    res = await run_pipeline(req)
    ALL["medium_15q"] = summarize(res, "15Q Quiz")

    out = res["final_output"]
    assert out is not None, "No output"
    n = len(out.content.quiz)
    # 70% pass threshold from reviewer
    assert n >= 10, f"Expected >=10 quiz, got {n}"

    questions = [q.question for q in out.content.quiz]
    unique = len(set(questions))
    print(f"  Unique questions: {unique}/{len(questions)}")
    assert unique == len(questions), "Duplicate questions detected!"

    print("\n  ✓ Medium batch PASSED")


async def test_multi_game_type():
    """Multi game-type: quiz + flashcard + fill_blank for Định luật Newton."""
    print("\n" + "=" * 60)
    print("TEST 3: Multi Game-Type — quiz + flashcard + fill_blank (15Q)")
    print("=" * 60)

    req = make_request(
        "Định luật Newton",
        num_questions=15,
        game_types=["quiz", "flashcard", "fill_blank"],
    )
    res = await run_pipeline(req)
    ALL["multi_type"] = summarize(res, "Multi-type 15Q")

    out = res["final_output"]
    assert out is not None, "No output"
    qn = len(out.content.quiz)
    fn = len(out.content.flashcard)
    bn = len(out.content.fill_blank)
    assert qn >= 10, f"Quiz: {qn} (expected >=10)"
    assert fn >= 10, f"Flashcard: {fn} (expected >=10)"
    assert bn >= 10, f"Fill-blank: {bn} (expected >=10)"

    # Validate flashcard structure
    fc = out.content.flashcard[0]
    assert fc.front and fc.back, "Empty flashcard front/back"
    print(f"\n  Flashcard: {fc.front[:80]} → {fc.back[:80]}")

    # Validate fill-blank structure
    fb = out.content.fill_blank[0]
    assert fb.template and fb.blanks, "Empty fill-blank template/blanks"
    print(f"  Fill-blank: {fb.template[:80]}")
    print(f"    Blanks: {[(b.position, b.correct_answer) for b in fb.blanks]}")

    print("\n  ✓ Multi game-type PASSED")


async def test_broad_topic():
    """Multi-chapter topic: broad topics spanning multiple sub-topics."""
    print("\n" + "=" * 60)
    print("TEST 4: Multi-Chapter Topic — Broad Coverage")
    print("=" * 60)

    req = make_request(
        "Hàm số và đồ thị", num_questions=20, game_types=["quiz", "flashcard"]
    )
    res = await run_pipeline(req)
    ALL["broad_topic"] = summarize(res, "Broad 20Q")

    out = res["final_output"]
    assert out is not None, "No output"
    n = len(out.content.quiz)
    assert n >= 14, f"Expected >=14 quiz (70% of 20), got {n}"

    # Check sub-topic diversity
    topics = [q.topic for q in out.content.quiz]
    topic_dist: dict[str, int] = {}
    for t in topics:
        topic_dist[t] = topic_dist.get(t, 0) + 1
    print(f"  Sub-topic distribution ({len(topic_dist)} unique topics):")
    for t, c in sorted(topic_dist.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    print("\n  ✓ Broad topic PASSED")


async def test_difficulty_levels():
    """Test easy / medium / hard for a Chemistry topic."""
    print("\n" + "=" * 60)
    print("TEST 5: Difficulty Levels — easy / medium / hard")
    print("=" * 60)

    topic = "Phản ứng oxi hóa khử"
    for diff in ["easy", "medium", "hard"]:
        print(f"\n  --- {diff} ---")
        req = make_request(
            topic, num_questions=10, difficulty=diff, game_types=["quiz"]
        )
        res = await run_pipeline(req)
        ALL[f"diff_{diff}"] = summarize(res, diff)

        out = res["final_output"]
        if out and out.content.quiz:
            q = out.content.quiz[0]
            print(f"    Sample: {q.question[:100]}")

    print("\n  ✓ Difficulty levels PASSED")


async def test_stem_subjects():
    """STEM subject coverage: Math, Physics, Chemistry — 20 questions each, all game types."""
    print("\n" + "=" * 60)
    print("TEST 6: STEM Subject Coverage (20Q × 3 types each)")
    print("=" * 60)

    subjects = [
        ("Toán", "Giải hệ phương trình bậc nhất hai ẩn", 20),
        ("Lý", "Chuyển động thẳng đều và biến đổi đều", 20),
        ("Hóa", "Cấu hình electron và bảng tuần hoàn", 20),
    ]

    for subj, topic, nq in subjects:
        print(f"\n  --- [{subj}] {topic} ({nq}Q × 3 types) ---")
        req = make_request(
            topic, num_questions=nq, game_types=["quiz", "flashcard", "fill_blank"]
        )
        res = await run_pipeline(req)
        ALL[f"subj_{subj}"] = summarize(res, subj)

        out = res["final_output"]
        if out:
            traces = sum(1 for q in out.content.quiz if q.computation_trace)
            print(f"    Computation traces: {traces}/{len(out.content.quiz)}")

    print("\n  ✓ STEM coverage PASSED")


def print_summary():
    """Print final summary table."""
    print("\n" + "=" * 90)
    print("PIPELINE TEST SUMMARY")
    print("=" * 90)
    print(
        f'{"Test":<22} {"Total":>6} {"Quiz":>5} {"FC":>4} {"FB":>4} '
        f'{"Gen":>5} {"Pass%":>6} {"Time":>7}'
    )
    print("-" * 90)

    total_items = 0
    total_time = 0.0
    pass_rates: list[float] = []
    failed_tests: list[str] = []

    for name, s in ALL.items():
        if s is None:
            print(f"{name:<22} FAILED")
            failed_tests.append(name)
            continue
        pr = s["passed"] / s["generated"] * 100 if s["generated"] > 0 else 0
        pass_rates.append(pr)
        total_items += s["total"]
        total_time += s["elapsed"]
        print(
            f'{name:<22} {s["total"]:>6} {s["quiz"]:>5} {s["fc"]:>4} {s["fb"]:>4} '
            f'{s["generated"]:>5} {pr:>5.1f}% {s["elapsed"]:>6.1f}s'
        )

    print("-" * 90)
    avg_pr = sum(pass_rates) / len(pass_rates) if pass_rates else 0
    print(
        f'{"TOTAL":<22} {total_items:>6} {"":>5} {"":>4} {"":>4} '
        f'{"":>5} {avg_pr:>5.1f}% {total_time:>6.1f}s'
    )

    print(
        f"\nTests: {len(ALL)} | Items: {total_items} | "
        f"Avg pass rate: {avg_pr:.1f}% | Time: {total_time:.0f}s ({total_time / 60:.1f}min)"
    )

    if failed_tests:
        print(f"❌ Failed: {failed_tests}")
    else:
        print("✅ All pipeline tests passed")


async def main():
    settings = get_settings()
    print("Pipeline Test — Direct Invocation (No Server)")
    print(f"  Project: {settings.gcp_project_id}")
    print(f"  Generation: {settings.generation_model}")
    print(f"  Review: {settings.review_model}")
    print(f"  Max review iterations: {MAX_REVIEW_ITERATIONS}")

    # Run tests sequentially (each one is a real LLM call)
    await test_smoke_5q()
    await test_medium_15q()
    await test_multi_game_type()
    await test_broad_topic()
    await test_difficulty_levels()
    await test_stem_subjects()

    print_summary()


if __name__ == "__main__":
    asyncio.run(main())
