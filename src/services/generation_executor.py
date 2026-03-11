"""Generation executor shared by Cloud Tasks and local async fallback."""

from src.api.schemas.requests import GenerationRequest
from src.graph.builder import get_graph_app
from src.services.firestore import complete_job, fail_job, get_job


async def execute_generation_job(request_id: str) -> dict:
    """Run LangGraph pipeline for a queued/local generation job and persist result."""
    job = await get_job(request_id)
    if not job:
        raise ValueError("Job not found")

    try:
        request_model = GenerationRequest.model_validate(job["request"])

        graph_input = {
            "request": request_model,
            "doc_scope": request_model.doc_scope.value,
            "iteration_count": 0,
            "rejected_items": [],
            "errors": [],
        }

        graph_app = get_graph_app()
        final_state = await graph_app.ainvoke(graph_input)
        final_output = final_state.get("final_output")

        if final_output is None:
            raise RuntimeError("Pipeline completed without final_output")

        output_dict = (
            final_output.model_dump(mode="json")
            if hasattr(final_output, "model_dump")
            else dict(final_output)
        )
        output_dict["request_id"] = request_id

        await complete_job(request_id=request_id, content=output_dict)
        return {"ok": True, "request_id": request_id, "status": "completed"}

    except Exception as exc:
        await fail_job(request_id=request_id, error=str(exc))
        raise
