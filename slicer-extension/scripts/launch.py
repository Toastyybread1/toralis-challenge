"""Run inside Slicer using --python-script, or exec(open(path).read())."""
from pathlib import Path
import qt
import slicer

extension_root = Path(__file__).resolve().parents[1]
module_file = extension_root / "BranchForge" / "BranchForge.py"
factory = slicer.app.moduleManager().factoryManager()
if not hasattr(slicer.modules, "branchforge"):
    factory.registerModule(qt.QFileInfo(str(module_file)))
    factory.loadModules(["BranchForge"])


def open_branchforge():
    slicer.util.selectModule("BranchForge")
    slicer.util.mainWindow().showMaximized()
    widget = slicer.modules.branchforge.widgetRepresentation().self()
    if widget.case_items and widget.scene.ct is None:
        widget.case_combo.setCurrentIndex(1)
        qt.QTimer.singleShot(100, widget.load_study)


qt.QTimer.singleShot(0, open_branchforge)
