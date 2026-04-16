import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.getcwd())
os.environ["OFFLINE_DEBUGGER_WORKSPACE_ROOT"] = os.getcwd()

import app
from backend.schemas import SnippetRequest

async def test_snippet(code, lang="c"):
    print(f"\n--- Testing Snippet ({lang}) ---")
    print(code)
    try:
        req = SnippetRequest(code=code, language=lang, mode="full")
        res = await app.debug_snippet(req)
        print(f"Status Code: 200 (Success)")
        print(f"Result Status: {res.status}")
        print(f"Error: {res.error}")
    except Exception as e:
        print(f"Status Code: 500 (FAILED)")
        print(f"Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

async def main():
    snippets = [
        "int main() { return 0; }", # Healthy
        "int main() { int x = 5 / 0; return 0; }", # Division by zero (static)
        "int main() { printf(\"%d\", undefined_var); return 0; }", # Undefined symbol
        "void f(); int main() { f(); return 0; }", # Linker error (no definition of f)
        "#include <non_existent.h>\nint main() { return 0; }", # Missing header
        "int main() { return invalid_syntax", # Syntax error
        "", # Empty snippet
    ]
    
    for snippet in snippets:
        await test_snippet(snippet)
        
    print("\n--- Testing Case Sensitivity ---")
    await test_snippet("int main() { return 0; }", lang="C")
    await test_snippet("int main() { return 0; }", lang="C++")

if __name__ == "__main__":
    asyncio.run(main())
