from app.agents.nodes import run_review


def invoke_review(file_path: str) -> dict:
    """Stable workflow entry point; nodes can be moved into LangGraph as the workflow grows."""
    return run_review(file_path)
