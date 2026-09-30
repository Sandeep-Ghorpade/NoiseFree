# NoiseFree PyInstaller spec
# Builds an onedir Linux bundle containing:
# - NoiseFree application
# - DeepFilterNet Python modules
# - DeepFilterNet3 model
# - libdf native libraries
# - ffmpeg + ffprobe

from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

ROOT = Path.cwd().resolve()
VENV = ROOT / ".venv"
MODEL = Path.home() / ".cache" / "DeepFilterNet" / "DeepFilterNet3"

hiddenimports = []
hiddenimports += collect_submodules("df")
hiddenimports += collect_submodules("libdf")

datas = []
datas += collect_data_files("df")
datas += collect_data_files("libdf")

# Bundle the already-downloaded DeepFilterNet3 model.
datas += [
    (str(MODEL / "config.ini"), "models/DeepFilterNet3"),
    (str(MODEL / "checkpoints" / "model_120.ckpt.best"), "models/DeepFilterNet3/checkpoints"),
]

binaries = []
binaries += collect_dynamic_libs("libdf")

# Bundle FFmpeg tools used by AudioProcessorV4.
binaries += [
    ("/usr/bin/ffmpeg", "."),
    ("/usr/bin/ffprobe", "."),
]

a = Analysis(
    ["app.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NoiseFree",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="NoiseFree",
)
