"""
Build 3: HITL + Tool Router Agent with Multi-LLM Support

This agent:
1. Routes user requests to either pre-built tools OR code generation
2. Requires human approval before executing code (HITL)
3. Provides natural language summaries
4. Traces everything via Langfuse

Supports: OpenAI, Anthropic Claude, Kimi (via provider switch)
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from textwrap import dedent

import pandas as pd
from dotenv import load_dotenv

# LangChain imports
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage
from langchain_core.runnables.history import RunnableWithMessageHistory

# Set project root for .env loading
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# Add src to path
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from src import ensure_dirs, read_data, basic_profile, TOOLS, TOOL_DESCRIPTIONS
from src.llm_provider import create_llm, get_provider_name

# --------------------------------------------------------------------------------------
# Langfuse setup
# --------------------------------------------------------------------------------------
LANGFUSE_AVAILABLE = False
try:
    from langfuse import Langfuse, observe
    from langfuse.decorators import observe as observe_decorator
    LANGFUSE_AVAILABLE = True
    langfuse = Langfuse()
except Exception as e:
    LANGFUSE_AVAILABLE = False
    print(f"Langfuse not available: {e}")
    
    def observe(*args, **kwargs):
        def wrapper(fn):
            return fn
        return wrapper


# --------------------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------------------

def profile_to_schema_text(profile: dict) -> str:
    """Convert profile to readable schema text."""
    lines = [
        f"Rows: {profile.get('n_rows')}",
        f"Columns: {profile.get('n_cols')}",
        "",
        "Columns and dtypes:",
    ]
    for col in profile["columns"]:
        lines.append(f"- {col}: {profile['dtypes'].get(col)}")
    return "\n".join(lines)


CODE_BLOCK_RE = re.compile(r"```python\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def extract_python_code(text: str) -> Optional[str]:
    """Extract Python code from markdown fenced block."""
    m = CODE_BLOCK_RE.search(text or "")
    return m.group(1).strip() if m else None


def parse_json_object(raw: str) -> Dict[str, Any]:
    """Parse JSON from text or fenced block."""
    raw = (raw or "").strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        pass

    match = JSON_BLOCK_RE.search(raw)
    if match:
        try:
            obj = json.loads(match.group(1))
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            pass

    # Fallback: extract between first { and last }
    i = raw.find("{")
    j = raw.rfind("}")
    if i != -1 and j != -1 and j > i:
        try:
            obj = json.loads(raw[i : j + 1])
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}

    return {}


def split_sections(text: str) -> Tuple[str, str, str]:
    """Split LLM response into PLAN / CODE / VERIFY sections."""
    if not text:
        return "", "", ""
    up = text.upper()
    i_plan = up.find("PLAN:")
    i_code = up.find("CODE:")
    i_ver = up.find("VERIFY:")
    if i_plan == -1 or i_code == -1 or i_ver == -1:
        return text.strip(), "", ""
    return text[i_plan:i_code].strip(), text[i_code:i_ver].strip(), text[i_ver:].strip()


def coerce_tool_args(raw_args: Any) -> Dict[str, Any]:
    """Ensure tool args are a dict."""
    if isinstance(raw_args, dict):
        return raw_args
    return {}


def save_text(path: Path, content: str) -> None:
    """Save text to file."""
    path.write_text(content, encoding="utf-8")


@dataclass
class ToolResult:
    """Standardized tool result."""
    name: str
    artifact_paths: list[str]
    text: str


def normalize_tool_return(tool_name: str, result: Any) -> ToolResult:
    """Normalize various tool return types to ToolResult."""
    if isinstance(result, ToolResult):
        return result

    if isinstance(result, str):
        return ToolResult(name=tool_name, artifact_paths=[], text=result)

    if isinstance(result, dict):
        text = str(result.get("text", ""))
        artifact_paths = result.get("artifact_paths", []) or []
        if not isinstance(artifact_paths, list):
            artifact_paths = [str(artifact_paths)]
        return ToolResult(
            name=tool_name, artifact_paths=[str(p) for p in artifact_paths], text=text
        )

    return ToolResult(name=tool_name, artifact_paths=[], text=str(result))


def format_tool_arg_hints(tools: Dict[str, Callable], allowed_tools: list[str]) -> str:
    """Build argument guidance from tool signatures."""
    lines: list[str] = []
    for tool_name in allowed_tools:
        fn = tools.get(tool_name)
        if fn is None:
            continue

        required: list[str] = []
        optional: list[str] = []
        try:
            sig = inspect.signature(fn)
            for p in sig.parameters.values():
                if p.name in {"df", "kwargs"}:
                    continue
                if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                    continue
                if p.default is inspect.Parameter.empty:
                    required.append(p.name)
                else:
                    optional.append(p.name)
        except (TypeError, ValueError):
            lines.append(f"- {tool_name}: args unknown")
            continue

        if required and optional:
            lines.append(f"- {tool_name}: required={required}; optional={optional}")
        elif required:
            lines.append(f"- {tool_name}: required={required}")
        elif optional:
            lines.append(f"- {tool_name}: optional={optional}")
        else:
            lines.append(f"- {tool_name}: no args")

    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# LangChain Chains
# --------------------------------------------------------------------------------------

def build_router_chain(
    model: Optional[str],
    allowed_tools: list[str],
    tool_arg_hints: str,
    temperature: float = 0.0,
):
    """Build router chain that decides tool vs codegen."""
    llm = create_llm(model=model, temperature=temperature)
    
    tool_list = "\n".join([f"- {t}: {TOOL_DESCRIPTIONS.get(t, '')}" for t in allowed_tools])
    
    system_text = dedent(f"""
    You are a TOOL ROUTER for a data analysis CLI.
    
    Available tools:
    {tool_list}
    
    Tool signatures:
    {tool_arg_hints}
    
    Routing rules:
    1) Does a tool clearly satisfy the request? → mode="tool"
    2) Otherwise → mode="codegen"
    3) If mode="tool": pick exact tool name, extract valid column names
    4) Use correct parameter names from tool signatures
    
    Return ONLY valid JSON in ONE of these forms:
    
    For tool mode:
    {{"mode": "tool", "tool": "tool_name", "args": {{"param": "value"}}, "note": "why"}}
    
    For codegen mode:
    {{"mode": "codegen", "code_request": "specific coding task", "note": "why"}}
    """)

    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_text),
        ("human", "Dataset schema:\n{{schema_text}}\n\nUser request:\n{{user_request}}"),
    ])
    
    return prompt | llm | StrOutputParser()


def build_codegen_chain(model: Optional[str], temperature: float = 0.2):
    """Build code generation chain."""
    llm = create_llm(model=model, temperature=temperature)
    
    system_text = (
        "You are a careful Python data analysis code generator.\n"
        "IMPORTANT:\n"
        "- ONLY use columns from the schema\n"
        "- Produce ONE standalone Python script\n"
        "- The script MUST use argparse with --data and --report_dir\n"
        "- Read CSV at --data with pandas\n"
        "- Handle missing values\n"
        "- Save at least ONE artifact to --report_dir\n\n"
        "OUTPUT FORMAT:\n"
        "PLAN:\n- ...\n\n"
        "CODE:\n```python\n# full script\n```\n\n"
        "VERIFY:\n- ..."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_text),
        ("human", "Dataset schema:\n{{schema_text}}\n\nUser request:\n{{user_request}}"),
    ])
    
    return prompt | llm | StrOutputParser()


def build_summarize_chain(model: Optional[str], temperature: float = 0.2):
    """Build results summarizer chain."""
    llm = create_llm(model=model, temperature=temperature)
    
    system_text = (
        "You explain data analysis results clearly.\n"
        "Given a request and results:\n"
        "1) What we did (1-2 sentences)\n"
        "2) Key findings (bullets)\n"
        "3) Interpretation (plain language)\n"
        "4) Caveats (bullets)\n"
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_text),
        ("human", "User request:\n{{user_request}}\n\nResults:\n{{results}}"),
    ])
    
    return prompt | llm | StrOutputParser()


# --------------------------------------------------------------------------------------
# Core execution functions with Langfuse tracing
# --------------------------------------------------------------------------------------

@observe(name="execute_tool")
def run_tool(
    tool_name: str,
    tool_fn: Callable,
    df: pd.DataFrame,
    tool_args: Dict[str, Any],
    report_dir: Path,
) -> ToolResult:
    """Execute a tool with tracing."""
    # Setup output directories
    tool_output_dir = report_dir / "tool_outputs"
    tool_figure_dir = report_dir / "tool_figures"
    tool_output_dir.mkdir(parents=True, exist_ok=True)
    tool_figure_dir.mkdir(parents=True, exist_ok=True)
    
    # Check signature for dir injection
    sig = inspect.signature(tool_fn)
    params = sig.parameters
    
    # Inject figure/output dirs if supported
    for param_name in ["fig_dir", "figure_dir", "plots_dir", "plot_dir"]:
        if param_name in params and param_name not in tool_args:
            tool_args[param_name] = tool_figure_dir
    
    for param_name in ["out_dir", "output_dir", "artifact_dir"]:
        if param_name in params and param_name not in tool_args:
            tool_args[param_name] = tool_output_dir
    
    # Execute
    print(f"\nRunning tool: {tool_name}")
    result = tool_fn(df, **tool_args)
    
    normalized = normalize_tool_return(tool_name, result)
    
    # Save text output
    out_file = tool_output_dir / f"{tool_name}_output.txt"
    save_text(out_file, normalized.text)
    print(f"Saved output to: {out_file}")
    
    return normalized


@observe(name="execute_generated_script")
def run_generated_script(
    script_path: Path, data_path: Path, report_dir: Path, timeout_s: int = 60
) -> subprocess.CompletedProcess:
    """Execute generated script via subprocess with tracing."""
    cmd = [
        sys.executable,
        str(script_path),
        "--data", str(data_path),
        "--report_dir", str(report_dir),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)


def do_codegen(
    request: str,
    codegen_chain,
    schema_text: str,
    script_path: Path,
    stream: bool = False,
) -> bool:
    """Generate code and ask for approval."""
    print(f"\n=== CODE GENERATION ===")
    print(f"Request: {request}")
    
    # Generate code
    response = codegen_chain.invoke({
        "schema_text": schema_text,
        "user_request": request,
    })
    
    # Extract sections
    plan, code_section, verify = split_sections(response)
    code = extract_python_code(response)
    
    if not code:
        print("ERROR: No Python code found in response")
        print("Raw response:", response[:500])
        return False
    
    # Show plan and verify
    print("\n--- PLAN ---")
    print(plan if plan else "(No plan section)")
    
    print("\n--- GENERATED CODE ---")
    print(code[:1000] + "..." if len(code) > 1000 else code)
    
    print("\n--- VERIFICATION ---")
    print(verify if verify else "(No verify section)")
    
    # HITL: Ask for approval
    print("\n" + "="*50)
    confirm = input("Approve and save this code? (y/n): ").strip().lower()
    
    if confirm == "y":
        save_text(script_path, code)
        print(f"✓ Code saved to: {script_path}")
        print("Type 'run' to execute the approved code")
        return True
    else:
        print("✗ Code not approved")
        return False


def do_execute(
    script_path: Path,
    data_path: Path,
    report_dir: Path,
    timeout_s: int = 60,
) -> bool:
    """Execute approved code."""
    if not script_path.exists():
        print("ERROR: No approved script found. Use 'code' or 'ask' first.")
        return False
    
    print(f"\n=== EXECUTING APPROVED CODE ===")
    print(f"Script: {script_path.name}")
    
    # HITL: Confirm execution
    confirm = input("Execute now? (y/n): ").strip().lower()
    if confirm != "y":
        print("Execution cancelled")
        return False
    
    try:
        result = run_generated_script(script_path, data_path, report_dir, timeout_s)
        
        # Save execution log
        log_path = report_dir / "execution_log.txt"
        log_content = f"""=== Execution Log ===
