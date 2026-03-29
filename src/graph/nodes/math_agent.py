"""Math Agent node — handles STEM content generation.

The Math Agent (Phase 1) specializes in:
- Mathematics, Physics, Chemistry content
- Uses Code Execution for accurate calculations
- Queries Vertex AI Search for document context

This agent uses a two-phase approach:
1. Retrieves relevant document chunks via Vertex AI Search
2. Generates content using Gemini + Code Execution (verifies calculations)
3. Parses the response into structured ContentItemList format
4. Includes computation traces for math problems

Performance optimizations:
- Code traces truncated to MAX_CODE_TRACES_CHARS before parsing
- Batch parsing runs concurrently via asyncio.gather()
- Parse failures retry within math_agent (avoid full pipeline restart)
- Early termination on empty code execution output
"""

import asyncio
import math
import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from src.config.constants import (
    GENERATION_MAX_TOKENS,
    GENERATION_TEMPERATURE,
    PARSE_BATCH_SIZE,
    YIELD_OVERSHOOT_RATIO,
    OVERSHOOT_BY_DIFFICULTY,
)

from src.graph.state import AgentState
from src.api.schemas import ContentItem
from src.config import get_settings
from src.services.vertex_search import retrieve_context
from src.services.llm import get_generation_llm
from src.services.rate_limiter import rate_limited_llm_call

logger = structlog.get_logger(__name__)

# ─── Performance Tuning Constants ────────────────────────────────────
MAX_CODE_TRACES_CHARS: int = 8000
"""Cap code traces passed to parsing prompt (prevents overwhelming the parser)."""

MAX_PARSE_RETRIES: int = 2
"""Parse retry count per batch (reduced from 3 — third attempt rarely succeeds)."""

MAX_GENERATION_RETRIES: int = 2
"""Number of times to retry Phase 1 code execution within math_agent before giving up.
Replaces full pipeline restart on parse failure."""


class GeneratedContentItem(BaseModel):
    """Schema for LLM structured output."""

    question: str = Field(..., description="The question in Vietnamese")
    answer: str = Field(..., description="The correct answer")
    explanation: str = Field(..., description="Explanation in Vietnamese")
    topic: str = Field(..., description="Specific topic")
    computation_trace: str | None = Field(
        default=None, description="Python code and output if calculation was needed"
    )


class ContentItemList(BaseModel):
    """List of generated content items."""

    items: list[GeneratedContentItem]


# ─── P1: Few-Shot Exemplars per Difficulty Level ─────────────────────
DIFFICULTY_EXEMPLARS: dict[str, list[dict[str, str]]] = {
    "recall": [
        {
            "question": "Cho hàm số y = x⁴. Tính đạo hàm y'.",
            "answer": "y' = 4x³",
            "explanation": "Áp dụng trực tiếp công thức đạo hàm lũy thừa: (xⁿ)' = n·xⁿ⁻¹ với n = 4.",
        },
    ],
    "comprehension": [
        {
            "question": "Giải thích ý nghĩa hình học của đạo hàm f'(a) tại điểm x = a.",
            "answer": "f'(a) là hệ số góc của tiếp tuyến với đồ thị y = f(x) tại điểm có hoành độ x = a.",
            "explanation": "f'(a) = tan(α) với α là góc giữa tiếp tuyến và chiều dương Ox. "
            "Ví dụ: f(x) = x² thì f'(1) = 2, tiếp tuyến tại (1,1) là y = 2x - 1.",
        },
    ],
    "application": [
        {
            "question": "Tìm GTLN, GTNN của f(x) = x³ - 3x + 2 trên [-2, 2].",
            "answer": "max f = 4 (tại x = -1 và x = 2), min f = 0 (tại x = 1 và x = -2).",
            "explanation": "f'(x) = 3x² - 3 = 0 ⟹ x = ±1 ∈ [-2,2]. "
            "So sánh f(-2)=0, f(-1)=4, f(1)=0, f(2)=4 → max=4, min=0.",
        },
    ],
    "high_application": [
        {
            "question": "Cho hàm số y = x³ - 3mx + 2 (m là tham số). Tìm m để đồ thị có hai "
            "điểm cực trị A, B sao cho tam giác OAB có diện tích bằng 4.",
            "answer": "m = ∛4.",
            "explanation": "Kết hợp: (1) y' = 3x²-3m=0, cần m>0; "
            "(2) Tọa độ cực trị A(-√m, 2+2m√m), B(√m, 2-2m√m); "
            "(3) S_OAB = ½|det| = 4 → giải theo m. "
            "Bài toán tổng hợp đạo hàm + hình giải tích + cực trị.",
        },
        {
            "question": "Hộp chữ nhật không nắp, đáy vuông. Tổng diện tích đáy và mặt bên bằng "
            "48 cm². Tìm kích thước để thể tích lớn nhất.",
            "answer": "Cạnh đáy x = 4 cm, chiều cao h = 2 cm, V_max = 32 cm³.",
            "explanation": "x² + 4xh = 48 → h = (48-x²)/(4x). "
            "V = x²h = x(48-x²)/4. V'=(48-3x²)/4=0 → x=4, h=2. "
            "Bài toán tối ưu: mô hình hóa thực tế + đạo hàm.",
        },
    ],
}

