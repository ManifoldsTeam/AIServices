#!/usr/bin/env python3
"""Generate the T4.2 accuracy test notebook."""
import json

nb = {
    "cells": [],
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3 (ipykernel)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.12.12"},
    },
    "nbformat": 4,
    "nbformat_minor": 4,
}


def md(src: str):
    lines = src.split("\n")
    nb["cells"].append(
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [l + "\n" for l in lines[:-1]] + [lines[-1]],
        }
    )


def code(src: str):
    lines = src.split("\n")
    nb["cells"].append(
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [l + "\n" for l in lines[:-1]] + [lines[-1]],
        }
    )


# ─── Cell 0: Title ───
md(
    "# T4.2 Accuracy Testing - Golden Set 100 STEM Questions\n"
    "\n"
    "**Objective:** Generate 100 STEM quiz questions via pipeline, then evaluate correctness using LLM evaluator.\n"
    "\n"
    "**Target:** >= 98% accuracy\n"
    "\n"
    "**Subjects:** Math, Physics, Chemistry (Grades 10-12)"
)

# ─── Cell 1: Setup header ───
md("## 0. Setup")

# ─── Cell 2: Setup code ───
code(
    "import sys, time, re, json, asyncio\n"
    "from pathlib import Path\n"
    "from IPython.display import display, Markdown, HTML\n"
    "\n"
    "project_root = str(Path.cwd().parent.parent)\n"
    "if project_root not in sys.path:\n"
    "    sys.path.insert(0, project_root)\n"
    "\n"
    "from src.config import get_settings\n"
    "from src.api.schemas import (\n"
    "    GenerationRequest, GameType, DifficultyLevel, DocScope,\n"
    "    GameContentResponse, QuizQuestion,\n"
    ")\n"
    "from src.graph.builder import compile_graph\n"
    "from src.graph.state import MAX_REVIEW_ITERATIONS\n"
    "from src.services.llm import get_generation_llm\n"
    "\n"
    "settings = get_settings()\n"
    "\n"
    'display(Markdown(f"""\n'
    "### Configuration\n"
    "| Setting | Value |\n"
    "|---------|-------|\n"
    "| GCP Project | `{settings.gcp_project_id}` |\n"
    "| Generation Model | `{settings.generation_model}` @ `{settings.generation_model_location or settings.gcp_location}` |\n"
    "| Review Model | `{settings.review_model}` @ `{settings.review_model_location}` |\n"
    "| Max Review Iterations | `{MAX_REVIEW_ITERATIONS}` |\n"
    '"""))\n'
    'print("Setup OK")'
)

# ─── Cell 3: Golden set header ───
md("## 1. Golden Test Set Definition")

# ─── Cell 4: Golden topics ───
code(
    "# 10 topics x 10 questions = 100 questions\n"
    "GOLDEN_TOPICS = [\n"
    '    {"topic": "Ham so bac hai va do thi", "subject": "Toan 10", "difficulty": "comprehension"},\n'
    '    {"topic": "Dao ham va ung dung cua dao ham", "subject": "Toan 11", "difficulty": "application"},\n'
    '    {"topic": "Tich phan va ung dung", "subject": "Toan 12", "difficulty": "comprehension"},\n'
    '    {"topic": "So phuc va phuong trinh bac hai trong tap so phuc", "subject": "Toan 12", "difficulty": "application"},\n'
    '    {"topic": "Chuyen dong thang deu va chuyen dong thang bien doi deu", "subject": "Vat ly 10", "difficulty": "comprehension"},\n'
    '    {"topic": "Cac dinh luat Newton ve chuyen dong", "subject": "Vat ly 10", "difficulty": "application"},\n'
    '    {"topic": "Dao dong dieu hoa", "subject": "Vat ly 12", "difficulty": "comprehension"},\n'
    '    {"topic": "Bang tuan hoan cac nguyen to hoa hoc va quy luat bien doi tuan hoan", "subject": "Hoa hoc 10", "difficulty": "recall"},\n'
    '    {"topic": "Phan ung oxi hoa khu va can bang phuong trinh", "subject": "Hoa hoc 10", "difficulty": "application"},\n'
    '    {"topic": "Este va chat beo", "subject": "Hoa hoc 12", "difficulty": "comprehension"},\n'
    "]\n"
    "\n"
    "NUM_QUESTIONS_PER_TOPIC = 10\n"
    "TOTAL_EXPECTED = len(GOLDEN_TOPICS) * NUM_QUESTIONS_PER_TOPIC\n"
    'print(f"{len(GOLDEN_TOPICS)} topics, {TOTAL_EXPECTED} questions expected")'
)