Return code: {result.returncode}

=== STDOUT ===
{result.stdout}

=== STDERR ===
{result.stderr}
"""
        save_text(log_path, log_content)
        print(f"✓ Execution complete (return code: {result.returncode})")
        print(f"✓ Log saved to: {log_path}")
        
        if result.returncode != 0:
            print("WARNING: Script returned non-zero exit code")
            print("STDERR:", result.stderr[:500])
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print(f"ERROR: Script timed out after {timeout_s} seconds")
        return False
    except Exception as e:
        print(f"ERROR: Execution failed: {e}")
        return False


def do_tool_run(
    request: str,
    router_chain,
    summarize_chain,
    tools: Dict[str, Callable],
    allowed_tools: list[str],
    df: pd.DataFrame,
    df_columns: set[str],
    schema_text: str,
    report_dir: Path,
) -> bool:
    """Route to tool and execute."""
    print(f"\n=== TOOL ROUTING ===")
    print(f"Request: {request}")
    
    # Get routing decision
    raw_response = router_chain.invoke({
        "schema_text": schema_text,
        "user_request": request,
    })
    
    plan = parse_json_object(raw_response)
    
    if not plan:
        print("ERROR: Router did not return valid JSON")
        print("Raw response:", raw_response[:500])
        return False
    
    print(f"\nRouter decision:")
    print(json.dumps(plan, indent=2))
    
    mode = plan.get("mode", "").lower()
    
    if mode == "codegen":
        print("\n→ Router decided: CODE GENERATION")
        return False  # Signal to fall back to codegen
    
    if mode != "tool":
        print(f"ERROR: Unknown mode '{mode}'")
        return False
    
    tool_name = plan.get("tool")
    tool_args = coerce_tool_args(plan.get("args", {}))
    
    # Validate tool exists
    if tool_name not in tools:
        print(f"ERROR: Tool '{tool_name}' not found")
        print(f"Available: {', '.join(allowed_tools)}")
        return False
    
    # Validate columns
    for key, value in tool_args.items():
        if isinstance(value, str) and value not in df_columns and value not in [
            "fig_dir", "figure_dir", "plots_dir", "plot_dir",
            "out_dir", "output_dir", "artifact_dir", "report_dir"
        ]:
            if value in str(df_columns):  # Might be a column name
                pass  # OK
    
    # HITL: Ask for approval
    print(f"\n→ Router decided: TOOL '{tool_name}'")
    print(f"Arguments: {tool_args}")
    
    confirm = input(f"Run tool '{tool_name}' now? (y/n): ").strip().lower()
    if confirm != "y":
        print("Tool execution cancelled")
        return False
    
    # Execute tool
    try:
        result = run_tool(tool_name, tools[tool_name], df, tool_args, report_dir)
        
        # Generate summary
        print("\n=== RESULTS ===")
        print(result.text[:1000])
        if len(result.text) > 1000:
            print("... (truncated)")
        
        # Get natural language summary
        print("\n=== GENERATING INTERPRETATION ===")
        summary = summarize_chain.invoke({
            "user_request": request,
            "results": result.text,
        })
        print(summary)
        
        return True
        
    except Exception as e:
        print(f"ERROR: Tool execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


# --------------------------------------------------------------------------------------
# Main CLI
# --------------------------------------------------------------------------------------

HELP_TEXT = """
Commands:
  help                Show this help
  schema              Display dataset schema
  ask <request>       Router decides: tool OR codegen
  code <request>      Force code generation
  run                 Execute approved code
  exit                Quit