HIGH_APPLICATION_TOPIC_EXEMPLARS: dict[str, list[dict[str, str]]] = {
    "chemistry": [
        {
            "question": "Trong phòng thí nghiệm, cho hỗn hợp bột Fe và Cu tác dụng với dung dịch H2SO4 loãng dư. "
            "Sau phản ứng thu được khí A và chất rắn B. Hãy đề xuất quy trình tối ưu để định lượng phần trăm khối lượng Fe trong hỗn hợp ban đầu, "
            "nêu rõ các phép đo cần thực hiện và công thức tính.",
            "answer": "Đo thể tích khí H2 (A) ở điều kiện chuẩn để suy ra n(Fe) = n(H2), rồi tính mFe = 56*n(Fe) và %mFe = mFe/mhh * 100%.",
            "explanation": "Bài toán yêu cầu mô hình hóa thực nghiệm + chọn đại lượng đo phù hợp + liên hệ phản ứng Fe + H2SO4 -> FeSO4 + H2. "
            "Cu không phản ứng với H2SO4 loãng, nên khí H2 chỉ do Fe tạo ra.",
        },
        {
            "question": "Thiết kế phương án phân biệt ba dung dịch mất nhãn: Na2SO4, Na2CO3, NaCl chỉ với hai thuốc thử cho trước là HCl và Ba(OH)2. "
            "Yêu cầu lập trình tự thí nghiệm tối ưu và giải thích vì sao phương án là duy nhất.",
            "answer": "Dùng HCl trước để nhận Na2CO3 (sủi khí CO2), sau đó dùng Ba(OH)2 để phân biệt Na2SO4 (kết tủa BaSO4) và NaCl (không hiện tượng).",
            "explanation": "Đây là bài tổng hợp: chọn thứ tự thuốc thử, tránh nhiễu hiện tượng, và chứng minh tính duy nhất của chuỗi quyết định.",
        },
        {
            "question": "Hòa tan hoàn toàn m gam hỗn hợp X gồm Fe, Fe2O3, Fe3O4 trong dung dịch HNO3 loãng dư. "
            "Sau phản ứng thu được 2,24 lít khí NO (đktc) và dung dịch chỉ chứa Fe(NO3)3. "
            "Biết tỉ lệ mol Fe : Fe2O3 : Fe3O4 = 1 : 1 : 1. Tính m.",
            "answer": "m = 34,4 gam.",
            "explanation": "Bài tổng hợp nhiều khái niệm: bảo toàn electron (Fe → Fe³⁺, N⁺⁵ → N⁺²), "
            "bảo toàn nguyên tố, hệ phương trình mol. "
            "Yêu cầu thiết lập hệ từ 3 ràng buộc: tỉ lệ mol, bảo toàn e, và thể tích NO.",
        },
        {
            "question": "Đốt cháy hoàn toàn a gam hỗn hợp hai ancol no đơn chức liên tiếp trong dãy đồng đẳng, "
            "thu được 4,48 lít CO2 (đktc) và 5,4 gam H2O. Xác định CTPT hai ancol và tính a.",
            "answer": "Hai ancol là CH3OH và C2H5OH; a = 4,6 gam.",
            "explanation": "Cần kết hợp: (1) bảo toàn C, H, O từ phương trình đốt cháy ancol CnH(2n+2)O, "
            "(2) hệ phương trình 2 ẩn từ nCO2 và nH2O, "
            "(3) nhận dạng 'liên tiếp trong dãy đồng đẳng' để ràng buộc n. "
            "Bài toán yêu cầu tổng hợp kiến thức hữu cơ + kỹ năng lập hệ.",
        },
    ],
    "physics": [
        {
            "question": "Một nhóm học sinh cần thiết kế thí nghiệm xác định hệ số ma sát trượt giữa hộp gỗ và mặt bàn bằng điện thoại thông minh (đo gia tốc). "
            "Hãy đề xuất mô hình, đại lượng cần đo, cách xử lý sai số và công thức suy ra hệ số ma sát.",
            "answer": "Dùng định luật II Newton theo phương chuyển động: ma = Fk - μmg (hoặc trường hợp trượt tự do: ma = -μmg), suy ra μ từ hệ số góc dữ liệu a.",
            "explanation": "Bài toán yêu cầu thiết kế thực nghiệm + mô hình hóa + phân tích sai số, vượt mức áp dụng công thức trực tiếp.",
        },
        {
            "question": "Một mạch điện gồm nguồn (suất điện động E, điện trở trong r) mắc nối tiếp với biến trở R. "
            "Khi R = R1 = 3Ω thì công suất mạch ngoài P1 = 12W. Khi R = R2 = 12Ω thì P2 = P1 = 12W. "
            "Giải thích tại sao hai giá trị R khác nhau lại cho cùng công suất, và tìm E, r.",
            "answer": "E = 12V, r = 6Ω. Hai giá trị R cho cùng P vì P(R) = E²R/(R+r)² là hàm bậc hai ẩn R, có tính đối xứng qua Rmax = r.",
            "explanation": "Cần liên hệ: (1) P = E²R/(R+r)², (2) giải hệ P(R1) = P(R2) dẫn đến R1·R2 = r², "
            "(3) giải thích ý nghĩa vật lý: đồ thị P(R) đạt max tại R=r, hai điểm đối xứng có cùng P. "
            "Bài tổng hợp: đại số + mạch điện + phân tích đồ thị.",
        },
    ],
    "biology": [
        {
            "question": "Một quần thể thực vật có gen A quy định hoa đỏ trội hoàn toàn so với gen a quy định hoa trắng. "
            "Thế hệ xuất phát P: 0,36AA : 0,48Aa : 0,16aa. Nếu quần thể tự thụ phấn qua 3 thế hệ, "
            "hãy xác định tỉ lệ kiểu hình hoa đỏ : hoa trắng ở F3 và giải thích xu hướng biến đổi.",
            "answer": "F3: hoa đỏ = 0,72; hoa trắng = 0,28. Tỉ lệ hoa trắng tăng dần qua các thế hệ tự thụ phấn.",
            "explanation": "Cần kết hợp: (1) công thức tự thụ phấn — tỉ lệ Aa giảm theo (1/2)^n, "
            "(2) tính lại AA, Aa, aa sau 3 thế hệ, "
            "(3) tổng hợp kiểu hình từ kiểu gen. "
            "Bài toán yêu cầu vận dụng di truyền quần thể + nhận xét xu hướng tiến hóa.",
        },
    ],
}

