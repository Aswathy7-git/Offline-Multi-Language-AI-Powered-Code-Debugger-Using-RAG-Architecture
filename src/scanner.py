from __future__ import annotations

from pathlib import Path
from typing import Any

from src.scanner_python import PythonScanner  # type: ignore
from src.scanner_c import CScanner  # type: ignore
from src.scanner_java import JavaScanner  # type: ignore


class CodeScanner:
    def __init__(self, project_path: str, scan_cache_ttl_seconds: int = 5):
        self.project_path = project_path
        self.python_scanner = PythonScanner(project_path, scan_cache_ttl_seconds)
        self.c_scanner = CScanner(project_path, scan_cache_ttl_seconds)
        self.java_scanner = JavaScanner(project_path, scan_cache_ttl_seconds)

    def get_context_for_file(self, target_file: str) -> str:
        """Language agnostic file reading."""
        # We can just delegate to python_scanner as the reading logic is identical
        return self.python_scanner.get_context_for_file(target_file)

    def scan_workspace(self, root_dir: str | None = None) -> list[dict[str, Any]]:
        """Combine workspace scans from all supported languages."""
        results = []
        results.extend(self.python_scanner.scan_workspace(root_dir))
        results.extend(self.c_scanner.scan_workspace(root_dir))
        results.extend(self.java_scanner.scan_workspace(root_dir))
        
        # Sort combined results by relative path
        results.sort(key=lambda item: item["rel_path"])
        return results

    def invalidate_scan_cache(self) -> None:
        self.python_scanner.invalidate_scan_cache()
        self.c_scanner.invalidate_scan_cache()
        self.java_scanner.invalidate_scan_cache()