# ─── Cell 5: Helpers header ───
md("## 2. Helper Functions")

# ─── Cell 6: Helpers code ───
code(
    'def make_request(topic, difficulty="comprehension", num_questions=10):\n'
    "    return GenerationRequest(\n"
    '        user_id="accuracy_test_t42",\n'
    "        topic=topic,\n"
    '        game_types=[GameType("quiz")],\n'
    "        num_questions=num_questions,\n"
    "        difficulty=DifficultyLevel(difficulty),\n"
    '        doc_scope=DocScope("system"),\n'
    "    )\n"
    "\n"
    "async def run_pipeline(request):\n"
    "    app = compile_graph()\n"
    "    initial_state = {\n"
    '        "request": request,\n'
    '        "doc_scope": request.doc_scope.value,\n'
    '        "iteration_count": 0,\n'
    '        "rejected_items": [],\n'
    '        "errors": [],\n'
    "    }\n"
    "    t0 = time.time()\n"
    "    result = await app.ainvoke(initial_state)\n"
    "    elapsed = time.time() - t0\n"
    '    return {**result, "_elapsed": elapsed}\n'
    "\n"
    'print("Helpers loaded")'
)

# ─── Cell 7: Generate header ───
md("## 3. Generate All Questions")

# ─── Cell 8: Generate code ───
code(
    "all_questions = []\n"
    "generation_stats = []\n"
    "\n"
    "for idx, topic_info in enumerate(GOLDEN_TOPICS):\n"
    "    print(f\"\\n[{idx+1}/{len(GOLDEN_TOPICS)}] Generating: {topic_info['subject']} - {topic_info['topic']}...\")\n"
    '    req = make_request(topic_info["topic"], difficulty=topic_info["difficulty"])\n'
    "\n"
    "    try:\n"
    "        result = await run_pipeline(req)\n"
    '        output = result.get("final_output")\n'
    '        elapsed = result["_elapsed"]\n'
    '        errors = result.get("errors", [])\n'
    '        iterations = result.get("iteration_count", 0)\n'
    "\n"
    "        if output is None:\n"
    '            print(f"  FAIL No output! Errors: {errors}")\n'
    "            generation_stats.append({\n"
    '                "topic": topic_info["topic"], "subject": topic_info["subject"],\n'
    '                "count": 0, "elapsed": elapsed, "errors": errors, "iterations": iterations,\n'
    "            })\n"
    "            continue\n"
    "\n"
    "        quizzes = output.content.quiz\n"
    "        for q in quizzes:\n"
    '            all_questions.append({"topic_info": topic_info, "quiz": q, "topic_idx": idx})\n'
    "\n"
    "        meta = output.metadata\n"
    "        generation_stats.append({\n"
    '            "topic": topic_info["topic"], "subject": topic_info["subject"],\n'
    '            "count": len(quizzes), "elapsed": elapsed,\n'
    '            "generated": meta.total_generated, "passed": meta.total_passed_review,\n'
    '            "rejected": meta.total_rejected, "iterations": iterations,\n'
    "        })\n"
    '        print(f"  OK {len(quizzes)} questions in {elapsed:.0f}s (gen: {meta.total_generated}, pass: {meta.total_passed_review})")\n'
    "    except Exception as e:\n"
    '        print(f"  EXCEPTION: {e}")\n'
    "        generation_stats.append({\n"
    '            "topic": topic_info["topic"], "subject": topic_info["subject"],\n'
    '            "count": 0, "elapsed": 0, "errors": [str(e)], "iterations": 0,\n'
    "        })\n"
    "\n"
    "total_generated = len(all_questions)\n"
    'total_time = sum(s["elapsed"] for s in generation_stats)\n'
    'print(f"\\n=== Generation Complete: {total_generated}/{TOTAL_EXPECTED} questions in {total_time:.0f}s ===")'
)