# ─── Anti-patterns: common mistakes at high_application level ────────
HIGH_APPLICATION_ANTI_PATTERNS: str = """
COMMON MISTAKES TO AVOID for high_application questions:
1. DO NOT create questions that are just multi-step APPLICATION (routine procedure). 
   High_application requires NON-ROUTINE reasoning: combining concepts from different areas,
   designing experiments, or solving problems with unusual constraints.
2. DO NOT simply make a question harder by adding more numbers or steps.
   Instead, require the student to MODEL the situation, CHOOSE the approach, or SYNTHESIZE 
   information from multiple knowledge domains.
3. DO NOT produce questions that can be solved by a single formula substitution.
   Good high_application questions require the student to SET UP the problem themselves.
4. GOOD patterns: optimization with constraints, experimental design, proof of uniqueness,
   comparison of methods, real-world modeling, cross-topic synthesis.
"""


def _infer_subject(topic: str | None) -> str:
    """Infer coarse subject from topic text for exemplar selection."""
    if not topic:
        return "math"
    t = topic.lower()
    chemistry_keywords = [
        "oxi",
        "hóa",
        "hoa",
        "phản ứng",
        "electron",
        "ion",
        "axit",
        "bazơ",
        "muối",
        "ancol",
        "este",
        "hidrocacbon",
        "hữu cơ",
        "vô cơ",
        "dung dịch",
        "chất",
    ]
    physics_keywords = [
        "newton",
        "động lực",
        "dong luc",
        "chuyển động",
        "chuyen dong",
        "điện",
        "dien",
        "nhiệt",
        "nhiet",
        "quang",
        "sóng",
        "dao động",
        "từ trường",
        "lực",
    ]
    biology_keywords = [
        "sinh",
        "gen",
        "ADN",
        "ARN",
        "đột biến",
        "di truyền",
        "quần thể",
        "tiến hóa",
        "sinh thái",
        "tế bào",
        "enzyme",
        "quang hợp",
    ]
    if any(k in t for k in biology_keywords):
        return "biology"
    if any(k in t for k in chemistry_keywords):
        return "chemistry"
    if any(k in t for k in physics_keywords):
        return "physics"
    return "math"


