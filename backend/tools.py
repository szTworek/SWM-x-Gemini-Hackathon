import os
import subprocess
import sys
import httpx
import sympy as sp
import textwrap
import re
import cv2
import numpy as np
from ultralytics import YOLO
from google import genai
from google.genai import types

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

ALLOWED_IMPORTS = {
    "math", "statistics", "itertools", "functools", "collections",
    "numpy", "sympy", "json", "re", "datetime", "matplotlib", "plt", "pandas", "PIL", "io"
}

# Initialize YOLO model
# Make sure 'best.pt' is in the same directory
try:
    plot_model = YOLO("best.pt")
except Exception as e:
    print(f"Warning: YOLO model 'best.pt' not found. extract_plots will fail until added. Error: {e}")
    plot_model = None

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
    """Runs Python code safely. Automatically handles plots."""
    allowed_list = list(ALLOWED_IMPORTS) + [
        "matplotlib", "numpy", "PIL", "six", "cycler", "dateutil", "kiwisolver", 
        "pyparsing", "packaging", "_io", "abc", "codecs", "collections", "site"
    ]

    forbidden = ["os.", "sys.", "subprocess", "open(", "__import__", "exec(", "eval("]
    for f in forbidden:
        if f in code: return f"Blocked: code contains forbidden phrase '{f}'"

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
        return output or "Code executed successfully."
    except Exception as e:
        return f"Critical sandbox error: {e}"

# ── 4. TOOL: PLOT EXTRACTION (YOLO) ──────────────────────────────

def do_extract_plots(image_bytes: bytes, output_dir: str = "output_plots") -> str:
    """Uses YOLO to detect, crop, and save plots from image bytes."""
    if plot_model is None:
        return "Error: YOLO model 'best.pt' not loaded."
    
    # Decode image from bytes (which were converted from PNG to JPEG in agent.py)
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return "Error: Failed to decode image for extraction."

    os.makedirs(output_dir, exist_ok=True)
    
    # YOUR SPECIFIC THRESHOLDS
    conf_threshold = 0.95
    iou_threshold = 0.5
    
    # Run YOLO inference
    results = plot_model.predict(
        source=img, 
        conf=conf_threshold, 
        iou=iou_threshold, 
        verbose=False
    )
    
    boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes is not None else []
    scores = results[0].boxes.conf.cpu().numpy() if results[0].boxes is not None else []

    if len(boxes) == 0:
        return "No plots detected with high enough confidence (0.95) in the image."

    saved_files = []
    for i, (box, score) in enumerate(zip(boxes, scores)):
        x1, y1, x2, y2 = map(int, box[:4])
        # Boundary safety
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
        
        crop = img[y1:y2, x1:x2]
        filename = f"extracted_plot_{i}_conf{score:.2f}.jpg"
        path = os.path.join(output_dir, filename)
        cv2.imwrite(path, crop)
        saved_files.append(filename)

    return f"Successfully extracted {len(boxes)} plots: {', '.join(saved_files)}. Check 'output_plots' folder."

def do_digitize_plot(image_bytes: bytes, api_key: str):
    PROMPT = "Extract all data from this chart and return it as CSV. No explanation, no markdown, just raw CSV."
    MODEL = "models/gemini-2.5-flash"

    client = genai.Client(api_key=api_key)

    jpeg_bytes = image_bytes

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
            types.Part.from_text(text=PROMPT),
        ]
    )

    result = response.text
    print(result)

    with open("output.csv", "w", encoding="utf-8") as f:
        f.write(result)
    print("\n💾 Saved to output.csv")
    return result