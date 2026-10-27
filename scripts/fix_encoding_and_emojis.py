from pathlib import Path
import re

file_path = Path(r"C:\Users\julix\.gemini\antigravity\scratch\algoritmo_trading_CO_PS\trading_v2\execution\demo_paper_trader.py")
content = file_path.read_text(encoding="utf-8")

# 1. Add stdout reconfiguration near top of file
reconfig_code = """import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass
"""

if 'sys.stdout.reconfigure' not in content:
    content = content.replace("from __future__ import annotations\n", "from __future__ import annotations\n" + reconfig_code, 1)

# 2. Fix _default_log to be bulletproof against UnicodeEncodeError
old_log = 'self.log = logger or (lambda msg: print(f"[{datetime.now(timezone.utc).strftime(\'%H:%M:%S UTC\')}] {msg}"))'
new_log = '''def _safe_print(m: str) -> None:
            ts = datetime.now(timezone.utc).strftime('%H:%M:%S UTC')
            try:
                print(f"[{ts}] {m}")
            except Exception:
                safe_m = m.encode("ascii", errors="replace").decode("ascii")
                print(f"[{ts}] {safe_m}")
        self.log = logger or _safe_print'''

content = content.replace(old_log, new_log)

# 3. Remove emoji characters that break legacy Windows code pages
content = content.replace("🎯 ", "")
content = content.replace("🛡️ ", "")

file_path.write_text(content, encoding="utf-8")
print("FIX_APPLIED_SUCCESSFULLY")
