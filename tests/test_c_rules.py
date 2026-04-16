from pathlib import Path
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.debug_c import analyze_code # type: ignore

def verify_rule(name, code, expected_bug):
    print(f"Testing {name}...")
    result = analyze_code(code)
    print(f"Status: {result['status']}")
    print(f"Bug Type: {result['bug_type']}")
    print(f"Error Code: {result['error_code']}")
    if result['bug_type'] == expected_bug:
        print("[PASS]")
    else:
        print(f"[FAIL] (Expected: {expected_bug})")
    print("-" * 20)

if __name__ == "__main__":
    # Test 1: Division by zero
    verify_rule("Division By Zero", "int main() { int x = 10 / 0; return 0; }", "division-by-zero")

    # Test 2: Null pointer dereference
    verify_rule("Null Pointer", "int main() { int *p = NULL; *p = 10; return 0; }", "null-pointer-dereference")

    # Test 3: Buffer overflow
    verify_rule("Buffer Overflow", "void f() { char b[10]; strcpy(b, 'too long string'); }", "buffer-overflow")

    # Test 4: Stable system
    verify_rule("Stable System", "int main() { return 0; }", "None")

    # Test 5: Priority (Division by zero should beat Magic number)
    verify_rule("Priority", "int main() { int x = 12345 / 0; return 0; }", "division-by-zero")
