from __future__ import annotations

import subprocess
import tempfile
import re
import shutil
from pathlib import Path
from typing import Any


import json
import os

# Priority list for runtime errors
RUNTIME_PRIORITY = [
    "division-by-zero",
    "null-pointer-dereference",
    "buffer-overflow",
    "use-after-free",
    "memory-leak",
    "undefined-symbol"
]

def safe_output(text: str) -> str:
    """Safely handle Unicode characters for Windows cp1252 compatibility."""
    if not text:
        return ""
    return text.encode('utf-8', errors='replace').decode('utf-8')

def load_c_rules() -> list[dict[str, Any]]:
    """Load C diagnostic rules from the knowledge base."""
    kb_path = Path(__file__).parent.parent / "knowledge_base" / "c_knowledge.json"
    if kb_path.exists():
        try:
            with open(kb_path, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return data.get("diagnostics", [])
        except Exception:
            pass
    return []

def get_rule_patterns() -> dict[str, str]:
    """Define regex patterns for C rules."""
    return {
        "division-by-zero": r"/\s*0(?!\.)",
        "null-pointer-dereference": r"\*\s*NULL|->\s*NULL|=\s*NULL\s*;.*\*\s*[a-zA-Z_]\w*",
        "buffer-overflow": r"strcpy\(|gets\(|sprintf\(|strcat\(",
        "uninitialized-variable": r"(int|char|float|double|long)\s+[a-zA-Z_]\w*\s*;", # Simplified
        "memory-leak": r"malloc\(|calloc\(|realloc\((?!.*free\()", # Heuristic
        "invalid-pointer-arithmetic": r"ptr\s*[+\-]=\s*[a-zA-Z_]", # Very basic
        "dangling-pointer": r"free\([a-zA-Z_]\w*\);\s*[a-zA-Z_]\w*\[",
        "array-index-out-of-bounds": r"\[\s*\d{5,}\s*\]", # Magic number for large index
        "double-free": r"free\s*\(\s*([a-zA-Z_]\w*)\s*\);.*free\s*\(\s*\1\s*\);",
        "invalid-free": r"free\s*\(\s*&",
        "use-after-free": r"free\s*\(\s*([a-zA-Z_]\w*)\s*\);.*\1",
        "stack-overflow": r"void\s+([a-zA-Z_]\w*)\s*\([^)]*\)\s*\{.*\1\s*\(", # Recursion check
        "format-string-vulnerability": r"printf\([a-zA-Z_]\w*\)", # missing format string
        "unused-variable": r"(int|char|float|double)\s+([a-zA-Z_]\w*)\s*;", # Placeholder
        "missing-return": r"(int|char|float|double|long)\s+[a-zA-Z_]\w*\([^)]*\)\s*\{(?![^}]*return)", # Missing return
        "infinite-loop": r"while\s*\(1\)|for\s*\(\s*;\s*;\s*\)",
        "magic-number": r"(?<![\w\.])\d{3,}(?![\w\.])", # 3+ digits
        "long-function": r"\{[^{}]*\{[^{}]*\{[^{}]*\{", # Very rough nesting proxy
        "deep-nesting": r"if\s*\(.*if\s*\(.*if\s*\(.*if\s*\(",
        "missing-braces": r"if\s*\([^)]*\)\s*\n\s*[a-zA-Z_]",
        "multiple-return-statements": r"return.*;.*return",
        "syntax-error-semicolon": r"(?m)^[^;{}\n]+(?<!;)\n\s*(return|printf|if|for|while|int|float|double|char|{)", # Simplified check for missing semicolon before keywords
    }

def analyze_code(code_text: str, file_path: Path | None = None) -> dict[str, Any]:
    """Analyze C code using gcc and rule base."""
    result: dict[str, Any] = {
        "language": "c",
        "status": "Stable System",
        "bug_type": "None",
        "error_code": None,
        "explanation": "The code is syntactically correct and no C rule violations were detected.",
        "patch_required": "No",
        "error_type": None,
        "error_message": None,
        "line_number": None,
        "warnings": None,
        "analysis": "No issues detected.",
        "suggested_fix": None,
    }

    # Step 1: Compilation Check (GCC/CC)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".c", delete=False) as tmp:
        tmp.write(code_text)
        tmp_path = Path(tmp.name)

    compiler = "gcc"
    if shutil.which("gcc") is None:
        if shutil.which("cc") is not None:
            compiler = "cc"
        else:
            result["warnings"] = "Compiler (gcc/cc) not found in PATH. Results may be less accurate (AI/Heuristic fallback active)."
            compiler = None

    if compiler:
        try:
            # Step 1a: Compile to binary
            with tempfile.TemporaryDirectory() as temp_dir:
                executable_path = Path(temp_dir) / "temp.out"
                compile_run = subprocess.run(
                    [compiler, str(tmp_path), "-o", str(executable_path), "-lm"],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=10
                )

                if compile_run.returncode != 0:
                    stderr = compile_run.stderr
                    match = re.search(r":(\d+):\d+: error: (.+)", stderr)
                    if not match:
                        match = re.search(r"(\d+): error: (.+)", stderr)
                    
                    if match:
                        error_msg = match.group(2).strip()
                        result.update({
                            "status": "Bug Detected",
                            "error_message": error_msg,
                            "line_number": int(match.group(1)),
                            "patch_required": "Yes",
                            "error_type": "CompileError",
                            "bug_type": "undefined-symbol" if "undeclared" in error_msg.lower() or "undefined" in error_msg.lower() else "CompilationError",
                            "error_code": "C4001" if "undeclared" in error_msg.lower() or "undefined" in error_msg.lower() else "C0001",
                            "explanation": f"C Compilation failed: {error_msg}"
                        })
                        return result
                
                # Step 1b: Execute binary to catch runtime errors
                if executable_path.exists():
                    try:
                        exec_run = subprocess.run(
                            [str(executable_path)],
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            errors='replace',
                            timeout=5
                        )
                        
                        if exec_run.returncode != 0:
                            stderr = (exec_run.stderr or exec_run.stdout or "").strip()
                            result.update({
                                "status": "Bug Detected",
                                "bug_type": "RuntimeException",
                                "error_message": stderr or f"Process exited with code {exec_run.returncode}",
                                "error_type": "RuntimeError",
                                "explanation": f"Execution crashed: {stderr or 'Unknown crash'}",
                                "patch_required": "Yes"
                            })
                            # Heuristic for common runtime errors
                            if "segmentation fault" in stderr.lower():
                                result["bug_type"] = "null-pointer-dereference"
                                result["error_code"] = "E1002"
                            elif "floating point exception" in stderr.lower():
                                result["bug_type"] = "division-by-zero"
                                result["error_code"] = "E1001"
                            
                            return result
                    except subprocess.TimeoutExpired:
                        result["warnings"] = "Execution timed out."
                    except Exception as e:
                        result["warnings"] = f"Execution error: {str(e)}"

        except subprocess.TimeoutExpired:
            result["warnings"] = "Compilation timed out. Falling back to rules."
        except Exception as e:
            result["warnings"] = f"Internal Exception during compile check: {str(e)}"
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
                except:
                    pass
    else:
        # Compiler not found - cleanup temp file
        if tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except:
                pass

    # Step 2: Rule Matching
    patterns = get_rule_patterns()
    matches: list[dict[str, Any]] = []
    
    # Load rules from KB for metadata (explanation, etc)
    kb_rules = {r.get("name"): r for r in load_c_rules()}

    for rule_name, pattern in patterns.items():
        # Multi-line matching for certain rules
        flags = re.MULTILINE | re.DOTALL if any(word in rule_name for word in ["loop", "nesting", "braces", "return", "syntax"]) else 0
        
        match = re.search(pattern, code_text, flags)
        if match:
            # Use KB rule if available, else create a dummy one
            rule = kb_rules.get(rule_name, {"name": rule_name, "description": f"Potential {rule_name} detected."})
            matches.append(rule)

    if matches:
        # Step 5: Rule Priority
        selected_rule: dict[str, Any] | None = None
        for prioritized_name in RUNTIME_PRIORITY + ["syntax-error-semicolon"]:
            for match in matches:
                if str(match.get("name")) == prioritized_name:
                    selected_rule = match
                    break
            if selected_rule:
                break
        
        if not selected_rule and matches:
            selected_rule = matches[0]

        # Step 3: Classification
        if selected_rule:
            result["status"] = "Bug Detected"
            result["bug_type"] = selected_rule.get("name")
            result["error_code"] = selected_rule.get("error_code") or "C9999"
            result["explanation"] = selected_rule.get("description") or f"Potential {result['bug_type']} detected via heuristic rules."
            result["patch_required"] = "Yes"
            result["analysis"] = result["explanation"]
            result["error_type"] = "RuntimeException" if "syntax" not in result["bug_type"] else "SyntaxError"
            result["error_message"] = selected_rule.get("message_template") or result["explanation"]

    # Step 7: Output format fields are already populated in result
    return result
