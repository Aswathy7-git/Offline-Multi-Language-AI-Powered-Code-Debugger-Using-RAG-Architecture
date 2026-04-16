# Add src to path and handle package structure
import sys
import os
from pathlib import Path

# Add the project root to sys.path
root_dir = os.path.abspath(".")
if root_dir not in sys.path:
    sys.path.append(root_dir)

from src.debug_java import analyze_code
from src.agents import DebuggingAgents

def test_arithmetic_exception():
    print("Testing ArithmeticException detection...")
    code = """
public class Test {
    public static void main(String[] args) {
        int x = 10;
        int y = 0;
        int result = x / y; // BUG
        System.out.println(result);
    }
}
"""
    result = analyze_code(code)
    print(f"Status: {result['status']}")
    print(f"Bug Type: {result['bug_type']}")
    assert result['status'] == "Bug Detected"
    assert result['bug_type'] == "arithmetic-exception"
    
    print("Testing Heuristic Fix...")
    agents = DebuggingAgents()
    # Mock LLM to None if it exists to test fallback
    agents.llm = None
    fix = agents.code_fixer_agent(code, "arithmetic-exception", "java")
    print(f"Fixed Code Preview:\n{fix[:150]}...")
    assert "if (y != 0)" in fix

def test_new_rules():
    print("\nTesting New Rules...")
    test_cases = [
        ("resource-leak", 'Scanner sc = new Scanner(System.in); // No close'),
        ("insecure-random", 'Random r = new Random();'),
        ("empty-catch-block", 'try { } catch (Exception e) { }'),
        ("dead-code", 'if (false) { System.out.println("No"); }')
    ]
    
    for rule_name, code_snippet in test_cases:
        code = f"public class RuleTest {{ public void test() {{ {code_snippet} }} }}"
        result = analyze_code(code)
        print(f"Rule: {rule_name}, Detected: {result['bug_type']}")
        assert result['bug_type'] == rule_name

if __name__ == "__main__":
    try:
        test_arithmetic_exception()
        test_new_rules()
        print("\nAll tests passed!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