# ─── Cell 9: Gen summary ───
code(
    "# Generation summary table\n"
    'rows = ""\n'
    "for s in generation_stats:\n"
    '    status = "OK" if s["count"] >= NUM_QUESTIONS_PER_TOPIC else "WARN" if s["count"] > 0 else "FAIL"\n'
    "    rows += f\"| {status} | {s['subject']} | {s['topic'][:40]} | {s['count']}/{NUM_QUESTIONS_PER_TOPIC} | {s.get('generated','?')}->{s.get('passed','?')} | {s['iterations']} | {s['elapsed']:.0f}s |\\n\"\n"
    "\n"
    'display(Markdown(f"""\n'
    "### Generation Results\n"
    "| | Subject | Topic | Yield | Gen->Pass | Iter | Time |\n"
    "|---|---------|-------|-------|----------|------|------|\n"
    "{rows}\n"
    "| | | **TOTAL** | **{total_generated}/{TOTAL_EXPECTED}** | | | **{total_time:.0f}s** |\n"
    '"""))'
)

# ─── Cell 10: Evaluator header ───
md(
    "## 4. LLM Accuracy Evaluator\n\nUse Gemini 2.5 Flash as independent evaluator to verify each question's correctness."
)

# ─── Cell 11: Evaluator setup ───
code(
    "from pydantic import BaseModel, Field\n"
    "from langchain_core.messages import HumanMessage, SystemMessage\n"
    "\n"
    "class AccuracyVerdict(BaseModel):\n"
    '    correct_answer_valid: bool = Field(description="Is the marked correct answer actually correct?")\n'
    '    explanation_accurate: bool = Field(description="Is the explanation factually accurate?")\n'
    '    distractors_plausible: bool = Field(description="Are wrong options plausible (not obviously wrong)?")\n'
    '    reasoning: str = Field(description="Brief reasoning for the verdict (1-2 sentences)")\n'
    "\n"
    'EVALUATOR_SYSTEM = """You are an expert Vietnamese STEM education evaluator.\n'
    "You verify the correctness of quiz questions for Vietnamese high school students (THPT).\n"
    "\n"
    "For each quiz question, verify:\n"
    "1. Correct answer: Is the option marked as correct ACTUALLY the right answer?\n"
    "   - For math: verify computations step by step\n"
    "   - For physics: check formulas, units, and numerical results\n"
    "   - For chemistry: check reactions, properties, and nomenclature\n"
    "2. Explanation: Is the explanation factually accurate and consistent with the correct answer?\n"
    "3. Distractors: Are the wrong options plausible enough to be educational?\n"
    "\n"
    "Be strict on correctness. A wrong answer or wrong explanation = FAIL.\n"
    'Minor Vietnamese language issues are OK if the content is correct."""\n'
    "\n"
    "def format_quiz_for_eval(q):\n"
    '    options = "\\n".join(\n'
    "        f\"  {'[CORRECT]' if o.is_correct else '[WRONG]'} {o.text}\"\n"
    "        for o in q.options\n"
    "    )\n"
    '    trace = f"\\nComputation trace: {q.computation_trace[:500]}" if q.computation_trace else ""\n'
    '    return f"""Topic: {q.topic}\n'
    "Difficulty: {q.difficulty}\n"
    "Question: {q.question}\n"
    "Options:\n"
    "{options}\n"
    'Explanation: {q.explanation}{trace}"""\n'
    "\n"
    "eval_llm = get_generation_llm(temperature=0.0, max_output_tokens=1024)\n"
    "eval_structured = eval_llm.with_structured_output(AccuracyVerdict)\n"
    'print(f"Evaluator ready: {settings.generation_model} @ temp=0.0")'
)