import re as _re

# ─── Feedback Error Categories ───────────────────────────────────────
_ERROR_PATTERNS: list[tuple[str, _re.Pattern]] = [
    (
        "cognitive_level",
        _re.compile(
            r"cognitive|level|mức|nhận thức|recall|comprehension|application|routine|non-routine",
            _re.IGNORECASE,
        ),
    ),
    (
        "accuracy",
        _re.compile(
            r"accura|incorrect|sai|wrong|error|lỗi|tính toán|calculation|formula|công thức"
            r"|inconsistent|mismatch|không khớp|math",
            _re.IGNORECASE,
        ),
    ),
    (
        "clarity",
        _re.compile(
            r"clar|ambig|unclear|mơ hồ|không rõ|confus|vague|structure|cấu trúc",
            _re.IGNORECASE,
        ),
    ),
    (
        "domain",
        _re.compile(
            r"topic|chủ đề|domain|relevance|liên quan|off-topic|ngoài phạm vi",
            _re.IGNORECASE,
        ),
    ),
]

_ERROR_GUIDANCE: dict[str, str] = {
    "cognitive_level": (
        "→ FIX: Ensure questions require NON-ROUTINE reasoning. "
        "Combine concepts from different areas, add constraints that prevent direct formula application."
    ),
    "accuracy": (
        "→ FIX: Double-check all calculations with code execution. "
        "Verify numerical answers, chemical equations balance, and units are correct."
    ),
    "clarity": (
        "→ FIX: Rewrite question with explicit conditions and unambiguous phrasing. "
        "Define all variables and ensure exactly one correct interpretation."
    ),
    "domain": (
        "→ FIX: Align question content strictly with the requested topic. "
        "Reference specific concepts from the provided document context."
    ),
}


def _classify_feedback(feedback: str) -> str:
    """Classify a rejection feedback string into an error category."""
    for category, pattern in _ERROR_PATTERNS:
        if pattern.search(feedback):
            return category
    return "other"


def _build_rejection_feedback(
    rejected_items: list[dict],
    difficulty: str | None = None,
    max_items: int = 5,
) -> str:
    """Build feedback section from previously rejected items (P0).

    Classifies rejection reasons into error categories and provides
    targeted guidance for each category observed.
    """
    if not rejected_items:
        return ""

    filtered = rejected_items
    if difficulty is not None:
        same_difficulty = [
            item for item in rejected_items if item.get("difficulty") == difficulty
        ]
        if same_difficulty:
            filtered = same_difficulty

    if not filtered:
        return ""

    lines = [
        "PREVIOUS ATTEMPT FEEDBACK (your earlier questions were rejected — avoid these mistakes):"
    ]
    # Classify each rejection and collect categories
    categories_seen: set[str] = set()
    for item in filtered[-max_items:]:
        feedback = item.get("review_feedback", "No specific feedback")
        question_preview = item.get("question", "")[:100]
        score = item.get("review_score", "N/A")
        category = _classify_feedback(feedback)
        categories_seen.add(category)
        lines.append(f'- Rejected [{category}] (score={score}): "{question_preview}"')
        lines.append(f"  Reason: {feedback}")

    # Add targeted guidance for each observed error category
    if categories_seen:
        lines.append("\nTARGETED FIX GUIDANCE:")
        for cat in categories_seen:
            guidance = _ERROR_GUIDANCE.get(
                cat, "→ FIX: Address the specific feedback above."
            )
            lines.append(f"  {cat}: {guidance}")

    lines.append(
        "\nGenerate NEW questions that address the above feedback. "
        "Do NOT repeat rejected questions."
    )
    return "\n".join(lines)


