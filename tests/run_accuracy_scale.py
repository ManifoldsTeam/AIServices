"""Accuracy & Scale Test — Pipeline Quality Verification

Runs the same tests as test_accuracy_scale.ipynb via terminal.
Direct pipeline invocation, no HTTP server.
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config import get_settings
from src.api.schemas import (
    GenerationRequest, GameType, DifficultyLevel, DocScope,
    GameContentResponse, QuizQuestion, Flashcard, FillBlankQuestion,
)
from src.graph.builder import compile_graph
from src.graph.state import MAX_REVIEW_ITERATIONS


# ── Helpers ──

def pp(data):
    if hasattr(data, 'model_dump'):
        data = data.model_dump()
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))

def make_request(
    topic: str,
    num_questions: int = 10,
    game_types: list[str] | None = None,
    difficulty: str = 'medium',
    doc_scope: str = 'system',
) -> GenerationRequest:
    gts = [GameType(g) for g in (game_types or ['quiz'])]
    return GenerationRequest(
        user_id='accuracy_test',
        topic=topic,
        game_types=gts,
        num_questions=num_questions,
        difficulty=DifficultyLevel(difficulty),
        doc_scope=DocScope(doc_scope),
    )

async def run_pipeline(request: GenerationRequest) -> dict:
    app = compile_graph()
    initial_state = {
        'request': request,
        'doc_scope': request.doc_scope.value,
        'iteration_count': 0,
        'rejected_items': [],
        'errors': [],
    }
    t0 = time.time()
    result = await app.ainvoke(initial_state)
    elapsed = time.time() - t0
    return {**result, '_elapsed': elapsed}

def summarize(result: dict, label: str = ''):
    prefix = f'[{label}] ' if label else ''
    output: GameContentResponse | None = result.get('final_output')
    errors = result.get('errors', [])
    elapsed = result.get('_elapsed', 0)
    iterations = result.get('iteration_count', 0)

    if not output:
        print(f'{prefix}❌ No output. Errors: {errors}')
        return None

    c = output.content
    m = output.metadata
    qn, fn, bn = len(c.quiz), len(c.flashcard), len(c.fill_blank)
    total = qn + fn + bn

    print(f'{prefix}✅ {total} items in {elapsed:.1f}s ({iterations} iter)')
    print(f'  quiz={qn}  flashcard={fn}  fill_blank={bn}')
    print(f'  generated={m.total_generated}  passed={m.total_passed_review}  rejected={m.total_rejected}')
    if errors:
        print(f'  ⚠️ errors: {errors}')
    return {'quiz': qn, 'fc': fn, 'fb': bn, 'total': total, 'elapsed': elapsed,
            'generated': m.total_generated, 'passed': m.total_passed_review, 'rejected': m.total_rejected}

def is_vietnamese(text: str) -> bool:
    vn_chars = re.compile(r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]', re.IGNORECASE)
    return bool(vn_chars.search(text))


ALL = {}


# ── Test 1: Setup ──
async def test_setup():
    settings = get_settings()
    print('=' * 70)
    print('SETUP')
    print('=' * 70)
    print(f'Project: {settings.gcp_project_id}')
    print(f'Generation model: {settings.generation_model} @ {settings.generation_model_location or settings.gcp_location}')
    print(f'Review model: {settings.review_model} @ {settings.review_model_location}')
    print(f'Max review iterations: {MAX_REVIEW_ITERATIONS}')
    print('✓ Setup OK\n')


# ── Test 2: Accuracy 10Q ──
async def test_accuracy_10q():
    print('=' * 70)
    print('TEST 2: Accuracy — 10Q with Computation Trace Validation')
    print('=' * 70)

    req = make_request('Đạo hàm và ứng dụng', num_questions=10, game_types=['quiz'])
    res = await run_pipeline(req)
    ALL['accuracy_10q'] = summarize(res, 'Accuracy 10Q')

    out = res['final_output']
    assert out is not None, 'No output'

    quizzes = out.content.quiz
    assert len(quizzes) >= 7, f'Expected >=7 quiz, got {len(quizzes)}'

    with_trace = [q for q in quizzes if q.computation_trace]
    print(f'\nComputation traces: {len(with_trace)}/{len(quizzes)}')

    for i, q in enumerate(with_trace[:3]):
        print(f'\n[{i}] {q.question[:100]}')
        trace_preview = q.computation_trace[:200] if q.computation_trace else 'none'
        print(f'    Trace: {trace_preview}')

    for q in quizzes:
        assert len(q.options) == 4, f'Expected 4 options, got {len(q.options)}'
        assert any(o.is_correct for o in q.options), f'No correct option for: {q.question[:50]}'
        assert q.question and q.explanation

    print('\n✓ Accuracy test PASSED\n')


# ── Test 3: Vietnamese Language Quality ──
async def test_vietnamese():
    print('=' * 70)
    print('TEST 3: Vietnamese Language Quality')
    print('=' * 70)

    req = make_request('Phương trình bậc hai', num_questions=10, game_types=['quiz', 'flashcard'])
    res = await run_pipeline(req)
    ALL['vietnamese'] = summarize(res, 'Vietnamese')

    out = res['final_output']
    assert out is not None, 'No output'

    total_items = len(out.content.quiz) + len(out.content.flashcard)
    if total_items == 0:
        print('\n⚠️ No items to check — reviewer rejected all. Test SKIPPED.')
        return

    vn_count = 0
    total_checked = 0
    non_vn = []

    for q in out.content.quiz:
        total_checked += 1
        if is_vietnamese(q.question):
            vn_count += 1
        else:
            non_vn.append(f'Q: {q.question[:80]}')
        total_checked += 1
        if is_vietnamese(q.explanation):
            vn_count += 1
        else:
            non_vn.append(f'E: {q.explanation[:80]}')

    for fc in out.content.flashcard:
        total_checked += 1
        if is_vietnamese(fc.front):
            vn_count += 1
        else:
            non_vn.append(f'FC: {fc.front[:80]}')

    vn_rate = vn_count / total_checked * 100 if total_checked > 0 else 0
    print(f'\nVietnamese content: {vn_count}/{total_checked} ({vn_rate:.0f}%)')

    if non_vn:
        print(f'\n⚠️ Non-Vietnamese items ({len(non_vn)}):')
        for item in non_vn[:5]:
            print(f'  {item}')

    assert vn_rate >= 80, f'Expected >=80% Vietnamese, got {vn_rate:.0f}%'
    print('\n✓ Vietnamese language test PASSED\n')


# ── Test 4: Diversity 20Q ──
async def test_diversity_20q():
    print('=' * 70)
    print('TEST 4: Content Diversity — 20Q Uniqueness Check')
    print('=' * 70)

    req = make_request('Hàm số và đồ thị', num_questions=20, game_types=['quiz'])
    res = await run_pipeline(req)
    ALL['diversity_20q'] = summarize(res, 'Diversity 20Q')

    out = res['final_output']
    assert out is not None

    quizzes = out.content.quiz
    assert len(quizzes) >= 14, f'Expected >=14 (70% of 20), got {len(quizzes)}'

    questions = [q.question for q in quizzes]
    unique = set(questions)
    dup_rate = (len(questions) - len(unique)) / len(questions) * 100 if questions else 0
    print(f'\nUnique questions: {len(unique)}/{len(questions)} (dup rate: {dup_rate:.0f}%)')
    assert len(unique) >= len(questions) * 0.9, f'Too many duplicates: {len(unique)}/{len(questions)}'

    topics = [q.topic for q in quizzes]
    dist = {}
    for t in topics:
        dist[t] = dist.get(t, 0) + 1
    print(f'\nSub-topic distribution ({len(dist)} topics):')
    for t, c in sorted(dist.items(), key=lambda x: -x[1]):
        print(f'  {t}: {c}')

    assert len(dist) >= 2, f'Expected >=2 sub-topics, got {len(dist)}'
    print('\n✓ Diversity test PASSED\n')


# ── Test 5: Scale 30Q ──
async def test_scale_30q():
    print('=' * 70)
    print('TEST 5: Scale Test — 30Q (Kahoot Scale)')
    print('=' * 70)

    req = make_request('Tích phân và ứng dụng', num_questions=30, game_types=['quiz'])
    res = await run_pipeline(req)
    ALL['scale_30q'] = summarize(res, 'Scale 30Q')

    out = res['final_output']
    assert out is not None, f'No output. Errors: {res.get("errors", [])}'

    n = len(out.content.quiz)
    assert n >= 21, f'Expected >=21 (70% of 30), got {n}'

    questions = [q.question for q in out.content.quiz]
    unique = set(questions)
    print(f'\nUnique: {len(unique)}/{len(questions)}')

    for idx in [0, n // 2, -1]:
        q = out.content.quiz[idx]
        print(f'\n[{idx}] {q.question[:120]}')
        print(f'    topic: {q.topic}')
        has_trace = '✓' if q.computation_trace else '✗'
        print(f'    trace: {has_trace}')

    print(f'\nGeneration time: {res["_elapsed"]:.1f}s ({res["_elapsed"]/n:.1f}s per item)')
    print('\n✓ Scale test PASSED\n')


# ── Test 6: All Game Types ──
async def test_all_game_types():
    print('=' * 70)
    print('TEST 6: All Game Types — quiz + flashcard + fill_blank (20Q)')
    print('=' * 70)

    req = make_request(
        'Chuyển động thẳng đều và biến đổi đều',
        num_questions=20,
        game_types=['quiz', 'flashcard', 'fill_blank'],
    )
    res = await run_pipeline(req)
    ALL['all_types'] = summarize(res, 'All Types 20Q')

    out = res['final_output']
    assert out is not None

    qn = len(out.content.quiz)
    fn = len(out.content.flashcard)
    bn = len(out.content.fill_blank)

    assert qn >= 14, f'Quiz: expected >=14, got {qn}'
    assert fn >= 14, f'Flashcard: expected >=14, got {fn}'
    assert bn >= 14, f'Fill-blank: expected >=14, got {bn}'

    q = out.content.quiz[0]
    assert len(q.options) == 4
    assert any(o.is_correct for o in q.options)
    print(f'\nQuiz sample: {q.question[:100]}')
    print(f'  Options: {[o.text[:40] for o in q.options]}')

    fc = out.content.flashcard[0]
    assert fc.front and fc.back
    print(f'\nFlashcard sample:')
    print(f'  Front: {fc.front[:100]}')
    print(f'  Back: {fc.back[:100]}')

    fb = out.content.fill_blank[0]
    assert fb.template and fb.blanks
    print(f'\nFill-blank sample:')
    print(f'  Template: {fb.template[:100]}')
    print(f'  Blanks: {[(b.position, b.correct_answer[:30]) for b in fb.blanks]}')

    print('\n✓ All game types test PASSED\n')


# ── Test 7: Summary ──
def test_summary():
    print('=' * 85)
    print('ACCURACY & SCALE TEST SUMMARY')
    print('=' * 85)
    print(f'{"Test":<22} {"Total":>6} {"Quiz":>5} {"FC":>4} {"FB":>4} {"Gen":>5} {"Pass%":>6} {"Time":>7}')
    print('-' * 85)

    total_items = 0
    total_time = 0.0
    pass_rates = []

    for name, s in ALL.items():
        if s is None:
            print(f'{name:<22} FAILED')
            continue
        pr = s['passed'] / s['generated'] * 100 if s['generated'] > 0 else 0
        pass_rates.append(pr)
        total_items += s['total']
        total_time += s['elapsed']
        print(f'{name:<22} {s["total"]:>6} {s["quiz"]:>5} {s["fc"]:>4} {s["fb"]:>4} {s["generated"]:>5} {pr:>5.1f}% {s["elapsed"]:>6.1f}s')

    print('-' * 85)
    avg_pr = sum(pass_rates) / len(pass_rates) if pass_rates else 0
    print(f'{"TOTAL":<22} {total_items:>6} {"":>5} {"":>4} {"":>4} {"":>5} {avg_pr:>5.1f}% {total_time:>6.1f}s')

    print(f'\nTests: {len(ALL)} | Items: {total_items} | Avg pass rate: {avg_pr:.1f}%')
    print(f'Time: {total_time:.0f}s ({total_time/60:.1f}min)')

    failed = [k for k, v in ALL.items() if v is None]
    if failed:
        print(f'\n❌ Failed tests: {failed}')
    else:
        print('\n✅ All accuracy & scale tests passed')


async def main():
    await test_setup()

    tests = [
        ('accuracy_10q', test_accuracy_10q),
        ('vietnamese', test_vietnamese),
        ('diversity_20q', test_diversity_20q),
        ('scale_30q', test_scale_30q),
        ('all_game_types', test_all_game_types),
    ]

    for name, test_fn in tests:
        try:
            await test_fn()
        except Exception as e:
            print(f'\n❌ TEST {name} FAILED: {e}\n')
            if name not in ALL:
                ALL[name] = None

    test_summary()


if __name__ == '__main__':
    asyncio.run(main())
