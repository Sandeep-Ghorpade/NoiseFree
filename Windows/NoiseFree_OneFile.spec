from pathlib import Path
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

ROOT = Path.cwd().resolve()

hiddenimports = []
hiddenimports += collect_submodules("df")
hiddenimports += collect_submodules("libdf")
hiddenimports += [
    "soundfile",
]

datas = []
datas += collect_data_files("df")
datas += collect_data_files("libdf")

binaries = []
binaries += collect_dynamic_libs("df")
binaries += collect_dynamic_libs("libdf")

# DeepFilterNet3 model
MODEL = ROOT / "models" / "DeepFilterNet3"

datas += [
    (
        str(MODEL / "config.ini"),
        "models/DeepFilterNet3",
    ),
    (
        str(MODEL / "checkpoints" / "model_120.ckpt.best"),
        "models/DeepFilterNet3/checkpoints",
    ),
]

# Bundled FFmpeg
FFMPEG_DIR = ROOT / "tools" / "bin"

for file in FFMPEG_DIR.iterdir():
    if file.is_file():
        binaries.append(
            (
                str(file),
                "tools/bin",
            )
        )

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
    a.binaries,
    a.datas,
    [],
    name="NoiseFree",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "NoiseFree.png"),
)