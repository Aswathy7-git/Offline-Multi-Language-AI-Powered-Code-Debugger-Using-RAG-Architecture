import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agents import DebuggingAgents

async def verify_java_integration():
    print("Testing Java Integration in Multi-Agent Pipeline...")
    agents = DebuggingAgents()
    
    # Java code with Arithmetic Exception
    java_code = """
    public class Calculator {
        public int divide(int a, int b) {
            return a / 0;
        }
    }
    """
    
    # We'll call multi_agent_pipeline directly
    # Note: Even if LLM is None, it should return heuristic results
    report = agents.multi_agent_pipeline(
        error="java.lang.ArithmeticException: / by zero",
        context=java_code,
        knowledge="Standard Java Exceptions",
        language="java"
    )
    
    print(f"Report Status: {report.get('Status')}")
    print(f"Report Bug Type: {report.get('Bug Type')}")
    print(f"Report Explanation: {report.get('Explanation')}")
    
    if report.get('Bug Type') == "arithmetic-exception":
        print("[PASS] Java rule successfully integrated into pipeline.")
    else:
        print(f"[FAIL] Expected arithmetic-exception, got {report.get('Bug Type')}")

if __name__ == "__main__":
    asyncio.run(verify_java_integration())
