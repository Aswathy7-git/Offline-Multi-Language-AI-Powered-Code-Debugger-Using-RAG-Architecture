import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents import DebuggingAgents # type: ignore

async def verify_isolation():
    agents = DebuggingAgents()
    
    test_cases = [
        {
            "name": "Python Bug (Division by Zero)",
            "lang": "python",
            "code": "result = 10 / 0",
            "expected_bug": "ZeroDivisionError"
        },
        {
            "name": "Python Stable",
            "lang": "python",
            "code": "result = 10 / 2",
            "expected_bug": "None"
        },
        {
            "name": "C Bug (Null Pointer)",
            "lang": "c",
            "code": "int *p = NULL; *p = 10;",
            "expected_bug": "null-pointer-dereference"
        },
        {
            "name": "C Stable",
            "lang": "c",
            "code": "int x = 10; return 0;",
            "expected_bug": "None"
        },
        {
            "name": "Java Bug (Index Out of Bounds)",
            "lang": "java",
            "code": "int[] arr = new int[2]; arr[5] = 10;",
            "expected_bug": "index-out-of-bounds"
        },
        {
            "name": "Java Stable",
            "lang": "java",
            "code": "public class Main { public static void main(String[] args) {} }",
            "expected_bug": "None"
        }
    ]

    print("\n--- MULTI-LANGUAGE ISOLATION TEST ---\n")
    
    for case in test_cases:
        print(f"Testing: {case['name']}")
        report = agents.multi_agent_pipeline(
            error="", # Logical audit mode
            context=case['code'],
            knowledge="Test Knowledge",
            language=case['lang']
        )
        
        status = report.get("Status")
        bug_type = report.get("Bug Type")
        
        print(f"  Status: {status}")
        print(f"  Bug Type: {bug_type}")
        
        if bug_type == case['expected_bug']:
            print(f"  ✅ [PASS]")
        elif status == "Stable System" and case['expected_bug'] == "None":
             print(f"  ✅ [PASS]")
        else:
            print(f"  ❌ [FAIL] Expected {case['expected_bug']}, got {bug_type}")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(verify_isolation())