Examples:
  ask summarize the income column
  ask what is the correlation between age and income
  code create a histogram of ages by income level
  run
"""


def main():
    parser = argparse.ArgumentParser(
        description="Build 3: HITL + Tool Router Agent"
    )
    parser.add_argument("--data", type=str, required=True, help="Path to CSV data file")
    parser.add_argument("--report_dir", type=str, default="reports", help="Output directory")
    parser.add_argument("--model", type=str, default=None, help="Model name (provider-specific)")
    parser.add_argument("--temperature", type=float, default=0.2, help="LLM temperature")
    parser.add_argument("--timeout", type=int, default=60, help="Script execution timeout")
    parser.add_argument("--script", type=str, default="generated_analysis.py", help="Generated script name")
    args = parser.parse_args()
    
    # Setup paths
    data_path = Path(args.data)
    report_dir = Path(args.report_dir)
    script_path = report_dir / args.script
    
    ensure_dirs(report_dir)
    
    # Load data
    print(f"Loading data from: {data_path}")
    df = read_data(data_path)
    profile = basic_profile(df)
    df_columns = set(df.columns)
    schema_text = profile_to_schema_text(profile)
    
    print(f"✓ Loaded {profile['n_rows']} rows, {profile['n_cols']} columns")
    print(f"✓ Provider: {get_provider_name()}")
    print(f"✓ Langfuse: {'ENABLED' if LANGFUSE_AVAILABLE else 'DISABLED'}")
    
    # Load tools
    tools = TOOLS
    allowed_tools = sorted(tools.keys())
    tool_arg_hints = format_tool_arg_hints(tools, allowed_tools)
    
    print(f"✓ Tools loaded: {', '.join(allowed_tools)}")
    print("\n" + "="*50)
    print("Type 'help' for commands, 'exit' to quit")
    print("="*50 + "\n")
    
    # Build chains
    router_chain = build_router_chain(
        model=args.model,
        allowed_tools=allowed_tools,
        tool_arg_hints=tool_arg_hints,
        temperature=0.0,
    )
    codegen_chain = build_codegen_chain(
        model=args.model,
        temperature=args.temperature,
    )
    summarize_chain = build_summarize_chain(
        model=args.model,
        temperature=args.temperature,
    )
    
    # State
    approved_code_exists = False
    
    # Main loop
    while True:
        try:
            user_input = input("\n> ").strip()
            if not user_input:
                continue
            
            cmd = user_input.lower().split()[0] if user_input else ""
            arg = user_input[len(cmd):].strip() if len(user_input) > len(cmd) else ""
            
            if cmd == "exit":
                print("Goodbye!")
                break
            
            elif cmd == "help":
                print(HELP_TEXT)
            
            elif cmd == "schema":
                print("\n=== DATASET SCHEMA ===")
                print(schema_text)
            
            elif cmd == "ask":
                if not arg:
                    print("Usage: ask <analysis request>")
                    continue
                
                # Try tool first
                tool_success = do_tool_run(
                    request=arg,
                    router_chain=router_chain,
                    summarize_chain=summarize_chain,
                    tools=tools,
                    allowed_tools=allowed_tools,
                    df=df,
                    df_columns=df_columns,
                    schema_text=schema_text,
                    report_dir=report_dir,
                )
                
                # Fall back to codegen if tool routing returned False
                if not tool_success:
                    print("\n→ Falling back to CODE GENERATION")
                    approved = do_codegen(
                        request=arg,
                        codegen_chain=codegen_chain,
                        schema_text=schema_text,
                        script_path=script_path,
                    )
                    approved_code_exists = approved
            
            elif cmd == "code":
                if not arg:
                    print("Usage: code <analysis request>")
                    continue
                
                approved = do_codegen(
                    request=arg,
                    codegen_chain=codegen_chain,
                    schema_text=schema_text,
                    script_path=script_path,
                )
                approved_code_exists = approved
            
            elif cmd == "run":
                if not script_path.exists():
                    print("No approved code found. Use 'code' or 'ask' first.")
                    continue
                
                do_execute(
                    script_path=script_path,
                    data_path=data_path,
                    report_dir=report_dir,
                    timeout_s=args.timeout,
                )
            
            else:
                print(f"Unknown command: {cmd}")
                print("Type 'help' for available commands")
        
        except KeyboardInterrupt:
            print("\nUse 'exit' to quit")
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
