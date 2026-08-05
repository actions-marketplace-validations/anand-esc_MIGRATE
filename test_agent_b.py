import sys
import os
from pydantic import ValidationError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from shared.schemas import ClassifiedFunction
from agents.converter_critic.graph import run

# We will monkey patch the converter to always raise ValidationError 
# to simulate Claude returning malformed JSON that Pydantic rejects.
import agents.converter_critic.graph as graph_module

# Keep the original function
original_run_converter = graph_module.run_converter

call_count = 0

def mock_run_converter(state: dict):
    global call_count
    call_count += 1
    print(f"[Mock] Converter called! Attempt {call_count}")
    # Simulate a Pydantic Validation Error during JSON parsing
    raise ValidationError.from_exception_data("Simulated JSON structural validation failure", line_errors=[])

# Apply patch
graph_module.run_converter = mock_run_converter
# We have to rebuild the graph after patching because it binds the function on build
graph_module.build_graph = lambda: (
    __import__("langgraph.graph").graph.StateGraph(graph_module.GraphState)
    .add_node("converter", mock_run_converter)
    .add_node("critic", graph_module.run_critic)
    .add_edge(graph_module.START, "converter")
    .add_edge("converter", "critic")
    .add_edge("critic", graph_module.END)
    .compile()
)

if __name__ == "__main__":
    stub = ClassifiedFunction(
        function_id="test_malformed_json_001",
        source_code="def test_func():\n    print \"hello\"",
        classification="llm_needed",
        py2_constructs=["print_stmt"]
    )
    
    print(f"Running conversion for {stub.function_id} (simulating malformed LLM JSON output)...")
    result = run(stub)
    print("\nResult:")
    print(result.model_dump_json(indent=2))
    
    assert call_count == 2, f"Expected 2 attempts, got {call_count}"
    assert result.critic_verdict == "conversion_failed", "Verdict should be conversion_failed"
    print("\nTest passed: Retry logic worked and correctly fell back to 'conversion_failed'.")
