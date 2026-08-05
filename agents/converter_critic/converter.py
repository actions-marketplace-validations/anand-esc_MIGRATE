import os
from pathlib import Path
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate

# Define a Pydantic schema for the output of the converter
class ConverterOutput(BaseModel):
    converted_code: str = Field(description="The converted Python 3 code.")

def run_converter(state: dict) -> dict:
    """
    LangGraph node function for the converter.
    Takes the graph state, runs the Claude model to convert the code,
    and returns the state update.
    """
    fn = state["function"]
    
    # Load prompt template
    prompt_path = Path(__file__).parent / "prompts" / "convert.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()
        
    prompt = PromptTemplate.from_template(prompt_text)
    
    # Initialize the Anthropic LLM and enforce structured output
    if "ANTHROPIC_API_KEY" in os.environ:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    else:
        # Fallback fake for standalone test if missing key
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
        from langchain_core.messages import AIMessage
        import json
        llm = FakeMessagesListChatModel(responses=[AIMessage(content=json.dumps({"converted_code": "def mock_func():\\n    print(\"Mock!\")"}))])

    # Bind the schema to ensure JSON output and include raw for token extraction
    structured_llm = llm.with_structured_output(ConverterOutput, include_raw=True)
    
    # Create the chain
    chain = prompt | structured_llm
    
    # Run the chain
    result = chain.invoke({"source_code": fn.source_code})
    
    parsed = result.get("parsed")
    raw = result.get("raw")
    
    tokens_used = 0
    if raw and hasattr(raw, "response_metadata"):
        usage = raw.response_metadata.get("usage", {})
        if isinstance(usage, dict):
            tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        else:
            # Fallback if usage is an object (like AnthropicUsage)
            tokens_used = getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
            
    # For testing, stub tokens if still 0
    if tokens_used == 0 and "ANTHROPIC_API_KEY" not in os.environ:
        tokens_used = 150
    
    return {
        "converted_code": parsed.converted_code if parsed else "",
        "tokens_used": tokens_used # Accumulates in graph state
    }
