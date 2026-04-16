from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .debug_c import analyze_code as analyze_c  # type: ignore
from .debug_java import analyze_code as analyze_java  # type: ignore
from .debug_python import analyze_code as analyze_python  # type: ignore
from backend.config import logger  # type: ignore

try:
    from llama_cpp import Llama  # type: ignore
except ImportError:  # pragma: no cover - environment dependent
    Llama = None

try:
    import radon.metrics as radon_mi  # type: ignore
    from radon.metrics import mi_visit  # type: ignore
except ImportError:  # pragma: no cover - environment dependent
    radon_mi = None


# Force UTF-8 for Windows console support.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class DebuggingAgents:
    def __init__(self, model_path: str = "models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"):
        self.model_path = model_path
        self.llm = None
        self._lock = threading.Lock()  # llama.cpp is NOT thread-safe

        if _env_flag("OFFLINE_DEBUGGER_DISABLE_MODEL"):
            logger.info("Model loading disabled via OFFLINE_DEBUGGER_DISABLE_MODEL.")
            return

        if Llama is None:
            logger.warning("llama-cpp-python is not installed. LLM features are disabled.")
            return

        if not os.path.exists(self.model_path):
            logger.warning("Model not found at %s", self.model_path)
            return

        n_threads = min(os.cpu_count() or 4, 8)
        try:
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=2048,
                n_threads=n_threads,
                n_batch=128,
                verbose=False,
            )
            logger.info("Model loaded on %d threads", n_threads)
        except Exception as exc:  # pragma: no cover - depends on local runtime/GGUF
            self.llm = None
            logger.exception("Failed to initialize model: %s", exc)

    def clean_response(self, text: str, start_phrase: str) -> str:
        """Strict filter to keep output concise and parse-safe."""
        if not text:
            return f"{start_phrase} No response generated."

        sentences = text.split(".")
        short_version = ". ".join(sentences[:2])  # type: ignore

        for stopper in ["A:", "B:", "Analysis:", "Teacher:", "Explanation:", "This solution"]:
            short_version = short_version.split(stopper)[0]

        clean_text = short_version.strip().replace("..", ".")
        if not clean_text.endswith("."):
            clean_text += "."

        return f"{start_phrase} {clean_text}"

    def generate_response(self, prompt: str) -> str:
        if self.llm is None:
            return "Model unavailable."
        try:
            with self._lock:
                llm = self.llm
                if llm is not None:
                    output = llm(
                        prompt,
                        max_tokens=80,
                        temperature=0.0,
                        repeat_penalty=1.7,
                        echo=False,
                    )
                    return output["choices"][0]["text"].strip()
            return "Model generation failed."
        except Exception as exc:  # pragma: no cover - runtime dependent
            return f"Model error: {exc}"

    def multi_agent_pipeline(self, error: str, context: str, knowledge: str, language: str = "python") -> dict[str, Any]:
        """Consolidate analysis/explanation/verification into the user's requested structured format."""
        # Step 0: Rule-Based Heuristic Audit with Strict Gating
        heuristic_res: dict[str, Any] = {}
        language = language.lower()
        # Normalise language alias: "python" -> "py" for internal use
        lang_key = "py" if language == "python" else language

        if lang_key in ("c", "h"):
            heuristic_res = analyze_c(context)
        elif lang_key == "java":
            heuristic_res = analyze_java(context)
        elif lang_key == "py":
            heuristic_res = analyze_python(context)

        if self.llm is None:
            return {
                "Language": language.capitalize(),
                "Status": heuristic_res.get("status", "Bug Detected"),
                "Error Code": heuristic_res.get("error_code"),
                "Bug Type": heuristic_res.get("bug_type", "Unknown"),
                "Explanation": heuristic_res.get("explanation", f"The error is {error}."),
                "Patch Required": heuristic_res.get("patch_required", "Yes"),
                "Fixed Code": context
            }

        start_marker = "STRUCT_START"
        audit_context = f"Error Message: {error}"
        if not error or "no error" in error.lower():
            audit_context = "This is a LOGICAL AUDIT. The code runs without crashing but may have logical flaws."
        
        # Inject heuristic results into the prompt context with strict gating
        heuristic_context = ""
        if heuristic_res and heuristic_res.get("status") == "Bug Detected":
            heuristic_context = (
                f"\n[HEURISTIC AUDIT DETECTED ISSUE]\n"
                f"Status: {heuristic_res.get('status')}\n"
                f"Bug Type: {heuristic_res.get('bug_type')}\n"
                f"Error Code: {heuristic_res.get('error_code')}\n"
                f"Explanation: {heuristic_res.get('explanation')}\n"
                f"Patch Required: Yes\n"
            )
        else:
            heuristic_context = (
                f"\n[HEURISTIC AUDIT: CLEAN]\n"
                f"Status: Stable System\n"
                f"Bug Type: None\n"
                f"Explanation: The code is syntactically correct and no {language.capitalize()} rule violations were detected.\n"
                f"Patch Required: No\n"
            )

        prompt = f"""<|im_start|>system
You are a multi-language code debugger (Python, C, Java).

IMPORTANT:
- Apply STRICT debugging only for Java.
- For Python and C, follow normal debugging behavior (do not over-restrict).

WHEN LANGUAGE = JAVA:
--------------------------------
You must act as a ZERO-TRUST strict analyzer.

Rules:
1. Never assume the code is correct.
2. Always check for compilation errors first.
3. If any issue exists (even minor), mark UNSTABLE.
4. Pay special attention to:
   - Uninitialized variables
   - NullPointerException risks
   - Syntax and compilation errors
   - Incorrect loops or conditions

5. If a variable is declared but not initialized -> ERROR.
6. If compilation would fail -> UNSTABLE immediately.
7. Only mark STABLE if 100% correct.

WHEN LANGUAGE = PYTHON or C:
--------------------------------
- Use normal debugging.
- Do not over-analyze.
- Mark errors only if clearly present.

OUTPUT FORMAT:

STATUS: STABLE or UNSTABLE

ERRORS:
- [Line X]: Description

WARNINGS:
- [Line X]: Description (if any)

FIXED CODE:
<only if issues exist>

FINAL RULE:
- Be strict ONLY for Java.
- Do NOT affect Python and C behavior.
<|im_end|>
<|im_start|>user
Language: {language.capitalize()}
Code:
{context}

{audit_context}
{heuristic_context}

Knowledge Base:
{knowledge}

Final Debugging Report:<|im_end|>
<|im_start|>assistant
STATUS:"""
        raw = self.generate_response(prompt)
        import re
        try:
            if not raw.startswith("STATUS:"):
                raw = "STATUS:" + raw
            
            status_match = re.search(r"STATUS:\s*(STABLE|UNSTABLE)", raw)
            status_val = status_match.group(1) if status_match else "UNSTABLE"
            
            report = {}
            report["Language"] = language.capitalize()
            report["Status"] = "Stable System" if status_val == "STABLE" else "Bug Detected"
            
            errors_match = re.search(r"ERRORS:(.*?)(?:WARNINGS:|FIXED CODE:|$)", raw, re.DOTALL)
            errors = errors_match.group(1).strip() if errors_match else ""
            
            if status_val == "UNSTABLE":
                report["Bug Type"] = heuristic_res.get("bug_type") if heuristic_res and heuristic_res.get("bug_type") else "Unclassified"
                report["Explanation"] = errors if errors else "Bug detected by strict multi-language analyzer."
                report["Patch Required"] = "Yes"
            else:
                report["Bug Type"] = "None"
                report["Explanation"] = "The code is syntactically correct and no violations were detected."
                report["Patch Required"] = "No"

            fixed_code_match = re.search(r"FIXED CODE:(.*?)$", raw, re.DOTALL)
            if fixed_code_match and fixed_code_match.group(1).strip():
                report["Fixed Code"] = fixed_code_match.group(1).strip()
            else:
                report["Fixed Code"] = self.code_fixer_agent(context, error, language)

            # Ensure heuristic findings are preserved if LLM missed them
            if heuristic_res and heuristic_res.get("status") == "Bug Detected" and report.get("Status") == "Stable System":
                 report["Status"] = "Bug Detected"
                 report["Bug Type"] = heuristic_res.get("bug_type")
                 report["Explanation"] = f"[Verified by Heuristic] {heuristic_res.get('explanation')}"
                 report["Patch Required"] = "Yes"

            return report
        except Exception:
            # Fallback to individual agents but still try to preserve structure
            analysis = self.analyzer_agent(error, context)
            explanation = self.explainer_agent(analysis, knowledge)
            return {
                "Language": language.capitalize(),
                "Status": heuristic_res.get("status", "Bug Detected"),
                "Bug Type": heuristic_res.get("bug_type", "Unclassified"),
                "Explanation": heuristic_res.get("explanation", analysis),
                "Patch Required": heuristic_res.get("patch_required", "Yes"),
                "Fixed Code": self.code_fixer_agent(context, error, language)
            }

    def analyzer_agent(self, error: str, context: str) -> str:
        start = "The bug is"
        prompt = (
            f"Code: {context}\n"
            f"Error: {error}\n"
            f"Task: Identify the bug in 15 words or less.\n"
            f"Result: {start}"
        )
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def explainer_agent(self, analysis: str, knowledge: str) -> str:
        start = "Cause:"
        prompt = f"""
        [STRICT reasoning]
        Knowledge: {knowledge}
        Bug: {analysis}
        Task: Explain the root cause in one detailed sentence.
        Result: {start}"""
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def verifier_agent(self, explanation: str) -> str:
        start = "Status:"
        prompt = f"Fix: {explanation}\nTask: Validate this logic. Answer in 5 words.\nResult: {start}"
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def _heuristic_fallback_fix(self, context: str, error: str, language: str = "py") -> str:
        cmt = "//" if language in ("c", "h", "java") else "#"
        error_msg = (error or "").lower()
        # Accept both "py" and "python" as Python language
        lang_is_python = language in ("py", "python")
        if lang_is_python and "zerodivisionerror" in error_msg and "result = num / denom" in context:
            return context.replace(
                "result = num / denom",
                (
                    "if denom != 0:\n"
                    "    result = num / denom\n"
                    "else:\n"
                    "    result = 0\n"
                    "    print('Handled zero denominator safely')"
                ),
            )
        if language == "java" and ("arithmeticexception" in error_msg or "arithmetic-exception" in error_msg) and "result = x / y" in context:
            return context.replace(
                "int result = x / y;",
                (
                    "int result = 0;\n"
                    "        if (y != 0) {\n"
                    "            result = x / y;\n"
                    "        } else {\n"
                    "            System.out.println(\"Warning: Division by zero avoided.\");\n"
                    "        }"
                ),
            )
        if language in ("c", "h") and ("division-by-zero" in error_msg or "division by zero" in error_msg) and "result = a / b" in context:
            return context.replace(
                "int result = a / b;",
                (
                    "int result = (b != 0) ? (a / b) : 0;\n"
                    "    if (b == 0) printf(\"Warning: Division by zero handled safely.\\n\");"
                ),
            )
        if language == "java" and ("string-equality" in error_msg or "string-equality-operator" in error_msg):
            # Replace == comparisons after String declarations with .equals()
            import re as _re
            def _replace_string_eq(m):
                a, b = m.group(1), m.group(2)
                return f"{a}.equals({b})"
            fixed = _re.sub(r'\b([a-zA-Z_]\w*)\s*==\s*([a-zA-Z_]\w*)\b', _replace_string_eq, context)
            if fixed != context:
                return fixed
        return (
            f"{cmt} Auto-fix skipped: model unavailable or low-confidence generation.\n"
            f"{cmt} Original code is preserved below.\n"
            f"{context}"
        )

    def code_fixer_agent(self, context: str, error: str, language: str = "py", attempt: int = 1) -> str:
        """Rewrite script to fix detected error using guarded prompting."""
        if self.llm is None:
            return self._heuristic_fallback_fix(context, error, language)

        retry_tip = ""
        if attempt > 1:
            retry_tip = (
                "\n[CRITIC FEEDBACK] Previous fix failed validation."
                " Simplify logic and avoid security risks."
            )

        audit_instruction = "Identify logical flaws as the code runs but may be incorrect." if not error or "no error" in error.lower() else "Identify the crashing line."
        prompt = f"""<|im_start|>system
You are an expert {language} developer. Fix the bug with minimal, safe edits.
1. {audit_instruction}
2. Apply the smallest valid correction.
3. Keep behavior intact unless required for safety.{retry_tip}
Return ONLY corrected code inside a ```{language} block.<|im_end|>
<|im_start|>user
Buggy Code:
{context}

Error:
{error}

Fixed Code:<|im_end|>
<|im_start|>assistant
```{language}"""

        try:
            with self._lock:
                llm = self.llm
                if llm is not None:
                    output = llm(
                        prompt,
                        max_tokens=1024,
                        temperature=0.01 if attempt == 1 else 0.4,
                        stop=["<|im_end|>", "```"],
                        echo=False,
                    )
                    fixed = output["choices"][0]["text"].strip()
                else:
                    return self._heuristic_fallback_fix(context, error, language)
        except Exception:
            return self._heuristic_fallback_fix(context, error, language)

        if len(fixed) < 10 or fixed.strip() == context.strip():
            return self._heuristic_fallback_fix(context, error, language)
        return fixed

    def researcher_agent(self, error: str, context: str, workspace_files: list[dict[str, Any]], language: str = "py") -> list[str]:
        """Identify relevant files based on imports/error keywords."""
        relevant_files: list[str] = []
        try:
            imports: list[str] = []
            if language == "py":
                tree = ast.parse(context)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for import_node in node.names:
                            if isinstance(import_node.name, str):
                                imports.append(import_node.name)
                    elif isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
                        imports.append(str(node.module))
            else:
                for line in context.splitlines():
                    line = line.strip()
                    if language in ("c", "h") and line.startswith("#include"):
                        inc = line.replace("#include", "").strip(' "<>')
                        imports.append(inc.replace(".h", ""))
                    elif language == "java" and line.startswith("import "):
                        parts = line.split()
                        if len(parts) > 1:
                            imports.append(parts[1].split(".")[-1].replace(";", ""))

            for file_info in workspace_files:
                path = file_info.get("path")
                name = file_info.get("name", "")
                if not isinstance(path, str) or not isinstance(name, str):
                    continue

                module_name = name.replace(".py", "")
                if any(imp and module_name in imp for imp in imports):
                    relevant_files.append(str(path))
                elif any(word in (error or "").lower() for word in module_name.lower().split("_")):
                    relevant_files.append(str(path))
        except Exception:
            return []

        return list(set(relevant_files))[:2]  # type: ignore

    def critic_agent(self, original_code: str, proposed_fix: str, language: str = "py") -> dict[str, Any]:
        """Validate proposed fix for syntax, complexity, and security."""
        try:
            if language == "py":
                ast.parse(proposed_fix)
            elif language in ("c", "h"):
                res = analyze_c(proposed_fix)
                if res.get("error_type") == "CompileError":
                    return {"valid": False, "reason": str(res.get("analysis"))}
            elif language == "java":
                res = analyze_java(proposed_fix)
                if res.get("error_type") == "CompileError":
                    return {"valid": False, "reason": str(res.get("analysis"))}
        except SyntaxError:
            return {"valid": False, "reason": "Syntax error in proposed fix."}

        complexity = self.complexity_agent(proposed_fix, language)
        orig_complexity = self.complexity_agent(original_code, language)
        security = self.security_audit_agent(proposed_fix, language)
        critical_vulnerabilities = [v for v in security.get("issues", []) if v.get("risk") == "CRITICAL"]

        if critical_vulnerabilities:
            return {
                "valid": False,
                "reason": f"Fix introduced critical vulnerability: {critical_vulnerabilities[0]['type']}",
            }
        if complexity["complexity_score"] > 25 and complexity["complexity_score"] > orig_complexity["complexity_score"]:
            return {"valid": False, "reason": "Fix drastically increased code complexity (Cyclomatic > 25)."}

        return {"valid": True, "metrics": {"complexity": complexity, "security": security}}

    async def viper_orchestration(
        self, error: str, context: str, workspace_files: list[dict[str, Any]], language: str = "py"
    ) -> dict[str, Any]:
        """Orchestrated multi-agent loop with research and critique."""
        if self.llm is None:
            return {
                "success": False,
                "fix": "",
                "reason": "LLM unavailable; orchestration skipped.",
                "path_taken": "LLM unavailable fallback",
            }

        relevant_paths = self.researcher_agent(error, context, workspace_files, language)
        augmented_context = context
        cmt = "//" if language in ("c", "h", "java") else "#"
        for path in relevant_paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as file_obj:
                    augmented_context += f"\n\n{cmt} Context from {os.path.basename(path)}:\n" + file_obj.read()
            except OSError:
                continue

        best_fix = ""
        last_reason = None
        for attempt in range(1, 3):
            candidate = self.code_fixer_agent(augmented_context, error, language, attempt)
            report = self.critic_agent(context, candidate, language)
            if report["valid"]:
                return {
                    "success": True,
                    "fix": candidate,
                    "metrics": report["metrics"],
                    "path_taken": f"Orchestrated fix successful on attempt {attempt}",
                }
            last_reason = report["reason"]
            best_fix = candidate

        return {
            "success": False,
            "fix": best_fix,
            "reason": f"Fix candidate failed validation: {last_reason}",
            "path_taken": "Viper fallback (no valid fix found within constraints)",
        }

    def severity_agent(self, error: str) -> str:
        error_lower = (error or "").lower()
        if any(
            token in error_lower
            for token in [
                "segfault", "memoryerror", "zerodivision", "systemerror",
                "recursionerror", "timeout", "stackoverflow", "outofmemory",
                "division-by-zero", "null-pointer", "buffer-overflow"
            ]
        ):
            return "CRITICAL"
        if any(
            token in error_lower
            for token in [
                "typeerror", "valueerror", "indexerror", "keyerror",
                "attributeerror", "nameerror", "nullpointerexception",
                "arithmeticexception", "classcastexception", "string-equality",
                "index-out-of-bounds", "compilation"
            ]
        ):
            return "WARNING"
        return "INFO"

    def complexity_agent(self, code_text: str, language: str = "py") -> dict[str, Any]:
        """AST-based cyclomatic complexity analysis with summary metrics."""
        # Normalise: accept both 'py' and 'python'
        lang_key = "py" if language in ("py", "python") else language
        if lang_key != "py":
            lines = code_text.splitlines()
            loc = len([line for line in lines if line.strip()])
            cmt_char = "//" if lang_key in ("c", "h", "java") else "#"
            comments = len([line for line in lines if line.strip().startswith(cmt_char)])
            return {
                "functions": 0, "classes": 0, "loops": 0, "conditions": 0,
                "complexity_score": 0, "grade": "C", "loc": loc,
                "comments": comments, "top_complex": "N/A",
                "mi_score": None, "mi_grade": None,
            }
        try:
            tree = ast.parse(code_text)
        except SyntaxError:
            return {
                "functions": 0,
                "classes": 0,
                "loops": 0,
                "conditions": 0,
                "complexity_score": 0,
                "grade": "F",
                "loc": 0,
                "comments": 0,
                "top_complex": "N/A",
                "mi_score": None,
                "mi_grade": None,
            }

        functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        loops = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While, ast.AsyncFor)))
        conditions = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.If, ast.Compare, ast.BoolOp)))
        complexity_score = len(functions) + loops + conditions

        lines = code_text.splitlines()
        loc = len([line for line in lines if line.strip()])
        comments = len([line for line in lines if line.strip().startswith("#")])

        top_complex = "N/A"
        if functions:
            def count_complexity(node: ast.AST) -> int:
                return sum(
                    1 for item in ast.walk(node) if isinstance(item, (ast.For, ast.While, ast.If, ast.Compare, ast.BoolOp))
                )

            scored_functions = [(func.name, count_complexity(func)) for func in functions]
            top_complex = max(scored_functions, key=lambda entry: entry[1])[0]

        grade = "A"
        if complexity_score > 30:
            grade = "F"
        elif complexity_score > 20:
            grade = "D"
        elif complexity_score > 10:
            grade = "C"
        elif complexity_score > 5:
            grade = "B"

        radon_data = self.complexity_radon_metrics(code_text)

        return {
            "functions": len(functions),
            "classes": classes,
            "loops": loops,
            "conditions": conditions,
            "complexity_score": complexity_score,
            "grade": grade,
            "loc": loc,
            "comments": comments,
            "top_complex": top_complex,
            "mi_score": radon_data.get("mi_score") if radon_data else None,
            "mi_grade": radon_data.get("mi_grade") if radon_data else None,
        }

    def complexity_radon_metrics(self, code_text: str) -> dict[str, Any] | None:
        """Advanced maintainability metrics using Radon, if installed."""
        if radon_mi is None:
            return None
        try:
            mi_score = radon_mi.mi_visit(code_text, multi=True)
            return {
                "mi_score": round(mi_score, 2),
                "mi_grade": "A" if mi_score > 40 else ("B" if mi_score > 20 else "C"),
            }
        except Exception:
            return None

    def security_bandit_agent(self, code_text: str, language: str = "py") -> list[dict[str, Any]]:
        """Run Bandit if installed; return findings in normalized format."""
        if language != "py":
            return []
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(code_text)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["bandit", "-f", "json", "-q", tmp_path],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=20,
            )
            if not result.stdout.strip():
                return []

            data = json.loads(result.stdout)
            issues: list[dict[str, Any]] = []
            for issue in data.get("results", []):
                issues.append(
                    {
                        "type": issue.get("issue_text"),
                        "risk": issue.get("issue_severity"),
                        "desc": f"{issue.get('issue_text')} (Confidence: {issue.get('issue_confidence')})",
                        "line": issue.get("line_number"),
                    }
                )
            return issues
        except Exception:
            return []

    def security_audit_agent(self, code_text: str, language: str = "py") -> dict[str, Any]:
        """Audit code for common security vulnerabilities."""
        vulnerabilities: list[dict[str, Any]] = []
        lower_text = code_text.lower()
        
        if language in ("c", "h"):
            if "strcpy" in lower_text or "gets(" in lower_text or "sprintf(" in lower_text:
                vulnerabilities.append({"type": "Buffer Overflow", "risk": "CRITICAL", "desc": "Unsafe memory functions used."})
        elif language == "java":
            if "runtime.getruntime().exec" in lower_text or "processbuilder" in lower_text:
                vulnerabilities.append({"type": "Command Injection", "risk": "HIGH", "desc": "Unsafe OS command execution."})

        if "os.system(" in code_text or ("subprocess" in lower_text and "shell=true" in lower_text):
            vulnerabilities.append(
                {
                    "type": "Injection",
                    "risk": "CRITICAL",
                    "desc": "Execution of OS commands with potentially unsafe input.",
                }
            )
        if any(token in lower_text for token in ["api_key =", "secret =", "password =", "token ="]):
            vulnerabilities.append(
                {"type": "Exposure", "risk": "HIGH", "desc": "Potential hardcoded credentials detected."}
            )
        if "yaml.load(" in code_text and "SafeLoader" not in code_text:
            vulnerabilities.append(
                {
                    "type": "Deserialization",
                    "risk": "HIGH",
                    "desc": "Insecure YAML loading can lead to code execution.",
                }
            )
        if "eval(" in code_text or "exec(" in code_text:
            vulnerabilities.append(
                {
                    "type": "Arbitrary Code Execution",
                    "risk": "CRITICAL",
                    "desc": "Use of eval()/exec() with untrusted data.",
                }
            )

        bandit_issues = self.security_bandit_agent(code_text, language)
        if bandit_issues:
            vulnerabilities.extend(bandit_issues)

        return {
            "count": len(vulnerabilities),
            "issues": vulnerabilities,
            "is_secure": len(vulnerabilities) == 0,
            "audit_timestamp": time.time(),
            "engine": "Bandit + Custom Heuristics",
        }

    def confidence_agent(self, error: str, analysis: str, fixed_code: str | None) -> int:
        """Score fix confidence 1-10 using stable heuristics."""
        score = 7
        known_errors = {
            "nameerror",
            "typeerror",
            "valueerror",
            "zerodivisionerror",
            "indexerror",
            "keyerror",
            "syntaxerror",
            "attributeerror",
        }

        error_lower = (error or "").lower()
        analysis_lower = analysis.lower() if analysis else ""
        fixed_text = fixed_code or ""

        if any(token in error_lower for token in known_errors):
            score += 2
        if len(fixed_text.strip()) < 20:
            score -= 4
        if "pass" in fixed_text or "TODO" in fixed_text:
            score -= 2
        if any(token in analysis_lower for token in known_errors):
            score += 1

        return max(1, min(10, score))
