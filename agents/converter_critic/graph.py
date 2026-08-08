import os
import requests
from shared.schemas import ParsedFunction, ConversionResult

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")

def call_gemini(prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]

def call_nvidia(prompt: str) -> str:
    invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Accept": "application/json",
    }
    payload = {
      "model": "minimaxai/minimax-m3",
      "messages": [
        {"role": "user", "content": prompt}
      ],
      "temperature": 0.2,
      "max_tokens": 1024,
    }
    response = requests.post(invoke_url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def extract_code(text: str) -> str:
    if "```python" in text:
        return text.split("```python")[1].split("```")[0].strip()
    if "```" in text:
        return text.split("```")[1].split("```")[0].strip()
    return text.strip()

def run(fn: ParsedFunction) -> ConversionResult:
    # 1. Conversion Phase using Gemini
    conversion_prompt = f"""
    You are an expert Python migration engineer. Convert the following Python 2 function to idiomatic Python 3.
    Use semantic refactoring where necessary (e.g., filter returns iterators, map returns iterators, dict.keys() returns views, xrange->range, unicode->str/bytes).
    Output ONLY the python code inside a ```python block. Do not output any other text or explanation.

    ```python
    {fn.source}
    ```
    """
    
    try:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in environment.")
        
        gemini_response = call_gemini(conversion_prompt)
        converted_code = extract_code(gemini_response)
        
    except Exception as e:
        return ConversionResult(
            function_id=fn.function_name,
            converted_code=fn.source,
            critic_verdict="conversion_failed",
            critic_reasoning=f"Gemini API failure: {str(e)}"
        )

    # 2. Critic Phase using NVIDIA MiniMax
    critic_prompt = f"""
    Review this Python 3 conversion of a legacy Python 2 function.
    
    Original Python 2:
    ```python
    {fn.source}
    ```
    
    Converted Python 3:
    ```python
    {converted_code}
    ```
    
    Is the converted code a valid, safe, and logically equivalent Python 3 refactor?
    Answer ONLY with "APPROVED" if it looks correct, or "NEEDS_REVIEW" if there are logical bugs or syntax errors.
    """
    
    try:
        if not NVIDIA_API_KEY:
            raise ValueError("NVIDIA_API_KEY is not set in environment.")
            
        nvidia_response = call_nvidia(critic_prompt)
        verdict_text = nvidia_response.strip().upper()
        
        critic_verdict = "approved" if "APPROVED" in verdict_text else "needs_review"
        
    except Exception as e:
        critic_verdict = "needs_review"
        nvidia_response = f"NVIDIA API failure: {str(e)}"

    return ConversionResult(
        function_id=fn.function_name,
        converted_code=converted_code,
        critic_verdict=critic_verdict,
        critic_reasoning=nvidia_response
    )
