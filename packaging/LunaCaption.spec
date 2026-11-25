# Reproducible folder recipe; run through Build-Windows.ps1.
from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).parent
stage = Path(os.environ["LUNACAPTION_BUILD_STAGE"])
datas = [
    (str(stage / "lunacaption-0.1.0.dist-info"), "lunacaption-0.1.0.dist-info"),
    (str(root / "scripts" / "verify_offline.py"), "."),
]
# Transformers builds lazy import maps by reading source files.
datas += collect_data_files("transformers", include_py_files=True)
for package in ("Pillow", "torch", "transformers", "truststore"):
    datas += copy_metadata(package, recursive=True)
hiddenimports = [
    "transformers.models.blip.configuration_blip",
    "transformers.models.blip.processing_blip",
    "transformers.models.blip.image_processing_blip",
    "transformers.models.blip.modeling_blip",
    "transformers.models.blip.modeling_blip_text",
    "transformers.models.bert.tokenization_bert",
    "transformers.models.bert.tokenization_bert_fast",
    "transformers.generation.utils",
    "lunacaption.desktop", "lunacaption.diagnostics", "lunacaption.batch",
    "requests.sessions", "unittest.mock",
]
a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "src")], binaries=[], datas=datas,
    hiddenimports=hiddenimports, hookspath=[], runtime_hooks=[],
    excludes=["pytest", "_pytest", "ruff", "pip", "IPython", "matplotlib",
              "tensorflow", "flax", "jax", "onnx", "onnxruntime"],
    noarchive=False,
)
pyz = PYZ(a.pure)
icon = str(root / "packaging" / "LunaCaption.ico")
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LunaCaption",
          debug=False, strip=False, upx=False, console=False, icon=icon)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="LunaCaption-CLI",
          debug=False, strip=False, upx=False, console=True, icon=icon)
COLLECT(gui, cli, a.binaries, a.datas, strip=False, upx=False, name="LunaCaption")
