import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent))

from src.debug_c import analyze_code

def test_c_compilation_error():
    print("\n--- Testing C Compilation Error ---")
    code = """
    #include <stdio.h>
    int main() {
        printf("Hello world") // Missing semicolon
        return 0;
    }
    """
    result = analyze_code(code)
    print(f"Status: {result['status']}")
    print(f"Error Message: {result.get('error_message')}")
    print(f"Bug Type: {result.get('bug_type')}")
    assert result['status'] == "Bug Detected"
    assert "error" in result.get('error_message', '').lower()

def test_c_runtime_error():
    print("\n--- Testing C Runtime Error (Division by Zero) ---")
    # Note: Modern GCC might catch constant division by zero at compile time
    # but let's try a slightly more dynamic one.
    code = """
    #include <stdio.h>
    int main() {
        int x = 5;
        int y = 0;
        int z = x / y;
        printf("%d", z);
        return 0;
    }
    """
    result = analyze_code(code)
    print(f"Status: {result['status']}")
    print(f"Error Message: {result.get('error_message')}")
    print(f"Bug Type: {result.get('bug_type')}")
    print(f"Warnings: {result.get('warnings')}")
    
    # If gcc is available, it should have captured the crash
    if result.get('warnings') and "Compiler" in result['warnings']:
        print("Skipping deeper assertion as compiler is not available.")
    else:
        assert result['status'] == "Bug Detected"
        assert result['bug_type'] in ["division-by-zero", "RuntimeException"]

if __name__ == "__main__":
    try:
        test_c_compilation_error()
        test_c_runtime_error()
        print("\nVerification successful!")
    except Exception as e:
        print(f"\nVerification failed: {e}")