# ─── Cell 12: Evaluate all questions ───
code(
    "# Evaluate all questions\n"
    "eval_results = []\n"
    "EVAL_BATCH_PAUSE = 0.5\n"
    "\n"
    'print(f"Evaluating {len(all_questions)} questions...")\n'
    "eval_t0 = time.time()\n"
    "\n"
    "for i, item in enumerate(all_questions):\n"
    '    q = item["quiz"]\n'
    "    prompt = format_quiz_for_eval(q)\n"
    "\n"
    "    try:\n"
    "        verdict = await eval_structured.ainvoke([\n"
    "            SystemMessage(content=EVALUATOR_SYSTEM),\n"
    '            HumanMessage(content=f"Evaluate this quiz question:\\n\\n{prompt}"),\n'
    "        ])\n"
    '        eval_results.append({"question_idx": i, "verdict": verdict, "quiz": q, "topic_info": item["topic_info"]})\n'
    "\n"
    '        status = "OK" if verdict.correct_answer_valid and verdict.explanation_accurate else "FAIL"\n'
    "        if (i + 1) % 10 == 0 or not (verdict.correct_answer_valid and verdict.explanation_accurate):\n"
    '            print(f"  [{i+1}/{len(all_questions)}] {status} {q.topic[:30]}... | ans={verdict.correct_answer_valid} exp={verdict.explanation_accurate}")\n'
    "    except Exception as e:\n"
    '        print(f"  [{i+1}] EVAL ERROR: {e}")\n'
    '        eval_results.append({"question_idx": i, "verdict": None, "quiz": q, "topic_info": item["topic_info"]})\n'
    "\n"
    "    if EVAL_BATCH_PAUSE > 0:\n"
    "        await asyncio.sleep(EVAL_BATCH_PAUSE)\n"
    "\n"
    "eval_time = time.time() - eval_t0\n"
    'print(f"\\nEvaluation complete in {eval_time:.0f}s")'
)

# ─── Cell 13: Accuracy header ───
md("## 5. Accuracy Analysis")

# ─── Cell 14: Overall accuracy ───
code(
    "# Overall accuracy\n"
    'total_evaluated = len([r for r in eval_results if r["verdict"] is not None])\n'
    'correct_answer = sum(1 for r in eval_results if r["verdict"] and r["verdict"].correct_answer_valid)\n'
    'correct_explanation = sum(1 for r in eval_results if r["verdict"] and r["verdict"].explanation_accurate)\n'
    'correct_distractors = sum(1 for r in eval_results if r["verdict"] and r["verdict"].distractors_plausible)\n'
    'fully_correct = sum(1 for r in eval_results if r["verdict"] and r["verdict"].correct_answer_valid and r["verdict"].explanation_accurate)\n'
    "\n"
    "ans_pct = correct_answer / total_evaluated * 100 if total_evaluated > 0 else 0\n"
    "exp_pct = correct_explanation / total_evaluated * 100 if total_evaluated > 0 else 0\n"
    "dist_pct = correct_distractors / total_evaluated * 100 if total_evaluated > 0 else 0\n"
    "full_pct = fully_correct / total_evaluated * 100 if total_evaluated > 0 else 0\n"
    "\n"
    'target_met = "TARGET MET" if full_pct >= 98 else "BELOW TARGET"\n'
    "\n"
    'display(Markdown(f"""\n'
    "## Overall Accuracy Results\n"
    "\n"
    "| Metric | Count | Percentage | Target |\n"
    "|--------|-------|------------|--------|\n"
    "| Total generated | {len(all_questions)} | | 100 |\n"
    "| Total evaluated | {total_evaluated} | | |\n"
    "| Correct answer | {correct_answer}/{total_evaluated} | **{ans_pct:.1f}%** | >= 98% |\n"
    "| Accurate explanation | {correct_explanation}/{total_evaluated} | **{exp_pct:.1f}%** | >= 98% |\n"
    "| Plausible distractors | {correct_distractors}/{total_evaluated} | **{dist_pct:.1f}%** | |\n"
    "| **Fully correct (ans + exp)** | **{fully_correct}/{total_evaluated}** | **{full_pct:.1f}%** | **>= 98%** |\n"
    "\n"
    "### {target_met} -- Accuracy: {full_pct:.1f}%\n"
    '"""))'
)