def _build_exemplars_section(difficulty: str, topic: str | None = None) -> str:
    """Build few-shot exemplar section for the given difficulty (P1)."""
    exemplars = list(DIFFICULTY_EXEMPLARS.get(difficulty, []))

    if difficulty == "high_application":
        subject = _infer_subject(topic)
        exemplars.extend(HIGH_APPLICATION_TOPIC_EXEMPLARS.get(subject, []))

    if not exemplars:
        return ""

    lines = [
        f"EXEMPLAR QUESTIONS at '{difficulty}' level "
        "(use as reference for quality and cognitive level):"
    ]
    for i, ex in enumerate(exemplars, 1):
        lines.append(f"\nExemplar {i}:")
        lines.append(f"  Question: {ex['question']}")
        lines.append(f"  Answer: {ex['answer']}")
        lines.append(f"  Explanation: {ex['explanation']}")

    lines.append(
        "\nGenerate questions at this cognitive level. "
        "Match the complexity and depth shown above."
    )

    # Add anti-patterns for high_application to steer away from common mistakes
    if difficulty == "high_application":
        lines.append(HIGH_APPLICATION_ANTI_PATTERNS)

    return "\n".join(lines)


MATH_AGENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert Vietnamese educational content creator specializing in STEM subjects (Math, Physics, Chemistry) for THPT (high school) level.

Your task is to generate {num_questions} educational questions based on the provided document context.

COGNITIVE DIFFICULTY LEVELS (aligned with Vietnamese THPT standards):
- recall (Nhan biet): Test knowledge recognition, recall of facts/formulas/definitions
- comprehension (Thong hieu): Require explanation, interpretation, or demonstration of understanding
- application (Van dung): Require applying procedures to solve routine multi-step problems
- high_application (Van dung cao): Require non-routine reasoning, synthesis, or modeling across concepts

REQUIREMENTS:
1. All content MUST be in Vietnamese
2. Questions MUST match the cognitive level: {difficulty}
3. For math/physics problems with calculations:
   - You MUST use the code execution tool to write and run Python code that verifies your calculations
   - Show the computation steps in your explanation
   - Do NOT guess numerical answers — always verify with code
4. Each question must have:
   - Clear, unambiguous question text
   - Correct answer (verified by code execution for math)
   - Detailed explanation referencing the verified computation
   - Topic classification
5. Questions should be varied and test different aspects of the topic

CODE EXECUTION CONSTRAINTS (IMPORTANT):
- Keep verification code CONCISE — maximum 3 Python code cells total
- Each code cell should be self-contained and SHORT (under 30 lines)
- Do NOT write complex simulations, Monte Carlo, or iterative searches
- Use direct formulas and standard library functions (math, sympy) where possible
- For multiple questions, you may verify several in a single code cell
- Focus on VERIFICATION, not elaborate computation

{feedback_section}
{exemplars_section}
CONTEXT FROM DOCUMENTS:
{context}

TOPIC FOCUS: {topic}

Generate exactly {num_questions} questions at the '{difficulty}' cognitive level. For every math/physics question with
numerical answers, USE CODE EXECUTION to verify the answer before presenting it.""",
        ),
        (
            "human",
            "Generate {num_questions} questions at '{difficulty}' cognitive level about {topic}. "
            "Use code execution to verify all calculations. Keep code cells concise (max 3 cells, max 30 lines each).",
        ),
    ]
)


PARSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """Parse the following raw content into a structured list of educational items.

