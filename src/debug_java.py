from __future__ import annotations

import subprocess
import tempfile
import re
import os
import shutil
from pathlib import Path
from typing import Any


import json

# Priority list for Java runtime errors
RUNTIME_PRIORITY = [
    "arithmetic-exception",
    "index-out-of-bounds",
    "null-pointer-exception",
    "string-equality-operator",
    "illegal-state-exception",
    "file-not-found"
]

def load_java_rules() -> list[dict[str, Any]]:
    """Load Java diagnostic rules from the knowledge base."""
    kb_path = Path(__file__).parent.parent / "knowledge_base" / "java_knowledge.json"
    if kb_path.exists():
        try:
            with open(kb_path, "r") as f:
                data = json.load(f)
                return data.get("diagnostics", [])
        except Exception:
            pass
    return []

def get_rule_patterns() -> dict[str, str]:
    """Define regex patterns for Java rules."""
    return {
        "illegal-state-exception": r"throw\s+new\s+IllegalStateException\(",
        "file-not-found": r"new\s+File\([^\)]+\)\s*;\s*(?![^;]*exists\(\))", # Heuristic: file created but not checked for existence
        "arithmetic-exception": r"/(?!\s*\d+\.\d+)\s*0(?!\.)|([a-zA-Z_]\w*)\s*=\s*0\s*;.*[a-zA-Z_]\w*\s*/\s*\1|int\s+([a-zA-Z_]\w*)\s*=\s*0\s*;.*[a-zA-Z_]\w*\s*/\s*\2",
        "index-out-of-bounds": r"\[\s*(-?\d+|[a-zA-Z_]\w*\.length\(\))\s*\]|get\(\s*(-?\d+)\s*\)", 
        "null-pointer-exception": r"=\s*null\s*;(?![^;]*if\b).*\.\w+\(|(?<!\w)null\.\w+\(|([a-zA-Z_]\w*)\s*=\s*null\s*;(?!.*if\s*\(\s*\1\s*!=?\s*null\)).*\1\.\w+\(", 
        "illegal-access": r"private\s+.*\b([a-zA-Z_]\w*)\b;.*\b\1\s*=", 
        "unsupported-operation": r"throw\s+new\s+UnsupportedOperationException\(",
        "resource-leak": r"new\s+(FileInputStream|FileOutputStream|FileReader|FileWriter|Scanner)\(.*\)(?!.*\.close\(\))",
        "insecure-random": r"new\s+Random\(\)",
        "empty-catch-block": r"catch\s*\([^)]+\)\s*\{\s*\}",
        "dead-code": r"if\s*\(\s*(false|true\s*==\s*false)\s*\)\s*\{|while\s*\(\s*false\s*\)\s*\{",
        "concurrent-modification": r"for\s*\([^)]+\)\s*\{[^{}]*list\.remove\(",
        "serialization-error": r"class\s+[a-zA-Z_]\w*\s+implements\s+Serializable\s*\{(?![^}]*serialVersionUID)",
        "invalid-thread-state": r"thread\.start\(\);.*thread\.start\(\)", # Double start
        "redundant-import": r"import\s+([a-zA-Z0-9.]+);.*import\s+\1;",
        "unused-exception": r"catch\s*\([^)]+\s+([a-zA-Z_]\w*)\)\s*\{(?![^}]*\1)", # Catch block doesn't use the exception variable
        "redundant-cast": r"\(\w+\)\s*\w+\.toString\(\)", # Heuristic: casting a string to something already string
        "unused-constructor": r"private\s+[a-zA-Z_]\w*\s*\(\)\s*\{", # Private empty constructor
        "duplicate-case-label": r"case\s+(\w+):.*case\s+\1:",
        "empty-finally-block": r"finally\s*\{\s*\}",
        "unreachable-code": r"return.*;.*\n\s*[a-zA-Z_]",
        "redundant-boolean": r"==\s*true|==\s*false",
        "unused-loop-variable": r"for\s*\(int\s+([a-zA-Z_]\w*)\s*=.*\}\s*(?![^}]*\1)",
        "empty-loop": r"for\s*\([^)]*\)\s*\{\s*\}|while\s*\([^)]*\)\s*\{\s*\}",
        "large-class": r"class\s+[a-zA-Z_]\w*\s*\{[^{}]*\{[^{}]*\{[^{}]*\{[^{}]*\{[^{}]*\{", # Complexity proxy
        "high-cyclomatic-complexity": r"if\s*\(.*if\s*\(.*if\s*\(.*if\s*\(",
        "excessive-parameters": r"\(\s*\w+\s+\w+\s*(,\s*\w+\s+\w+\s*){5,}\)", # 6+ parameters
        "hard-coded-path": r"\"[a-zA-Z]:\\\\|/home/|/usr/local/", # Windows or Linux paths
        "long-switch-statement": r"switch\s*\([^)]*\)\s*\{(\s*case[^:]+:){10,}", # 10+ cases
        # Detects any == comparison involving at least one string — variable or literal.
        # Classic Java bug: String a = ...; if (a == b) should use .equals()
        "string-equality-operator": r'(?:"[^"]*"\s*==\s*[a-zA-Z_]\w*|[a-zA-Z_]\w*\s*==\s*"[^"]*"|(?:String\s+[a-zA-Z_]\w*\s*=|new\s+String\s*\()[\s\S]{0,200}?\b([a-zA-Z_]\w*)\s*==\s*([a-zA-Z_]\w*))',
        "synchronized-method-overuse": r"synchronized\s+public",
        "nested-try-block": r"try\s*\{[^{}]*try\s*\{",
        "long-lambda-expression": r"->\s*\{[^{}]*;[^{}]*;[^{}]*;[^{}]*;[^{}]*\}", # 5+ statements in lambda
        "overuse-of-static": r"(static\s+.*\b[a-zA-Z_]\w*\b\s*[=;].*){10,}", # 10+ statics
    }