# ─── Cell 15: Per-subject ───
code(
    "# Per-subject breakdown\n"
    "from collections import defaultdict\n"
    'subject_stats = defaultdict(lambda: {"total": 0, "correct": 0, "ans_fail": 0, "exp_fail": 0})\n'
    "\n"
    "for r in eval_results:\n"
    '    if r["verdict"] is None:\n'
    "        continue\n"
    '    subj = r["topic_info"]["subject"].split()[0]\n'
    '    subject_stats[subj]["total"] += 1\n'
    '    if r["verdict"].correct_answer_valid and r["verdict"].explanation_accurate:\n'
    '        subject_stats[subj]["correct"] += 1\n'
    '    if not r["verdict"].correct_answer_valid:\n'
    '        subject_stats[subj]["ans_fail"] += 1\n'
    '    if not r["verdict"].explanation_accurate:\n'
    '        subject_stats[subj]["exp_fail"] += 1\n'
    "\n"
    'rows = ""\n'
    'for subj in ["Toan", "Vat", "Hoa"]:\n'
    "    s = subject_stats[subj]\n"
    '    pct = s["correct"] / s["total"] * 100 if s["total"] > 0 else 0\n'
    '    name = {"Toan": "Mathematics", "Vat": "Physics", "Hoa": "Chemistry"}[subj]\n'
    "    rows += f\"| {name} | {s['total']} | {s['correct']} | {pct:.1f}% | {s['ans_fail']} | {s['exp_fail']} |\\n\"\n"
    "\n"
    'display(Markdown(f"""\n'
    "### Per-Subject Accuracy\n"
    "| Subject | Evaluated | Correct | Accuracy | Ans Fails | Exp Fails |\n"
    "|---------|-----------|---------|----------|-----------|----------|\n"
    '{rows}"""))'
)

# ─── Cell 16: Show failures ───
code(
    "# Show ALL failures for debugging\n"
    'failures = [r for r in eval_results if r["verdict"] and not (r["verdict"].correct_answer_valid and r["verdict"].explanation_accurate)]\n'
    'eval_errors = [r for r in eval_results if r["verdict"] is None]\n'
    "\n"
    "if not failures and not eval_errors:\n"
    '    display(Markdown("### No failures detected!"))\n'
    "else:\n"
    '    display(Markdown(f"### {len(failures)} failures + {len(eval_errors)} eval errors\\n"))\n'
    "    for f in failures:\n"
    '        q = f["quiz"]\n'
    '        v = f["verdict"]\n'
    '        correct_opt = next((o.text for o in q.options if o.is_correct), "N/A")\n'
    '        display(Markdown(f"""\n'
    "---\n"
    "**FAIL #{f['question_idx']+1}** [{f['topic_info']['subject']}] -- {q.topic}\n"
    "\n"
    "> {q.question}\n"
    "\n"
    "Marked correct: _{correct_opt}_\n"
    "\n"
    "| Check | Result |\n"
    "|-------|--------|\n"
    '| Answer correct | {"PASS" if v.correct_answer_valid else "FAIL"} |\n'
    '| Explanation accurate | {"PASS" if v.explanation_accurate else "FAIL"} |\n'
    '| Distractors plausible | {"PASS" if v.distractors_plausible else "FAIL"} |\n'
    "\n"
    "**Evaluator reasoning:** {v.reasoning}\n"
    '"""))'
)

# ─── Cell 17: Summary header ───
md("## 6. Final Summary")

# ─── Cell 18: Final summary ───
code(
    'display(Markdown(f"""\n'
    "## T4.2 Accuracy Test Report\n"
    "\n"
    '**Date:** {time.strftime("%Y-%m-%d %H:%M")}\n'
    "\n"
    "| Metric | Value |\n"
    "|--------|-------|\n"
    "| Topics tested | {len(GOLDEN_TOPICS)} |\n"
    "| Questions generated | {len(all_questions)} / {TOTAL_EXPECTED} |\n"
    "| Questions evaluated | {total_evaluated} |\n"
    "| **Answer accuracy** | **{ans_pct:.1f}%** |\n"
    "| **Explanation accuracy** | **{exp_pct:.1f}%** |\n"
    "| **Overall accuracy (ans+exp)** | **{full_pct:.1f}%** |\n"
    "| Target | >= 98% |\n"
    "| **Result** | **{target_met}** |\n"
    "| Generation time | {total_time:.0f}s |\n"
    "| Evaluation time | {eval_time:.0f}s |\n"
    "| Total time | {total_time + eval_time:.0f}s |\n"
    "\n"
    "### Failures: {len(failures)} | Eval errors: {len(eval_errors)}\n"
    '"""))'
)

with open("notebooks/tests/test_accuracy_t42.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"Wrote {len(nb['cells'])} cells")
