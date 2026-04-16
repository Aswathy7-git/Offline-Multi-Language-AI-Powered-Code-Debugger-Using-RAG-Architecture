from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from typing import Any


import json
import re

# Priority list for Python runtime errors
RUNTIME_PRIORITY = [
    "ZeroDivisionError",
    "IndexError",
    "KeyError",
    "TypeError",
    "AttributeError",
    "NameError"
]

def load_python_rules() -> list[dict[str, Any]]:
    """Load Python diagnostic rules from the knowledge base."""
    # We'll use a mix of kb.json and pylint_knowledge.json
    kb_path = Path(__file__).parent.parent / "knowledge_base" / "kb.json"
    pylint_path = Path(__file__).parent.parent / "knowledge_base" / "pylint_knowledge.json"
    
    rules = []
    if kb_path.exists():
        try:
            with open(kb_path, "r") as f:
                data = json.load(f)
                core = data.get("core", {})
                for name, info in core.items():
                    info["name"] = name
                    rules.append(info)
        except Exception:
            pass
            
    if pylint_path.exists():
        try:
            with open(pylint_path, "r") as f:
                data = json.load(f)
                rules.extend(data)
        except Exception:
            pass
    return rules

def get_rule_patterns() -> dict[str, str]:
    """Define regex patterns for Python rules."""
    return {
        "ZeroDivisionError": r"/\s*0(?!\.)",
        # Only flag very large numeric indices (out-of-bounds risk), not normal dict key accesses
        "IndexError": r"\[\s*\d{5,}\s*\]|get\(\s*\d{5,}\s*\)",
        # Only flag integer keys used directly on dicts (e.g. d[0]), not string-keyed accesses
        "KeyError": r"(?<!\w)\w+\[\s*\d+\s*\](?!\s*=)",
        "TypeError": r"(\d+|['\"][^'\"]*['\"])\s*\+\s*(\d+|['\"][^'\"]*['\"])",
        "AttributeError": r"None\.\w+\(",
        "MutableDefaultArgument": r"def\s+\w+\s*\(.*=\s*(\[\]|\{\})\s*\)",
        "LateBindingClosure": r"lambda\s*:\s*\w+",
        "unreachable": r"(return|raise|break|continue).*\n\s*[a-zA-Z_]",
        "duplicate-key": r"\{\s*['\"]([^'\"]+)['\"]\s*:[^,]+,.*['\"]\\1['\"]\s*:",
        "exec-used": r"\bexec\s*\(",
        "eval-used": r"\beval\s*\(",
    }

def analyze_code(code_text: str, file_path: Path | None = None) -> dict[str, Any]:
    """Analyze Python code using AST and rule base."""
    result: dict[str, Any] = {
        "language": "python",
        "status": "Stable System",
        "bug_type": "None",
        "error_code": None,
        "explanation": "The code executes correctly and no rule violations were detected.",
        "patch_required": "No",
        "error_type": None,
        "error_message": None,
        "line_number": None,
        "warnings": None,
        "analysis": "No issues detected.",
        "suggested_fix": None,
    }

    # 1. Syntax Validation via AST
    try:
        ast.parse(code_text)
    except SyntaxError as e:
        result["status"] = "Bug Detected"
        result["bug_type"] = "SyntaxError"
        result["error_code"] = "P0001"
        result["error_message"] = e.msg
        result["line_number"] = e.lineno
        result["explanation"] = f"Python syntax error on line {e.lineno}: {e.msg}"
        result["patch_required"] = "Yes"
        result["error_type"] = "SyntaxError"
        return result
        
    # 2. Rule Matching
    rules = load_python_rules()
    patterns = get_rule_patterns()
    matches: list[dict[str, Any]] = []

    for rule in rules:
        rule_name = str(rule.get("name", ""))
        pattern = patterns.get(rule_name)
        if pattern:
            match = re.search(pattern, code_text, re.MULTILINE | re.DOTALL)
            if match:
                matches.append(rule)

    if matches:
        selected_rule: dict[str, Any] | None = None
        for prioritized_name in RUNTIME_PRIORITY:
            for match in matches:
                if str(match.get("name")) == prioritized_name:
                    selected_rule = match
                    break
            if selected_rule:
                break
        
        if not selected_rule and matches:
            selected_rule = matches[0]

        if selected_rule:
            result["status"] = "Bug Detected"
            result["bug_type"] = selected_rule.get("name")
            result["error_code"] = selected_rule.get("error_code")
            result["explanation"] = selected_rule.get("description") or selected_rule.get("explanation")
            result["patch_required"] = "Yes"
            result["analysis"] = result["explanation"]
            result["error_type"] = "RuntimeException"
            result["error_message"] = result["explanation"]
            return result

    # 3. Runtime execution if a file path is provided (Fallback/Dynamic)
    if file_path and file_path.exists():
        try:
            exec_result = subprocess.run(
                [sys.executable, str(file_path)],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=5,
                cwd=str(file_path.parent)
            )
            
            if exec_result.returncode != 0:
                stderr = (exec_result.stderr or exec_result.stdout or "").strip()
                lines = stderr.splitlines()
                error_msg = lines[-1] if lines else f"Runtime error"
                
                result["status"] = "Bug Detected"
                result["bug_type"] = "RuntimeError"
                result["error_message"] = error_msg
                result["explanation"] = f"Runtime crash detected: {error_msg}"
                result["patch_required"] = "Yes"
                result["error_type"] = "RuntimeError"
                return result
                
        except Exception:
            pass

    return result