def analyze_code(code_text: str, file_path: Path | None = None) -> dict[str, Any]:
    """Analyze Java code using javac and rule base."""
    result: dict[str, Any] = {
        "language": "java",
        "status": "Stable System",
        "bug_type": "None",
        "error_code": None,
        "explanation": "The code is syntactically correct and no Java rule violations were detected.",
        "patch_required": "No",
        "error_type": None,
        "error_message": None,
        "line_number": None,
        "warnings": None,
        "analysis": "No issues detected.",
        "suggested_fix": None,
    }

    # Extract public class name if it exists, otherwise default to Temp
    class_name = "Temp"
    match = re.search(r"public\s+class\s+(\w+)", code_text)
    if match:
        class_name = match.group(1)

    # Step 1: Compilation Check (Javac)
    with tempfile.TemporaryDirectory() as temp_dir:
        java_file = Path(temp_dir) / f"{class_name}.java"
        java_file.write_text(code_text, encoding="utf-8")

        # Skip compilation check if javac is not available
        if shutil.which("javac") is None:
            result["warnings"] = "javac not found in PATH. Falling back to rule-based analysis."
        else:
            try:
                compile_result = subprocess.run(
                    ["javac", str(java_file)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=temp_dir
                )

                if compile_result.returncode != 0:
                    stderr = compile_result.stderr or compile_result.stdout
                    match_err = re.search(rf"{class_name}\.java:(\d+): error: (.+)", stderr)
                    if match_err:
                        result["status"] = "Bug Detected"
                        result["bug_type"] = "CompilationError"
                        result["error_code"] = "J0001"
                        result["error_message"] = match_err.group(2)
                        result["line_number"] = int(match_err.group(1))
                        result["explanation"] = f"Java Compilation failed: {match_err.group(2)}"
                        result["patch_required"] = "Yes"
                        result["error_type"] = "CompileError"
                        return result

            except Exception:
                pass  # Fallback to rule matching

    # Step 2: Rule Matching
    rules = load_java_rules()
    patterns = get_rule_patterns()
    matches: list[dict[str, Any]] = []

    for rule in rules:
        rule_name = str(rule.get("name", ""))
        pattern = patterns.get(rule_name)
        if pattern:
            # Multi-line matching for certain rules
            flags = 0
            if any(word in rule_name for word in ["loop", "modification", "dependency", "class", "switch", "try", "exception"]):
                flags = re.MULTILINE | re.DOTALL
            
            match = re.search(pattern, code_text, flags)
            if match:
                matches.append(rule)

    if matches:
        # Step 5: Rule Priority
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

        # Step 3: Classification
        if selected_rule:
            result["status"] = "Bug Detected"
            result["bug_type"] = selected_rule.get("name")
            result["error_code"] = selected_rule.get("error_code")
            result["explanation"] = selected_rule.get("description")
            result["patch_required"] = "Yes"
            result["analysis"] = selected_rule.get("description")
            result["error_type"] = "RuntimeException"
            result["error_message"] = selected_rule.get("message_template") or selected_rule.get("description")

    return result
