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
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from src.config.constants import (
    GENERATION_MAX_TOKENS,
    GENERATION_TEMPERATURE,
    PARSE_BATCH_SIZE,
    YIELD_OVERSHOOT_RATIO,
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


def _get_llm() -> ChatVertexAI:
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

    # Large batch — split into chunks and parse CONCURRENTLY
    num_batches = (num_q + PARSE_BATCH_SIZE - 1) // PARSE_BATCH_SIZE
    tasks = []
    for batch_idx in range(num_batches):
        start = batch_idx * PARSE_BATCH_SIZE + 1
        end = min((batch_idx + 1) * PARSE_BATCH_SIZE, num_q)
        tasks.append(
            _parse_batch(
                structured_llm,
                batch_idx,
                start,
                end,
                num_q,
                raw_text,
                code_traces_section,
            )
        )

    batch_results = await asyncio.gather(*tasks)
    all_items: list[GeneratedContentItem] = []
    for items in batch_results:
        all_items.extend(items)
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

    # Overshoot: generate more items to buffer against review rejection
    num_to_generate = math.ceil(request.num_questions * YIELD_OVERSHOOT_RATIO)

    logger.info(
        "math_agent_starting",
        user_id=request.user_id,
        topic=request.topic,
        num_questions=request.num_questions,
        num_to_generate=num_to_generate,
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
                difficulty=request.difficulty.value,
                topic=request.topic or "General STEM",
                context=context,
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
