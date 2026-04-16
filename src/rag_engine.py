import json
import os

class LocalRAGEngine:
    def __init__(self, data_dir="knowledge_base"):
        self.data_dir = data_dir
        self.kb_data = self._load_json("kb.json")
        self.pylint_data = self._load_json("pylint_knowledge.json")
        self.c_data = self._load_json("c_knowledge.json")
        self.java_data = self._load_json("java_knowledge.json")

    def _load_json(self, filename):
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base_path, self.data_dir, filename)
        
        if os.path.exists(path):
            with open(path, 'r', encoding="utf-8") as f:
                try:
                    return json.load(f)
                except Exception as e:
                    print(f"[WARNING] Could not parse {filename}: {e}")
                    return None
        return None

    def query_docs(self, error_msg: str, language: str = "py") -> str:
        """Matches the detected error against language-specific JSON entries."""
        error_msg_lower = (error_msg or "").lower()
        # Normalise Python alias so both "py" and "python" work
        lang_key = "py" if language in ("py", "python") else language

        # 1. Search Language-Specific KB
        target_kb = None
        if lang_key in ("c", "h"):
            target_kb = self.c_data
        elif lang_key == "java":
            target_kb = self.java_data
        
        if isinstance(target_kb, dict) and "errors" in target_kb:
            errors = target_kb["errors"]
            if isinstance(errors, dict):
                for err_pattern, details in errors.items():
                    if err_pattern.lower() in error_msg_lower:
                        return f"Source: {language}_knowledge.json | {details['explanation']} Suggestion: {details['suggestion']}"

        # 2. Search Generic/Python kb.json
        kb_data = self.kb_data
        if isinstance(kb_data, dict):
            for section in ["core", "secondary"]:
                entries = kb_data.get(section, {})
                if isinstance(entries, dict):
                    for err_name, details in entries.items():
                        if err_name.lower() in error_msg_lower:
                            return f"Source: kb.json | {details['explanation']} Suggestion: {details['suggestion']}"

        # 3. Search pylint_knowledge.json (Python only)
        pylint_data = self.pylint_data
        if lang_key == "py" and isinstance(pylint_data, list):
            for item in pylint_data:
                if isinstance(item, dict):
                    name = item.get("name", "").replace("-", " ")
                    if name != "" and name in error_msg_lower:
                        return f"Source: Pylint Docs | {item['description']}"

        return "No specific local documentation found."
