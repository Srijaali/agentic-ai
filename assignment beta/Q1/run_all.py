"""Run the analysis and optional local document exporters."""
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(root/'calculations.py')],cwd=root,check=True)
for name in ['build_workbook.py','build_report.py']:
    helper=root/'work'/name
    if helper.exists():
        subprocess.run([sys.executable,str(helper)],cwd=root,check=True)
