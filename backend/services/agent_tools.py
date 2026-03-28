import os
import subprocess
import sys
import httpx
import sympy as sp
import textwrap
import asyncio
import re

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

ALLOWED_IMPORTS = {
    "math", "statistics", "itertools", "functools", "collections",
    "numpy", "sympy", "json", "re", "datetime", "matplotlib", "plt", "pandas", "PIL", "io"
}

# ── 1. TOOL: SYMBOLIC MATH (SymPy) ──────────────────────────────

def do_math(expression: str, operation: str) -> str:
    """Performs symbolic operations: diff, integrate, solve, simplify, limit."""
    try:
        x, y, z, t, n = sp.symbols("x y z t n")
        expr = sp.sympify(expression)
        
        ops = {
            "diff": lambda e: sp.diff(e, x),
            "integrate": lambda e: sp.integrate(e, x),
            "solve": lambda e: sp.solve(e, x),
            "simplify": lambda e: sp.simplify(e),
            "limit": lambda e: sp.limit(e, x, 0)
        }
        
        func = ops.get(operation)
        if not func:
            return f"Error: Unknown operation '{operation}'"
            
        result = func(expr)
        return f"Result ({operation}): {result}"
    except Exception as e:
        return f"SymPy Error: {e}"

# ── 2. TOOL: WEB SEARCH (Brave API) ────────────────────────────────────

async def do_web_search(query: str) -> str:
    """Fetches raw text data from the web (titles + snippets)."""
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key: 
        return "Error: BRAVE_API_KEY not found in environment."

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"X-Subscription-Token": api_key, "Accept": "application/json"}
    # Changed search_lang to 'en'
    params = {"q": query, "count": 6, "search_lang": "en"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url, headers=headers, params=params)
            r.raise_for_status()
            data = r.json()
            results = data.get("web", {}).get("results", [])
            
            if not results: return "No search results found."
            
            output = []
            for res in results:
                title = res.get('title', 'No title')
                snippet = res.get('description', 'No description')
                output.append(f"SOURCE: {title}\nCONTENT: {snippet}\n")
            
            return "\n".join(output)
    except Exception as e:
        return f"Search error: {e}"

# ── 3. TOOL: SAFE PYTHON SANDBOX ───────────────────────────────────

def safe_exec(code: str) -> str:
    """Runs Python code. Automatically handles plots and UTF-8 encoding."""
    
    allowed_list = list(ALLOWED_IMPORTS) + [
        "matplotlib", "numpy", "PIL", "six", "cycler", "dateutil", "kiwisolver", 
        "pyparsing", "packaging", "_io", "abc", "codecs", "collections", "site"
    ]

    # Security check
    forbidden = ["os.", "sys.", "subprocess", "open(", "__import__", "exec(", "eval("]
    for f in forbidden:
        if f in code: return f"Blocked: code contains forbidden phrase '{f}'"

    # Wrapper fixing Windows environment and Matplotlib
    header = textwrap.dedent("""
        import sys, io, builtins, matplotlib
        if sys.stdout.encoding != 'utf-8':
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np

        def _mock_show(*args, **kwargs):
            plt.savefig('output_plot.png')
            print("[SYSTEM: Plot has been generated and saved as output_plot.png]")
        plt.show = _mock_show

        allowed_names = set(ALLOWED_LIST_PLACEHOLDER)
        _real_import = builtins.__import__
        def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if level > 0: return _real_import(name, globals, locals, fromlist, level)
            top = name.split('.')[0]
            if top in allowed_names or top in sys.modules:
                return _real_import(name, globals, locals, fromlist, level)
            raise ImportError(f"Import '{name}' is not allowed in this sandbox.")
        builtins.__import__ = _safe_import
    """).replace("ALLOWED_LIST_PLACEHOLDER", str(allowed_list))

    full_script = header + "\n" + textwrap.dedent(code)

    try:
        result = subprocess.run(
            [sys.executable, "-c", full_script],
            capture_output=True, text=True, encoding='utf-8', timeout=20
        )
        
        if result.returncode != 0:
            return f"Code execution error:\n{result.stderr.strip()}"
        
        output = result.stdout.strip()
        if os.path.exists("output_plot.png"):
            output += "\n\n(Success: Graphical file output_plot.png is ready for review)"
            
        return output or "Code executed successfully (no text output)."

    except Exception as e:
        return f"Critical sandbox error: {e}"
