import subprocess, sys, pathlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = pathlib.Path(r"D:\NJU\softengineering")
SRC = ROOT / "exp2" / "UI界面" / "_src"
OUT = ROOT / "exp2" / "UI界面"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PROFILE = pathlib.Path(r"D:\softeng-env\_edge_profile_ui")

pages = sys.argv[1:] or [f"界面{i:02d}" for i in range(1, 10)]
for name in pages:
    html = SRC / f"{name}.html"
    png = OUT / f"{name}.png"
    if not html.exists():
        print("SKIP", name, "no html")
        continue
    args = [
        EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=2", "--window-size=1440,900",
        f"--user-data-dir={PROFILE}",
        f"--screenshot={png}",
        html.resolve().as_uri(),
    ]
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    size = png.stat().st_size if png.exists() else 0
    print(f"{name}: rc={r.returncode} bytes={size}")
    if r.stderr.strip():
        print("  err:", r.stderr.strip()[:300])
