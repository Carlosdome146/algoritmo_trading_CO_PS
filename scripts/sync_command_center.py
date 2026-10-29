import shutil
import subprocess
from pathlib import Path
from trading_v2.execution.demo_paper_trader import get_mt5_module
from scripts.dashboard_movil import get_dashboard_data, render_markdown

ROOT = Path(".")
gist_id = "58af579d3d6fc1961143e3293d51b40b"
gh_cmd = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"

mt5 = get_mt5_module()
if mt5 and mt5.initialize():
    data = get_dashboard_data(mt5)
    mt5.shutdown()
    md = render_markdown(data)
    md_path = ROOT / "monitor_trading.md"
    md_path.write_text(md, encoding="utf-8")
    print("monitor_trading.md regenerated.")

hist_path = ROOT / "HISTORICO_OPERACIONES.md"
md_path = ROOT / "monitor_trading.md"

# Edit monitor_trading.md
r1 = subprocess.run([gh_cmd, "gist", "edit", gist_id, "--filename", "monitor_trading.md", str(md_path)], capture_output=True, text=True)
print("r1 code:", r1.returncode, r1.stdout.strip(), r1.stderr.strip())

# Edit HISTORICO_OPERACIONES.md
r2 = subprocess.run([gh_cmd, "gist", "edit", gist_id, "--filename", "HISTORICO_OPERACIONES.md", str(hist_path)], capture_output=True, text=True)
print("r2 code:", r2.returncode, r2.stdout.strip(), r2.stderr.strip())

print(f"Gist synced: https://gist.github.com/julio7gil/{gist_id}")