For each question found:
- Extract question, answer, explanation, and topic (all in Vietnamese)
- If Python code was used to verify calculations, include it as computation_trace
  formatted as: "Code:\\n<code>\\nOutput:\\n<output>"
- If no code was used for that question, set computation_trace to null

Return exactly {num_questions} items.""",
        ),
        (
            "human",
            """Raw generated content:
{raw_content}

Code execution traces:
{code_traces_section}""",
        ),
    ]
)


def _get_llm() -> BaseChatModel:
    """Get Gemini LLM for content generation."""
    return get_generation_llm(
        temperature=GENERATION_TEMPERATURE, max_output_tokens=GENERATION_MAX_TOKENS
    )


def _extract_content_with_traces(response: AIMessage) -> tuple[str, list[str]]:
    """Extract text content and code execution traces from LLM response.

    Gemini code execution responses may contain multiple parts:
    - text parts (explanations, questions)
    - executable_code parts (Python code that was run)
    - code_execution_result parts (output of the code)

    Returns:
        tuple of (full_text_content, list_of_code_traces)
    """
    text_parts: list[str] = []
    code_traces: list[str] = []

    content = response.content

    if isinstance(content, str):
        return content, []

    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict):
                if "text" in part:
                    text_parts.append(part["text"])
                elif "executable_code" in part:
                    ec = part["executable_code"]
                    code = (
                        ec.get("code", "")
                        if isinstance(ec, dict)
                        else getattr(ec, "code", str(ec))
                    )
                    code_traces.append(f"Code:\n{code}")
                elif "code_execution_result" in part:
                    er = part["code_execution_result"]
                    output = (
                        er.get("output", "")
                        if isinstance(er, dict)
                        else getattr(er, "output", str(er))
                    )
                    code_traces.append(f"Output:\n{output}")
            elif hasattr(part, "text") and part.text:
                text_parts.append(part.text)
            elif hasattr(part, "executable_code") and part.executable_code:
                code = getattr(part.executable_code, "code", str(part.executable_code))
                code_traces.append(f"Code:\n{code}")
            elif hasattr(part, "code_execution_result") and part.code_execution_result:
                output = getattr(
                    part.code_execution_result,
                    "output",
                    str(part.code_execution_result),
                )
                code_traces.append(f"Output:\n{output}")

    return "\n".join(text_parts), code_traces


def _truncate_code_traces(
    code_traces: list[str], max_chars: int = MAX_CODE_TRACES_CHARS
) -> str:
    """Truncate code traces to prevent overwhelming the parsing LLM.

    Joins code trace strings and truncates to max_chars, preserving
    complete trace blocks (Code:/Output: pairs) where possible.

    Returns:
        Truncated string for the parse prompt.
    """
    if not code_traces:
        return "No code execution traces."

    full = "\n".join(code_traces)
    if len(full) <= max_chars:
        return full

    # Truncate and add summary
    truncated = full[:max_chars]
    # Try to cut at last complete line
    last_nl = truncated.rfind("\n")
    if last_nl > max_chars * 0.5:
        truncated = truncated[:last_nl]

    omitted = len(full) - len(truncated)
    return (
        f"{truncated}\n\n[... {omitted} chars of code traces omitted for brevity ...]"
    )


async def _parse_batch(
    structured_llm,
    batch_idx: int,
    start: int,
    end: int,
    num_q: int,
    raw_text: str,
    code_traces_section: str,
) -> list[GeneratedContentItem]:
    """Parse a single batch of items from raw text with retry.

    Returns parsed items or empty list on failure.
    """
    batch_size = end - start + 1
    batch_prompt = (
        f"From the raw content below, extract ONLY questions #{start} through #{end} "
        f"(items {start}-{end} out of {num_q} total). Return exactly {batch_size} items.\n\n"
        f"Raw generated content:\n{raw_text}\n\n"
        f"Code execution traces:\n{code_traces_section}"
    )
    batch_messages = [
        {
            "role": "system",
            "content": PARSE_PROMPT.messages[0].prompt.template.format(
                num_questions=batch_size
            ),
        },
        {"role": "human", "content": batch_prompt},
    ]

    for attempt in range(MAX_PARSE_RETRIES):
        batch_result = await rate_limited_llm_call(
            structured_llm.ainvoke(batch_messages)
        )
        if batch_result is not None and isinstance(batch_result, ContentItemList):
            logger.info(
                "math_agent_batch_parsed",
                batch=batch_idx + 1,
                items=len(batch_result.items),
                attempt=attempt + 1,
            )
            return batch_result.items
        logger.warning(
            "math_agent_batch_parse_retry",
            batch=batch_idx + 1,
            attempt=attempt + 1,
        )
        if attempt < MAX_PARSE_RETRIES - 1:
            await asyncio.sleep(0.5 * (attempt + 1))

    logger.warning("math_agent_batch_parse_failed", batch=batch_idx + 1)
    return []


async def _parse_raw_content(
    raw_text: str,
    code_traces: list[str],
    num_to_generate: int,
) -> list[GeneratedContentItem]:
    """Parse raw LLM output into structured items.

    Uses truncated code traces and parallel batch parsing.
    Returns parsed items (may be empty if all parsing fails).
    """
    code_traces_section = _truncate_code_traces(code_traces)
    num_q = num_to_generate

    parse_llm = get_generation_llm(temperature=0.3, max_output_tokens=8192)
    structured_llm = parse_llm.with_structured_output(ContentItemList)

    if num_q <= PARSE_BATCH_SIZE:
        # Small batch — single parse call with retry
        parse_messages = PARSE_PROMPT.format_messages(
            num_questions=num_q,
            raw_content=raw_text,
            code_traces_section=code_traces_section,
        )
        for attempt in range(MAX_PARSE_RETRIES):
            result = await rate_limited_llm_call(structured_llm.ainvoke(parse_messages))
            if result is not None and isinstance(result, ContentItemList):
                return result.items
            logger.warning(
                "math_agent_structured_output_returned_none",
                batch="single",
                attempt=attempt + 1,
            )
            if attempt < MAX_PARSE_RETRIES - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
        return []

    # Large batch — split into chunks and parse SEQUENTIALLY (P4: reliability)
    num_batches = (num_q + PARSE_BATCH_SIZE - 1) // PARSE_BATCH_SIZE
    all_items: list[GeneratedContentItem] = []
    for batch_idx in range(num_batches):
        start = batch_idx * PARSE_BATCH_SIZE + 1
        end = min((batch_idx + 1) * PARSE_BATCH_SIZE, num_q)
        batch_items = await _parse_batch(
            structured_llm,
            batch_idx,
            start,
            end,
            num_q,
            raw_text,
            code_traces_section,
        )
        all_items.extend(batch_items)
    return all_items


async def math_agent_node(state: AgentState) -> dict:
    """Generate STEM educational content items with code execution.

    Uses a two-phase approach with internal retry:
    1. Generate content with Code Execution for verified calculations
    2. Parse the response into structured ContentItemList format
    3. If parsing fails, retry Phase 1+2 within this node (avoids full pipeline restart)

    Reads:
        - state["request"]: GenerationRequest
        - state["doc_scope"]: Document scope for filtering

    Writes:
        - state["search_context"]: Retrieved document chunks
        - state["search_sources"]: Source metadata
        - state["content_items"]: Generated ContentItems
    """
    request = state["request"]
    doc_scope = state.get("doc_scope", request.doc_scope.value)
    iteration_count = state.get("iteration_count", 0)
    rejected_items = state.get("rejected_items", [])
    reviewed_items = state.get("reviewed_items", [])

    # P0: On retry, only generate enough to fill the gap
    if iteration_count > 0 and reviewed_items:
        num_still_needed = max(request.num_questions - len(reviewed_items), 1)
    else:
        num_still_needed = request.num_questions

    # P2: Adaptive overshoot by difficulty
    difficulty_val = request.difficulty.value
    overshoot = OVERSHOOT_BY_DIFFICULTY.get(difficulty_val, YIELD_OVERSHOOT_RATIO)
    num_to_generate = math.ceil(num_still_needed * overshoot)

    # P0: Build rejection feedback for retry iterations
    feedback_section = (
        _build_rejection_feedback(rejected_items, difficulty=difficulty_val)
        if iteration_count > 0
        else ""
    )

    # P1: Build exemplars section
    exemplars_section = _build_exemplars_section(difficulty_val, topic=request.topic)

    logger.info(
        "math_agent_starting",
        user_id=request.user_id,
        topic=request.topic,
        num_questions=request.num_questions,
        num_to_generate=num_to_generate,
        num_still_needed=num_still_needed,
        iteration=iteration_count,
        doc_scope=doc_scope,
    )

    # Step 1: Retrieve context from Vertex AI Search
    query = f"{request.topic or 'STEM'} {request.difficulty.value} level educational content"
    search_context, search_sources = await retrieve_context(
        user_id=request.user_id,
        query=query,
        doc_scope=doc_scope,
        max_documents=10,
    )

    logger.info(
        "math_agent_context_retrieved",
        context_chunks=len(search_context),
    )

    # Build context string
    context = (
        "\n\n---\n\n".join(search_context)
        if search_context
        else "No specific context available. Generate based on general knowledge."
    )

    # Phase 1+2 with internal retry on parse failure
    all_parsed_items: list[GeneratedContentItem] = []

    for gen_attempt in range(MAX_GENERATION_RETRIES):
        try:
            # Phase 1: Generate with code execution
            llm = _get_llm()
            code_exec_llm = llm.bind_tools([{"code_execution": {}}])

            generation_messages = MATH_AGENT_PROMPT.format_messages(
                num_questions=num_to_generate,
                difficulty=difficulty_val,
                topic=request.topic or "General STEM",
                context=context,
                feedback_section=feedback_section,
                exemplars_section=exemplars_section,
            )

            raw_response: AIMessage = await rate_limited_llm_call(
                code_exec_llm.ainvoke(generation_messages)
            )
            raw_text, code_traces = _extract_content_with_traces(raw_response)

            logger.info(
                "math_agent_code_execution_done",
                text_length=len(raw_text),
                code_traces_count=len(code_traces),
                generation_attempt=gen_attempt + 1,
            )

            # Early termination: skip parsing if code execution returned nothing
            if not raw_text.strip():
                logger.warning(
                    "math_agent_empty_generation",
                    generation_attempt=gen_attempt + 1,
                )
                continue  # Retry Phase 1

            # Phase 2: Parse into structured output (parallel batches, truncated traces)
            all_parsed_items = await _parse_raw_content(
                raw_text, code_traces, num_to_generate
            )

            if all_parsed_items:
                logger.info(
                    "math_agent_parse_succeeded",
                    items=len(all_parsed_items),
                    generation_attempt=gen_attempt + 1,
                )
                break  # Success — exit retry loop

            logger.warning(
                "math_agent_parse_failed_retrying",
                generation_attempt=gen_attempt + 1,
                max_attempts=MAX_GENERATION_RETRIES,
            )

        except Exception as e:
            logger.error(
                "math_agent_generation_error",
                error=str(e),
                generation_attempt=gen_attempt + 1,
            )
            if gen_attempt == MAX_GENERATION_RETRIES - 1:
                return {
                    "search_context": search_context,
                    "search_sources": search_sources,
                    "content_items": [],
                    "errors": [f"Math agent generation failed: {str(e)}"],
                }

    if not all_parsed_items:
        logger.error("math_agent_structured_output_all_batches_failed")
        return {
            "search_context": search_context,
            "search_sources": search_sources,
            "content_items": [],
            "errors": [
                "Structured output parsing returned no items after all generation attempts"
            ],
        }

    # Convert to validated ContentItem dicts for state
    content_items = []
    for i, item in enumerate(all_parsed_items):
        doc_scope_value = "system"
        if search_sources and i < len(search_sources):
            source = search_sources[i]
            doc_scope_value = source.get("doc_scope", "system")

        validated = ContentItem(
            question=item.question,
            answer=item.answer,
            explanation=item.explanation,
            topic=item.topic,
            difficulty=request.difficulty,
            context_source=(
                search_sources[0].get("source", "unknown")
                if search_sources
                else "generated"
            ),
            doc_scope=doc_scope_value,
            computation_trace=item.computation_trace,
        )
        content_items.append(validated.model_dump(mode="json"))

    logger.info(
        "math_agent_generated",
        items_count=len(content_items),
    )

    return {
        "search_context": search_context,
        "search_sources": search_sources,
        "content_items": content_items,
    }
