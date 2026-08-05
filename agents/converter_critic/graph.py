import sys
import os
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langtrace_python_sdk import langtrace
from pydantic import ValidationError

# Ensure we can import from shared.schemas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from shared.schemas import ClassifiedFunction, ConversionResult

from agents.converter_critic.converter import run_converter
from agents.converter_critic.critic import run_critic

class GraphState(TypedDict):
    function: ClassifiedFunction
    converted_code: str
    critic_verdict: str
    critic_notes: str
    tokens_used: int

def build_graph():
    builder = StateGraph(GraphState)
    builder.add_node("converter", run_converter)
    builder.add_node("critic", run_critic)
    builder.add_edge(START, "converter")
    builder.add_edge("converter", "critic")
    builder.add_edge("critic", END)
    return builder.compile()

def _run_pipeline(graph, fn: ClassifiedFunction) -> dict:
    initial_state = {
        "function": fn,
        "converted_code": "",
        "critic_verdict": "",
        "critic_notes": "",
        "tokens_used": 0
    }
    final_state = graph.invoke(initial_state)
    return final_state

def run(fn: ClassifiedFunction) -> ConversionResult:
    """
    Main entrypoint for Soumini's convert.py orchestration.
    """
    # Initialize langtrace (requires LANGTRACE_API_KEY environment variable)
    if "LANGTRACE_API_KEY" in os.environ:
        langtrace.init(api_key=os.environ["LANGTRACE_API_KEY"])
        
    graph = build_graph()
    
    attempts = 2
    for attempt in range(attempts):
        try:
            final_state = _run_pipeline(graph, fn)
            
            # Coerce the dictionary into our strict Pydantic model
            result = ConversionResult(
                function_id=fn.function_id,
                converted_code=final_state.get("converted_code", ""),
                critic_verdict=final_state.get("critic_verdict", "clean"),
                critic_notes=final_state.get("critic_notes", ""),
                tokens_used=final_state.get("tokens_used", 0)
            )
            return result
            
        except ValidationError as e:
            if attempt == attempts - 1:
                # Option 2: Fallback verdict instead of raising an exception downstream
                return ConversionResult(
                    function_id=fn.function_id,
                    converted_code="",
                    critic_verdict="conversion_failed",
                    critic_notes=f"Validation failed after {attempts} attempts: {str(e)}",
                    tokens_used=0
                )
        except Exception as e:
            if attempt == attempts - 1:
                # Option 2: Fallback verdict instead of raising an exception downstream
                return ConversionResult(
                    function_id=fn.function_id,
                    converted_code="",
                    critic_verdict="conversion_failed",
                    critic_notes=f"Execution failed after {attempts} attempts: {str(e)}",
                    tokens_used=0
                )
