from pathlib import Path
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.debug_java import analyze_code # type: ignore

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
    # Test 1: Arithmetic exception (Division by zero)
    verify_rule("Arithmetic Exception", "public class Main { public static void main(String[] args) { int x = 10 / 0; } }", "arithmetic-exception")

    # Test 2: Index out of bounds
    verify_rule("Index Out Of Bounds", "public class Main { public static void main(String[] args) { int[] a = new int[5]; a[10000] = 10; } }", "index-out-of-bounds")

    # Test 3: String equality operator
    verify_rule("String Equality", 'public class Main { public static void main(String[] args) { String s = "hi"; if (s == "hi") {} } }', "string-equality-operator")

    # Test 4: Stable system
    verify_rule("Stable System", "public class Main { public static void main(String[] args) { System.out.println('Hello'); } }", "None")

    # Test 5: Priority (Arithmetic beats Concurrent)
    code_priority = """
    public class Main {
        public void test() {
            int x = 10 / 0;
            for (String s : list) {
                list.remove(s);
            }
        }
    }
    """
    test_rule("Priority", code_priority, "arithmetic-exception")
