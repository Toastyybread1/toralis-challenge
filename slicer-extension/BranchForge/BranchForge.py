"""BranchForge: a dedicated Slicer workspace for direct aortic branch discovery."""

import json
import logging
import math
from pathlib import Path
import tempfile
import time

import ctk
import qt
import slicer
import vtk
from slicer.ScriptedLoadableModule import ScriptedLoadableModule, ScriptedLoadableModuleWidget

from BranchForgeLib import ui
from BranchForgeLib.contract import discover_cases, load_prediction, lps_to_ras, save_prediction, validate_prediction
from BranchForgeLib.scene import AORTA_COLOR, BranchScene, COLORS
from BranchForgeLib.integration import detector_paths, detection_arguments
from BranchForgeLib.report import prediction_html
from BranchForgeLib.ar_share import SharingController
from BranchForgeLib.sample import create_sample
from BranchForgeLib.paths import load_path_evidence
from BranchForgeLib.ui import button, card, divider, label

LAYOUT_ID = 814
LAYOUT_XML = """
<layout type="vertical" split="true">
  <item splitSize="650"><view class="vtkMRMLViewNode" singletontag="1">
    <property name="viewlabel" action="default">Anatomy</property>
  </view></item>
  <item splitSize="260"><layout type="horizontal" split="true">
    <item><view class="vtkMRMLSliceNode" singletontag="Red">
      <property name="orientation" action="default">Axial</property>
      <property name="viewlabel" action="default">Axial</property>
    </view></item>
    <item><view class="vtkMRMLSliceNode" singletontag="Yellow">
      <property name="orientation" action="default">Sagittal</property>
      <property name="viewlabel" action="default">Sagittal</property>
    </view></item>
    <item><view class="vtkMRMLSliceNode" singletontag="Green">
      <property name="orientation" action="default">Coronal</property>
      <property name="viewlabel" action="default">Coronal</property>
    </view></item>
  </layout></item>
</layout>
"""
WINDOW_PRESETS = [("Vessels", 700, 220), ("Soft tissue", 400, 50), ("Bone", 1500, 400)]
SLICE_VIEWS = {"Red": ("Axial", "axial"), "Yellow": ("Sagittal", "sagittal"), "Green": ("Coronal", "coronal")}
SHORTCUTS_HELP = "F        fit anatomy\nL        3D only / 3D + slices\n1 2 3    Study / Detect / Display\nN  P     next / previous branch\nCtrl+E   export JSON\nCtrl+I   import JSON"


class BranchForge(ScriptedLoadableModule):
    def __init__(self, parent):
        super().__init__(parent)
        parent.title = "BranchForge"
        parent.categories = ["Vascular Modeling"]
        parent.dependencies = ["Volumes", "Segmentations", "Markups"]
        parent.contributors = ["BranchForge team"]
        parent.helpText = "Load a CT and parent-aorta mask, run your team's detector or import its JSON, and explore origins, seeds, directions and local radii. See the repository README for setup."
        parent.acknowledgementText = "Built for the Toralis Labs challenge using 3D Slicer, VTK, Qt and SimpleITK's physical-coordinate convention."


class BranchForgeWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        super().setup()
        self.scene = BranchScene()
        self.prediction = None
        self.synthetic = False
        self.loaded_case = None
        self.loaded_image = None
        self.loaded_mask = None
        self.workspace_open = False
        self.process = None
        self.run_dir = None
        self.run_log = ""
        self.cancelled = False
        self.started = 0.0
        self.case_items = []
        self.control_widgets = []
        self.workspace_state = None
        self.shortcuts = []
        self.slice_headers = {}
        self.slice_observers = []
        self.toast = None
        self.pulse = None
        self.window_index = 0
        self.settings = qt.QSettings()
        self.repo = Path(__file__).resolve().parents[2]
        self.elapsed_timer = qt.QTimer()
        self.elapsed_timer.setInterval(250)
        self.elapsed_timer.connect("timeout()", self.tick_elapsed)
        self.build_panel()
        self.build_inspector()
        self.build_header()
        self.ar_sharing = SharingController(self)
        self.scene_observer = slicer.mrmlScene.AddObserver(slicer.mrmlScene.StartCloseEvent, self.on_scene_close)
        self.scene_closed_observer = slicer.mrmlScene.AddObserver(slicer.mrmlScene.EndCloseEvent, self.on_scene_closed)
        self.load_local_catalog()
        self.refresh_pipeline_state()
        self.update_actions()

    # ------------------------------------------------------------------ left panel

    def build_panel(self):
        self.panel = qt.QWidget()
        self.panel.setObjectName("BFPanel")
        self.panel.setMinimumWidth(285)
        self.panel.setMaximumWidth(340)
        outer = qt.QVBoxLayout(self.panel)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(10)
        outer.addWidget(label("TORALIS BRANCHSEED CHALLENGE", "BFEyebrow"))
        outer.addWidget(label("Follow the branches.", "BFTitle"))
        outer.addWidget(label("From a CT scan to a map of every direct aortic branch.", "BFSubtitle", True))
        self.workspace_button = button("Open dedicated workspace", self.open_workspace, "primary", "sparkle")
        outer.addWidget(self.workspace_button)
        self.nav = ui.Segmented([("Study", "1"), ("Detect", "2"), ("Display", "3")], self.show_page)
        outer.addWidget(self.nav)
        self.controls_tabs = qt.QStackedWidget()
        self.controls_tabs.connect("currentChanged(int)", self.on_page_changed)
        outer.addWidget(self.controls_tabs, 1)
        self.build_study_page()
        self.build_detect_page()
        self.build_display_page()
        divider(outer)
        self.sample_button = button("Explore synthetic example", self.load_sample, "ghost", "flask", "Generate fictional anatomy with four reference branches to try the interface. Clearly labelled; never a detector result.")
        outer.addWidget(self.sample_button)
        outer.addWidget(label("BranchForge  /  Built on 3D Slicer", "BFFooter"))
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.panel, 1)
        self.control_widgets += [self.case_combo, self.catalog_button, self.image_edit, self.mask_edit, self.case_edit, self.load_button, self.sample_button, self.import_button, self.python_edit, self.pipeline_edit, self.fold_combo]

    def page(self):
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)
        body = qt.QWidget()
        body.setObjectName("BFPage")
        layout = qt.QVBoxLayout(body)
        layout.setContentsMargins(0, 8, 4, 8)
        layout.setSpacing(10)
        scroll.setWidget(body)
        self.controls_tabs.addWidget(scroll)
        return layout

    def build_study_page(self):
        layout = self.page()
        frame, body = card("DATASET", "folder")
        row = qt.QHBoxLayout()
        row.setSpacing(6)
        self.case_combo = qt.QComboBox()
        self.case_combo.setView(qt.QListView())
        self.case_combo.setMinimumWidth(120)
        self.case_combo.setCursor(qt.Qt.PointingHandCursor)
        self.case_combo.connect("currentIndexChanged(int)", self.select_catalog_case)
        row.addWidget(self.case_combo, 1)
        self.catalog_button = button("", self.choose_catalog, "icon", "folder", "Choose a dataset folder containing subject folders.")
        row.addWidget(self.catalog_button)
        body.addLayout(row)
        files = qt.QWidget()
        files_layout = qt.QVBoxLayout(files)
        files_layout.setContentsMargins(0, 4, 0, 0)
        files_layout.setSpacing(6)
        self.image_edit = self.path_input(files_layout, "CT VOLUME", "orig.nii or orig.nii.gz", self.choose_image)
        self.mask_edit = self.path_input(files_layout, "PARENT AORTA MASK", "mask.nii or mask.nii.gz", self.choose_mask)
        files_layout.addWidget(label("CASE ID", "BFEyebrow"))
        self.case_edit = qt.QLineEdit()
        self.case_edit.setPlaceholderText("e.g. subject001")
        self.case_edit.setToolTip("Must match case_id in the pipeline JSON. Applied when Load study is clicked.")
        files_layout.addWidget(self.case_edit)
        self.files_section = ui.Collapsible("Choose files manually", files)
        body.addWidget(self.files_section)
        layout.addWidget(frame)
        self.load_button = button("Load study", self.load_study, "primary", "load", "Load the selected CT and build the aorta surface from its mask.")
        layout.addWidget(self.load_button)
        frame, body = card("ACTIVE STUDY", "scan")
        self.study_case = label("No study loaded", "BFCardValue")
        body.addWidget(self.study_case)
        self.study_info = label("Select a CT and its matching aorta mask.", "BFMonoSmall", True)
        self.study_info.setMinimumHeight(34)
        body.addWidget(self.study_info)
        layout.addWidget(frame)
        layout.addStretch(1)

    def build_detect_page(self):
        layout = self.page()
        frame, body = card("PIPELINE", "link")
        row = qt.QHBoxLayout()
        self.pipeline_pill = ui.Pill("Not connected", "muted")
        row.addWidget(self.pipeline_pill)
        row.addStretch(1)
        body.addLayout(row)
        config = qt.QWidget()
        config_layout = qt.QVBoxLayout(config)
        config_layout.setContentsMargins(0, 4, 0, 0)
        config_layout.setSpacing(6)
        self.python_edit = self.path_input(config_layout, "TEAM'S PYTHON EXECUTABLE", "python.exe or /path/to/python", self.choose_python)
        self.pipeline_edit = self.path_input(config_layout, "DETECTION SCRIPT", "Path to your team's run.py", self.choose_pipeline)
        executable, script = detector_paths(self.repo, str(self.settings.value("BranchForge/Python", "")),
                                            str(self.settings.value("BranchForge/Pipeline", "")))
        self.python_edit.setText(executable)
        self.pipeline_edit.setText(script)
        self.python_edit.connect("textChanged(QString)", self.refresh_pipeline_state)
        self.pipeline_edit.connect("textChanged(QString)", self.refresh_pipeline_state)
        config_layout.addWidget(label("Uses the bundled detector in .venv. Run scripts/setup_environment.py first.\nRuns separately; includes the loaded case ID.", "BFHint", True))
        self.pipeline_section = ui.Collapsible("Connect your team's run.py", config)
        body.addWidget(self.pipeline_section)
        self.fold_combo = qt.QComboBox()
        self.fold_combo.setSizePolicy(qt.QSizePolicy.Ignored, qt.QSizePolicy.Fixed)
        self.fold_combo.setMinimumWidth(0)
        self.fold_combo.addItem("Unseen study - all models")
        for fold in range(19, 24):
            self.fold_combo.addItem(f"Subject {fold:03d} - held-out models")
        body.addWidget(self.fold_combo)
        body.addWidget(label("Subjects 019-023: choose held-out models.\nCase ID does not choose the model fold.", "BFHint", True))
        layout.addWidget(frame)
        run_row = qt.QHBoxLayout()
        run_row.setSpacing(8)
        self.run_button = button("Run detection", self.run_detection, "primary", "play", "Run the connected detector on the loaded study.")
        self.cancel_button = button("Cancel", self.cancel_run, "danger", "stop")
        self.cancel_button.hide()
        run_row.addWidget(self.run_button, 1)
        run_row.addWidget(self.cancel_button)
        layout.addLayout(run_row)
        self.activity = ui.ActivityBar()
        layout.addWidget(self.activity)
        self.import_button = button("Import prediction JSON", self.import_results, "secondary", "import", "Visualize a prediction.json written by the detector.")
        layout.addWidget(self.import_button)
        self.banner = ui.Banner("Ready when you are.", "info")
        self.status = self.banner.text_label
        layout.addWidget(self.banner)
        self.log_button = button("View pipeline log", self.show_log, "link", "log")
        self.log_button.hide()
        layout.addWidget(self.log_button)
        layout.addStretch(1)

    def build_display_page(self):
        layout = self.page()
        frame, body = card("LAYERS", "branch", spacing=0)
        self.aorta_check = self.toggle_row(body, "Parent aorta", "Surface built from the supplied mask", AORTA_COLOR)
        self.origins_check = self.toggle_row(body, "Origins and seeds", "Ostium centres and 5 mm seed points", "amber")
        self.arrows_check = self.toggle_row(body, "Direction arrows", "Initial path into each daughter", "blue")
        self.radii_check = self.toggle_row(body, "Radius rings", "Local lumen radius at the seed", "ivory")
        self.labels_check = self.toggle_row(body, "Branch labels", "Instance IDs beside each origin", "text2")
        layout.addWidget(frame)
        frame, body = card("AORTA OPACITY")
        row = qt.QHBoxLayout()
        row.setSpacing(10)
        self.opacity = qt.QSlider(qt.Qt.Horizontal)
        self.opacity.setRange(5, 100)
        self.opacity.setValue(75)
        self.opacity.setCursor(qt.Qt.PointingHandCursor)
        self.opacity.connect("valueChanged(int)", self.update_visibility)
        row.addWidget(self.opacity, 1)
        self.opacity_value = label("75%", "BFMono")
        self.opacity_value.setFixedWidth(38)
        self.opacity_value.setAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)
        row.addWidget(self.opacity_value)
        body.addLayout(row)
        layout.addWidget(frame)
        frame, body = card("CT WINDOW", "scan")
        self.window_segment = ui.Segmented([(name, None) for name, _, _ in WINDOW_PRESETS], self.change_window, height=32)
        body.addWidget(self.window_segment)
        layout.addWidget(frame)
        frame, body = card("VIEW", "fit")
        row = qt.QHBoxLayout()
        row.setSpacing(8)
        self.fit_button = button("Fit anatomy", self.fit_view, "secondary", "fit", "Frame the whole aorta (F)")
        row.addWidget(self.fit_button, 1)
        self.layout_button = button("3D only", self.toggle_layout, "secondary", "layout3d", "Switch between 3D only and 3D plus three CT planes (L)")
        row.addWidget(self.layout_button, 1)
        body.addLayout(row)
        body.addWidget(label("Drag to orbit. Scroll to zoom the 3D view or move through CT slices. Selecting a branch centres every slice on its opening in the aorta.", "BFHint", True))
        layout.addWidget(frame)
        frame, body = card("SHORTCUTS", "keyboard")
        body.addWidget(label(SHORTCUTS_HELP, "BFShortcuts"))
        layout.addWidget(frame)
        layout.addStretch(1)

    def path_input(self, layout, title, placeholder, callback):
        layout.addWidget(label(title, "BFEyebrow"))
        row = qt.QHBoxLayout()
        row.setSpacing(6)
        edit = qt.QLineEdit()
        edit.setMinimumWidth(80)
        edit.setPlaceholderText(placeholder)
        row.addWidget(edit, 1)
        browse = button("", callback, "icon", "folder", "Browse for " + title.lower())
        self.control_widgets.append(browse)
        row.addWidget(browse)
        layout.addLayout(row)
        return edit

    def toggle_row(self, layout, title, subtitle, swatch):
        row = ui.ToggleRow(title, subtitle, swatch, True, self.update_visibility)
        layout.addWidget(row)
        return row.switch

    # ------------------------------------------------------------------ right inspector

    def build_inspector(self):
        self.inspector_dock = qt.QDockWidget("BranchForge results", slicer.util.mainWindow())
        self.inspector_dock.setObjectName("BFResultsDock")
        self.inspector_dock.setAllowedAreas(qt.Qt.RightDockWidgetArea)
        self.inspector_dock.setFeatures(qt.QDockWidget.NoDockWidgetFeatures)
        self.inspector_dock.setTitleBarWidget(qt.QWidget())
        self.inspector = qt.QWidget()
        self.inspector.setObjectName("BFInspector")
        self.inspector.setMinimumWidth(280)
        self.inspector.setMaximumWidth(350)
        layout = qt.QVBoxLayout(self.inspector)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(label("RESULTS", "BFEyebrow"))
        metrics = qt.QHBoxLayout()
        metrics.setSpacing(12)
        self.count_label = ui.MetricLabel()
        metrics.addWidget(self.count_label)
        metrics.addWidget(label("direct branches\nlinked to the parent aorta", "BFMuted"), 1)
        layout.addLayout(metrics)
        source_row = qt.QHBoxLayout()
        self.source_pill = ui.Pill("Awaiting a prediction", "muted")
        source_row.addWidget(self.source_pill)
        source_row.addStretch(1)
        layout.addLayout(source_row)
        self.sample_warning = qt.QFrame()
        self.sample_warning.setObjectName("BFWarning")
        warning_layout = qt.QHBoxLayout(self.sample_warning)
        warning_layout.setContentsMargins(12, 9, 12, 9)
        warning_layout.setSpacing(10)
        mark = qt.QLabel()
        mark.setPixmap(ui.pixmap("warning", "gold", 16))
        warning_layout.addWidget(mark, 0, qt.Qt.AlignTop)
        warning_layout.addWidget(label("SYNTHETIC EXAMPLE / reference geometry\nNo detection algorithm has been run.", "BFWarningText", True), 1)
        layout.addWidget(self.sample_warning)
        self.sample_warning.hide()
        self.result_nav = ui.Segmented([("Branches", None), ("Details", None), ("JSON", None), ("AR", None)], lambda i: self.tabs.setCurrentIndex(i), height=34)
        layout.addWidget(self.result_nav)
        self.tabs = qt.QStackedWidget()
        self.tabs.connect("currentChanged(int)", lambda i: self.result_nav.set_index(i, notify=False))
        self.tabs.connect("currentChanged(int)", self.on_results_tab_changed)
        layout.addWidget(self.tabs, 1)
        self.build_branches_tab()
        self.build_details_tab()
        report_scroll = qt.QScrollArea()
        report_scroll.setWidgetResizable(True)
        report_scroll.setFrameShape(qt.QFrame.NoFrame)
        report_scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)
        report_page = qt.QWidget()
        report_layout = qt.QVBoxLayout(report_page)
        report_layout.setContentsMargins(0, 0, 0, 0)
        report_layout.addWidget(label("READABLE RESULTS", "BFEyebrow"))
        self.readable_view = qt.QTextBrowser()
        self.readable_view.setObjectName("BFReadable")
        self.readable_view.setOpenExternalLinks(False)
        self.readable_view.setHtml(prediction_html(None))
        self.readable_view.setMinimumHeight(180)
        report_layout.addWidget(self.readable_view, 3)
        report_layout.addWidget(label("RAW JSON  /  ORIGINAL OUTPUT", "BFEyebrow"))
        self.json_view = qt.QPlainTextEdit()
        self.json_view.setObjectName("BFJson")
        self.json_view.setReadOnly(True)
        self.json_view.setMinimumHeight(160)
        self.json_view.setPlaceholderText("Prediction JSON appears here.\n\nPhysical coordinates stay in SimpleITK's LPS convention.")
        report_layout.addWidget(self.json_view, 2)
        report_scroll.setWidget(report_page)
        self.tabs.addWidget(report_scroll)
        self.build_ar_tab()
        self.selection_summary = label("Select a branch. Geometry is in Details.", "BFMuted", True)
        layout.addWidget(self.selection_summary)
        self.export_button = button("Export prediction JSON", self.export_results, "primary", "export", "Save the prediction exactly as received, in SimpleITK physical coordinates (Ctrl+E)")
        layout.addWidget(self.export_button)
        self.nifti_button = button("Export edited .nii", self.export_edited_nifti, "ghost", "export", "Save a new labelmap: 0 background, 1 current aorta, 2 estimated traces outside it. Not a modified CT or full daughter-vessel segmentation. Requires real traced paths.")
        layout.addWidget(self.nifti_button)
        row = qt.QHBoxLayout()
        row.setSpacing(8)
        self.capture_button = button("Save visual check", self.capture_view, "ghost", "camera", "Capture the workspace as a PNG for the required visual checks")
        row.addWidget(self.capture_button, 1)
        self.copy_button = button("Copy JSON", self.copy_results, "ghost", "copy", "Copy the prediction JSON to the clipboard")
        row.addWidget(self.copy_button)
        layout.addLayout(row)
        self.inspector_dock.setMinimumWidth(300)
        self.inspector_dock.setWidget(self.inspector)
        slicer.util.mainWindow().addDockWidget(qt.Qt.RightDockWidgetArea, self.inspector_dock)
        self.inspector_dock.hide()

    def build_ar_tab(self):
        scroll = qt.QScrollArea()
        self.ar_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)
        body = qt.QWidget()
        layout = qt.QVBoxLayout(body)
        layout.setContentsMargins(0, 8, 4, 8)
        layout.setSpacing(10)
        layout.addWidget(label("YOUR ANATOMY. IN YOUR SPACE.", "BFEyebrow"))
        layout.addWidget(label("Share in AR", "BFDetailTitle"))
        self.ar_qr = qt.QLabel()
        self.ar_qr.setAlignment(qt.Qt.AlignCenter)
        layout.addWidget(self.ar_qr)
        self.ar_status = label("Sharing is off. Nothing is uploaded.", "BFHint", True)
        layout.addWidget(self.ar_status)
        layout.addWidget(label("Scan a QR code to open the visible model and markers on your phone, at anatomical size.", "BFHint", True))
        connection_body = qt.QWidget()
        connection_layout = qt.QVBoxLayout(connection_body)
        connection_layout.setContentsMargins(0, 0, 0, 0)
        connection_layout.addWidget(label("VERCEL VIEWER URL", "BFEyebrow"))
        self.ar_url = qt.QLineEdit()
        self.ar_url.setPlaceholderText("https://your-ar-viewer.vercel.app")
        self.ar_url.setText(self.settings.value("BranchForge/ARUrl", ""))
        host_file = self.repo / "slicer-extension" / "ar-host.json"
        if host_file.is_file() and not self.ar_url.text:
            self.ar_url.setText(json.loads(host_file.read_text(encoding="utf-8"))["url"])
        connection_layout.addWidget(self.ar_url)
        connection_layout.addWidget(label("PUBLISHER KEY  /  NEVER IN THE QR", "BFEyebrow"))
        self.ar_key = qt.QLineEdit()
        self.ar_key.setEchoMode(qt.QLineEdit.Password)
        self.ar_key.setPlaceholderText("Publisher key from your website setup")
        key_file = self.repo / "slicer-extension" / "artifacts" / "ar" / "publisher-key.txt"
        if key_file.is_file():
            self.ar_key.setText(key_file.read_text(encoding="utf-8").strip())
        connection_layout.addWidget(self.ar_key)
        self.ar_connection = ui.Collapsible("Website connection settings", connection_body,
                                            expanded=not bool(self.ar_url.text and self.ar_key.text))
        layout.addWidget(self.ar_connection)
        self.ar_consent = qt.QCheckBox("Approved de-identified demo data")
        layout.addWidget(self.ar_consent)
        layout.addWidget(label("Uploads visible surfaces and markers, not CT voxels or study names. Anyone with the QR link can view/save them. Expires in 1 hour. Do not share identifiable patient data.", "BFHint", True))
        self.ar_start = button("Start sharing & show QR", self.start_ar_sharing, "primary")
        layout.addWidget(self.ar_start)
        self.ar_link = None
        self.ar_copy = button("Copy phone link", self.copy_ar_link, "secondary")
        self.ar_copy.setEnabled(False)
        layout.addWidget(self.ar_copy)
        self.ar_stop = button("Stop sharing / revoke link", lambda: self.ar_sharing.stop(), "ghost")
        self.ar_stop.setEnabled(False)
        layout.addWidget(self.ar_stop)
        layout.addWidget(label("Android: live AR with a compatible WebXR browser.\n\niPhone: live webpage + Quick Look AR snapshot. Return to the webpage and reopen AR after changes.\n\nArrows and rings are illustrative markers, not full daughter-vessel surfaces. Downloaded snapshots cannot be revoked.", "BFHint", True))
        layout.addStretch(1)
        scroll.setWidget(body)
        self.tabs.addWidget(scroll)

    def start_ar_sharing(self):
        def start():
            if not self.ar_consent.checked:
                raise ValueError("Confirm that this is de-identified demonstration geometry you are allowed to share.")
            self.ar_sharing.start(self.ar_url.text, self.ar_key.text)
            self.settings.setValue("BranchForge/ARUrl", self.ar_url.text.strip())
        self.guard(start)

    def copy_ar_link(self):
        if self.ar_link:
            slicer.app.clipboard().setText(self.ar_link)
            self.notify("Phone viewing link copied", "success")

    def on_results_tab_changed(self, index):
        # Give the QR space on short/high-DPI screens. JSON actions remain on other tabs.
        for name in ("selection_summary", "export_button", "capture_button", "copy_button"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(index != 3)
        if index == 3 and getattr(self, "ar_link", None):
            qt.QTimer.singleShot(0, lambda: self.ar_scroll.ensureWidgetVisible(self.ar_qr, 0, 8))

    def build_branches_tab(self):
        self.table_stack = qt.QStackedWidget()
        self.table_empty = ui.EmptyState("branch", "Awaiting a prediction", "Run detection or import your team's JSON to list every direct branch here.")
        self.table_stack.addWidget(self.table_empty)
        self.table = qt.QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["BRANCH", "RADIUS  mm"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setIconSize(qt.QSize(10, 10))
        self.table.setMinimumHeight(120)
        self.table.setCursor(qt.Qt.PointingHandCursor)
        self.table.setToolTip("Click to inspect a branch. Double-click to fly the 3D camera to its origin.")
        self.table.connect("itemSelectionChanged()", self.select_branch)
        self.table.connect("cellDoubleClicked(int,int)", self.fly_to_branch)
        self.table_stack.addWidget(self.table)
        self.tabs.addWidget(self.table_stack)

    def build_details_tab(self):
        self.details_stack = qt.QStackedWidget()
        self.details_empty = ui.EmptyState("target", "Select a branch", "Click a row to inspect its origin, seed, direction and radius. The CT slices jump to its opening.")
        self.details_stack.addWidget(self.details_empty)
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarAlwaysOff)
        body = qt.QWidget()
        body.setObjectName("BFPage")
        layout = qt.QVBoxLayout(body)
        layout.setContentsMargins(0, 4, 4, 4)
        layout.setSpacing(8)
        head = qt.QHBoxLayout()
        head.setSpacing(8)
        self.detail_swatch = qt.QLabel()
        self.detail_swatch.setFixedSize(14, 14)
        head.addWidget(self.detail_swatch)
        self.detail_title = label("Select a branch", "BFDetailTitle")
        head.addWidget(self.detail_title)
        head.addStretch(1)
        parent_pill = ui.Pill("aorta", "mint", mono=True)
        parent_pill.setToolTip("parent_instance_id: every daughter links to the supplied aorta")
        head.addWidget(parent_pill)
        layout.addLayout(head)
        frame, card_body = card("ORIGIN  ·  LPS mm", "target")
        self.origin_values = self.triple(card_body)
        layout.addWidget(frame)
        frame, card_body = card("SEED  ·  LPS mm")
        self.seed_values = self.triple(card_body)
        card_body.addWidget(label("Centre of the daughter lumen 5 mm along its path from the origin.", "BFHint", True))
        layout.addWidget(frame)
        frame, card_body = card("DIRECTION  ·  UNIT")
        row = qt.QHBoxLayout()
        row.setSpacing(10)
        self.rose = ui.DirectionRose()
        row.addWidget(self.rose)
        column = qt.QVBoxLayout()
        column.setSpacing(2)
        self.direction_values = []
        for axis in ("x", "y", "z"):
            pair = qt.QHBoxLayout()
            pair.addWidget(label(axis, "BFAxis"))
            value = label("--", "BFMono")
            value.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
            self.direction_values.append(value)
            pair.addWidget(value, 1)
            column.addLayout(pair)
        column.addStretch(1)
        row.addLayout(column, 1)
        card_body.addLayout(row)
        card_body.addWidget(label("Axial rose in radiological view: patient left on the right, posterior at the bottom. The gauge shows the superior / inferior component.", "BFHint", True))
        layout.addWidget(frame)
        frame, card_body = card("RADIUS  ·  AT SEED")
        self.radius_value = label("--", "BFMonoBig")
        card_body.addWidget(self.radius_value)
        self.chord_value = label("", "BFHint", True)
        card_body.addWidget(self.chord_value)
        layout.addWidget(frame)
        actions = qt.QHBoxLayout()
        actions.setSpacing(8)
        self.fly_button = button("Fly to branch", self.fly_to_branch, "secondary", "target", "Glide the 3D camera onto this origin")
        actions.addWidget(self.fly_button, 1)
        self.copy_branch_button = button("Copy branch", self.copy_branch, "ghost", "copy", "Copy this branch's JSON object")
        actions.addWidget(self.copy_branch_button)
        layout.addLayout(actions)
        legend = label("DOT origin + seed    ARROW direction\nRING radius estimate    MINT parent aorta", "BFHint", True)
        legend.setToolTip("Arrow length is illustrative. Rings show radius estimates, not full vessel walls.")
        layout.addWidget(legend)
        layout.addStretch(1)
        body.setMinimumWidth(0)
        scroll.setWidget(body)
        self.details_stack.addWidget(scroll)
        self.tabs.addWidget(self.details_stack)

    def triple(self, layout):
        row = qt.QHBoxLayout()
        row.setSpacing(8)
        values = []
        for axis in ("x", "y", "z"):
            cell = qt.QVBoxLayout()
            cell.setSpacing(1)
            cell.addWidget(label(axis, "BFAxis"))
            value = label("--", "BFMono")
            value.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
            values.append(value)
            cell.addWidget(value)
            row.addLayout(cell, 1)
        layout.addLayout(row)
        return values

    # ------------------------------------------------------------------ header

    def build_header(self):
        self.toolbar = qt.QToolBar("BranchForge", slicer.util.mainWindow())
        self.toolbar.setObjectName("BFTopBar")
        self.toolbar.setMovable(False)
        header = qt.QWidget()
        header.setObjectName("BFHeader")
        header.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Preferred)
        row = qt.QHBoxLayout(header)
        row.setContentsMargins(14, 7, 14, 7)
        row.setSpacing(12)
        mark = qt.QLabel()
        logo = ui._render_svg(self.resourcePath("Icons/BranchForge.svg"), 64)
        logo.setDevicePixelRatio(2.0)
        mark.setPixmap(logo)
        mark.setFixedSize(32, 32)
        row.addWidget(mark)
        brand = qt.QVBoxLayout()
        brand.setSpacing(0)
        brand.addWidget(label("BRANCHFORGE", "BFBrand"))
        brand.addWidget(label("Direct aortic branch discovery", "BFBrandSub"))
        row.addLayout(brand)
        row.addStretch(1)
        self.stepper = ui.Stepper(["Load", "Detect", "Explore"])
        row.addWidget(self.stepper)
        row.addStretch(1)
        self.header_case = ui.Pill("No study loaded", "muted")
        row.addWidget(self.header_case)
        row.addSpacing(4)
        row.addWidget(button("", self.fit_view, "icon", "fit", "Fit anatomy (F)"))
        self.header_layout_button = button("", self.toggle_layout, "icon", "layout3d", "3D only / 3D + slices (L)")
        row.addWidget(self.header_layout_button)
        row.addWidget(button("", self.capture_view, "icon", "camera", "Save visual check (Ctrl+Shift+S)"))
        row.addSpacing(4)
        row.addWidget(button("Back to Slicer", self.close_workspace, "ghost", "back", "Restore the normal Slicer interface"))
        self.toolbar.addWidget(header)
        slicer.util.mainWindow().addToolBar(qt.Qt.TopToolBarArea, self.toolbar)
        self.toolbar.hide()

    # ------------------------------------------------------------------ workspace lifecycle

    def enter(self):
        self.open_workspace()

    def exit(self):
        self.close_workspace()

    def open_workspace(self):
        if self.workspace_open:
            return
        window = slicer.util.mainWindow()
        lm = slicer.app.layoutManager()
        widgets = []
        for widget in window.findChildren(qt.QToolBar):
            if widget != self.toolbar:
                widgets.append((widget, widget.isVisible()))
        for name in ("PanelDockWidget", "DataProbeCollapsibleWidget", "LogoLabel", "ModulePanelTitle", "HelpAndAcknowledgementCollapsibleButton"):
            for widget in slicer.util.findChildren(window, name=name):
                if name != "PanelDockWidget":
                    widgets.append((widget, widget.isVisible()))
        self.workspace_state = {"style": window.styleSheet, "widgets": widgets, "layout": lm.layout, "title": window.windowTitle, "menu": window.menuBar().isVisible(), "status": window.statusBar().isVisible(), "window_state": window.saveState()}
        module_panel = slicer.util.findChild(window, "ModulePanel")
        self.workspace_state["help"] = module_panel.helpAndAcknowledgmentVisible
        slicer.util.setModuleHelpSectionVisible(False)
        slicer.util.setModulePanelTitleVisible(False)
        for widget, visible in widgets:
            widget.hide()
        window.menuBar().hide()
        window.statusBar().hide()
        theme = Path(self.resourcePath("theme.qss")).read_text(encoding="utf-8")
        theme = theme.replace("{icons}", Path(self.resourcePath("Icons")).as_posix())
        window.setStyleSheet(self.workspace_state["style"] + "\n" + theme)
        window.setWindowTitle("BranchForge | Toralis vascular discovery")
        # Persist no theme or startup preferences in the user's Slicer settings.
        lm.layoutLogic().GetLayoutNode().AddLayoutDescription(LAYOUT_ID, LAYOUT_XML)
        lm.setLayout(LAYOUT_ID)
        self.configure_views()
        self.toolbar.show()
        self.inspector_dock.show()
        self.workspace_button.hide()
        self.workspace_open = True
        panel_docks = slicer.util.findChildren(window, name="PanelDockWidget")
        if panel_docks:
            window.resizeDocks([panel_docks[0], self.inspector_dock], [300, 300], qt.Qt.Horizontal)
        self.toast = ui.Toast(lm.viewport())
        self.install_shortcuts()
        self.stepper.start()
        self.workspace_state["annotations"] = self.set_slice_annotations(False)
        self.refresh_states()
        if self.scene.ct:
            qt.QTimer.singleShot(0, self.scene.focus_aorta)

    @staticmethod
    def set_slice_annotations(enabled):
        """Hide Slicer's corner text in slice views while our headers are shown; returns the previous state."""
        try:
            annotations = slicer.modules.DataProbeInstance.infoWidget.sliceAnnotations
            previous = bool(annotations.sliceViewAnnotationsEnabled)
            annotations.sliceViewAnnotationsEnabled = bool(enabled)
            annotations.updateSliceViewFromGUI()
            return previous
        except Exception:
            logging.debug("BranchForge: slice annotations unavailable", exc_info=True)
            return None

    def configure_views(self):
        """Apply the workspace look to the current view nodes. Safe to call again after a scene close."""
        lm = slicer.app.layoutManager()
        if lm.threeDViewCount:
            widget = lm.threeDWidget(0)
            node = widget.mrmlViewNode()
            # These scene view settings are restored (by value) when returning to Slicer.
            if self.workspace_state is not None and "view" not in self.workspace_state:
                self.workspace_state["view"] = (tuple(node.GetBackgroundColor()), tuple(node.GetBackgroundColor2()), node.GetBoxVisible(), node.GetAxisLabelsVisible(), widget.threeDController().isVisible(), node.GetOrientationMarkerType(), node.GetOrientationMarkerSize())
            node.SetBackgroundColor(.027, .043, .071)
            node.SetBackgroundColor2(.075, .11, .16)
            node.SetBoxVisible(False)
            node.SetAxisLabelsVisible(False)
            # The human figure rotates with the camera and tells the viewer at a glance which way the patient faces.
            node.SetOrientationMarkerType(slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeHuman)
            node.SetOrientationMarkerSize(slicer.vtkMRMLAbstractViewNode.OrientationMarkerSizeMedium)
            widget.threeDController().hide()
        for name in lm.sliceViewNames():
            widget = lm.sliceWidget(name)
            if self.workspace_state is not None:
                controls = self.workspace_state.setdefault("slice_controls", {})
                if name not in controls:
                    title, tone = SLICE_VIEWS.get(name, (name, "text2"))
                    heading = ui.SliceHeader(title, tone)
                    widget.layout().insertWidget(0, heading)
                    controls[name] = (widget.sliceController().isVisible(), heading)
                    self.slice_headers[name] = heading
            # Native slice toolbars impose a large minimum width. Scroll navigation
            # remains available in the view itself while our compact headers are shown.
            widget.sliceController().hide()
        self.attach_slice_observers()

    def attach_slice_observers(self):
        """(Re)connect the live offset readouts; slice nodes are replaced when a scene closes."""
        for node, tag in self.slice_observers:
            try:
                node.RemoveObserver(tag)
            except Exception:
                pass
        self.slice_observers = []
        lm = slicer.app.layoutManager()
        for name in lm.sliceViewNames():
            if name in self.slice_headers:
                node = lm.sliceWidget(name).mrmlSliceNode()
                tag = node.AddObserver(vtk.vtkCommand.ModifiedEvent, lambda caller, event, view=name: self.update_slice_header(view))
                self.slice_observers.append((node, tag))
                self.update_slice_header(name)

    def update_slice_header(self, name):
        heading = self.slice_headers.get(name)
        if heading is None:
            return
        node = slicer.app.layoutManager().sliceWidget(name).mrmlSliceNode()
        matrix = node.GetSliceToRAS()
        normal = [matrix.GetElement(i, 2) for i in range(3)]
        axis = max(range(3), key=lambda i: abs(normal[i]))
        letter = ("R", "A", "S")[axis] if normal[axis] > 0 else ("L", "P", "I")[axis]
        heading.set_offset(letter, node.GetSliceOffset())

    def install_shortcuts(self):
        self.remove_shortcuts()
        window = slicer.util.mainWindow()
        bindings = [("F", self.fit_view), ("L", self.toggle_layout), ("1", lambda: self.show_page(0)), ("2", lambda: self.show_page(1)), ("3", lambda: self.show_page(2)), ("N", lambda: self.step_branch(1)), ("P", lambda: self.step_branch(-1)), ("Ctrl+E", self.export_results), ("Ctrl+I", self.import_results), ("Ctrl+Shift+S", self.capture_view)]
        for keys, callback in bindings:
            shortcut = qt.QShortcut(qt.QKeySequence(keys), window)
            shortcut.setContext(qt.Qt.WindowShortcut)
            shortcut.connect("activated()", callback)
            self.shortcuts.append(shortcut)

    def remove_shortcuts(self):
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts = []

    def close_workspace(self):
        if hasattr(self, "ar_sharing") and self.ar_sharing.enabled:
            self.ar_sharing.stop()
        if not self.workspace_open:
            return
        self.workspace_open = False
        state = self.workspace_state
        window = slicer.util.mainWindow()
        self.remove_shortcuts()
        self.stepper.stop()
        if self.toast is not None:
            self.toast.hide()
            self.toast.deleteLater()
            self.toast = None
        for node, tag in self.slice_observers:
            node.RemoveObserver(tag)
        self.slice_observers = []
        self.slice_headers = {}
        if state.get("annotations") is not None:
            self.set_slice_annotations(state["annotations"])
        self.toolbar.hide()
        self.inspector_dock.hide()
        window.setStyleSheet(state["style"])
        window.setWindowTitle(state["title"])
        slicer.util.setModuleHelpSectionVisible(state["help"])
        slicer.util.setModulePanelTitleVisible(True)
        window.restoreState(state["window_state"])
        self.toolbar.hide()
        self.inspector_dock.hide()
        for widget, visible in state["widgets"]:
            widget.setVisible(visible)
        window.menuBar().setVisible(state["menu"])
        window.statusBar().setVisible(state["status"])
        if "view" in state and slicer.app.layoutManager().threeDViewCount:
            bg, bg2, box, axes, controller, marker_type, marker_size = state["view"]
            widget = slicer.app.layoutManager().threeDWidget(0)
            node = widget.mrmlViewNode()
            node.SetBackgroundColor(bg)
            node.SetBackgroundColor2(bg2)
            node.SetBoxVisible(box)
            node.SetAxisLabelsVisible(axes)
            node.SetOrientationMarkerType(marker_type)
            node.SetOrientationMarkerSize(marker_size)
            widget.threeDController().setVisible(controller)
        slicer.app.layoutManager().setLayout(state["layout"])
        for name in slicer.app.layoutManager().sliceViewNames():
            if name in state.get("slice_controls", {}):
                visible, heading = state["slice_controls"][name]
                heading.hide()
                heading.deleteLater()
                slicer.app.layoutManager().sliceWidget(name).sliceController().setVisible(visible)
        self.workspace_button.show()

    # ------------------------------------------------------------------ catalog and files

    def load_local_catalog(self):
        root = self.repo / "TORALIS CHALLENGE"
        if root.is_dir():
            self.set_catalog(root)
        else:
            self.case_combo.addItem("Choose a dataset folder")

    def set_catalog(self, root):
        self.case_items = discover_cases(root)
        self.case_combo.blockSignals(True)
        self.case_combo.clear()
        self.case_combo.addItem(f"Select one of {len(self.case_items)} studies")
        for name, image, mask in self.case_items:
            self.case_combo.addItem(name)
        self.case_combo.blockSignals(False)

    def choose_catalog(self):
        path = qt.QFileDialog.getExistingDirectory(self.parent, "Choose dataset folder", str(self.repo))
        if path:
            self.guard(lambda: self.set_catalog(path))

    def select_catalog_case(self, index):
        if index <= 0 or index > len(self.case_items):
            return
        name, image, mask = self.case_items[index - 1]
        self.image_edit.setText(image)
        self.mask_edit.setText(mask)
        self.case_edit.setText(name)

    def choose_image(self):
        path = qt.QFileDialog.getOpenFileName(self.parent, "Select CT", str(self.repo), "NIfTI volumes (*.nii *.nii.gz)")
        if path:
            self.image_edit.setText(path)
            self.case_edit.setText(Path(path).parent.name)

    def choose_mask(self):
        path = qt.QFileDialog.getOpenFileName(self.parent, "Select aorta mask", str(self.repo), "NIfTI volumes (*.nii *.nii.gz)")
        if path:
            self.mask_edit.setText(path)

    def choose_python(self):
        path = qt.QFileDialog.getOpenFileName(self.parent, "Choose pipeline Python executable", "", "Executables (*)")
        if path:
            self.python_edit.setText(path)

    def choose_pipeline(self):
        path = qt.QFileDialog.getOpenFileName(self.parent, "Choose team detection script", str(self.repo), "Python scripts (*.py)")
        if path:
            self.pipeline_edit.setText(path)

    def refresh_pipeline_state(self, *args):
        if not hasattr(self, "pipeline_pill"):
            return
        executable = self.python_edit.text.strip()
        script = self.pipeline_edit.text.strip()
        if Path(executable).is_file() and Path(script).is_file():
            self.pipeline_pill.setText("Connected  " + Path(script).name, "mint")
        elif executable or script:
            self.pipeline_pill.setText("Incomplete paths", "gold")
        else:
            self.pipeline_pill.setText("Not connected", "muted")

    # ------------------------------------------------------------------ feedback

    def set_status(self, text, kind="info"):
        self.banner.show_message(text, kind)

    def notify(self, text, kind="info", banner=None):
        self.set_status(banner or text, kind)
        if self.toast is not None and self.workspace_open:
            self.toast.show_message(text, kind)

    def guard(self, action):
        try:
            return action()
        except ValueError as exc:
            logging.warning("BranchForge: %s", exc)
            self.notify(str(exc), "error")
            return None
        except Exception as exc:
            logging.exception("BranchForge action failed")
            self.notify(str(exc), "error")
            slicer.util.errorDisplay(str(exc), windowTitle="BranchForge")
            return None

    # ------------------------------------------------------------------ study and results

    def load_study(self):
        self.guard(self._load_study)

    def _load_study(self):
        if self.process:
            raise ValueError("Wait for detection to finish or cancel it before loading a study.")
        image = self.image_edit.text.strip()
        mask = self.mask_edit.text.strip()
        case = self.case_edit.text.strip()
        if not case:
            raise ValueError("Enter a case ID before loading the study.")
        if not Path(image).is_file() or not Path(mask).is_file():
            raise ValueError("Choose an existing CT and its matching aorta mask.")
        self.set_status("Loading CT and building the aorta surface...", "info")
        slicer.app.processEvents()
        qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
        try:
            self.scene.load_case(image, mask)
        finally:
            qt.QApplication.restoreOverrideCursor()
        self.loaded_case, self.loaded_image, self.loaded_mask = case, image, mask
        self.synthetic = False
        self.clear_prediction()
        self.header_case.setText(case.upper(), "mint")
        self.study_case.setText(case)
        size = self.scene.ct.GetImageData().GetDimensions()
        spacing = self.scene.ct.GetSpacing()
        self.study_info.setText(f"{size[0]} x {size[1]} x {size[2]} voxels\nspacing {spacing[0]:.2f} / {spacing[1]:.2f} / {spacing[2]:.2f} mm\naorta mask {self.scene.mask_volume_ml:.1f} mL ({self.scene.mask_voxels:,} voxels)\n{Path(image).name}  +  {Path(mask).name}")
        self.notify(f"{case} loaded", "success", "Study loaded. Run detection or import your team's JSON.")
        self.show_page(1)
        self.update_visibility()
        self.change_window(self.window_index)
        self.update_actions()

    def clear_prediction(self):
        self.prediction = None
        ui.stop(self.pulse)
        self.pulse = None
        self.scene.clear_results()
        self.table.setRowCount(0)
        self.table_stack.setCurrentIndex(0)
        self.table_empty.set_text("Awaiting a prediction", "Run detection or import your team's JSON to list every direct branch here.", "branch")
        self.details_stack.setCurrentIndex(0)
        self.details_empty.set_text("Select a branch", "Click a row to inspect its origin, seed, direction and radius. The CT slices jump to its opening.", "target")
        self.count_label.set_value(None)
        self.json_view.setPlainText("")
        self.readable_view.setHtml(prediction_html(None))
        self.source_pill.setText("Awaiting a prediction", "muted")
        self.sample_warning.hide()
        self.detail_title.setText("Select a branch")
        self.rose.set_direction(None)
        self.selection_summary.setText("Select a branch. Geometry is in Details.")
        self.update_actions()

    def load_sample(self):
        self.guard(self._load_sample)

    def _load_sample(self):
        if self.process:
            raise ValueError("Cancel the active detection before loading the example.")
        self.set_status("Generating synthetic anatomy...", "info")
        slicer.app.processEvents()
        data = create_sample(self.scene)
        self.synthetic = True
        self.loaded_case = "synthetic_demo"
        self.loaded_image = self.loaded_mask = None
        self.header_case.setText("SYNTHETIC EXAMPLE", "amber")
        self.study_case.setText("Synthetic anatomy")
        self.study_info.setText("4 reference branches\ngenerated locally for interface exploration\nnot a detector result")
        self.apply_prediction(data, "Synthetic reference geometry", "amber")
        self.notify("Synthetic example ready", "warning", "Example ready. These are generated reference markers, not detector predictions.")
        self.scene.focus_aorta()
        self.update_actions()

    def import_results(self):
        if not self.scene.ct:
            self.set_status("Load a study before importing its prediction JSON.", "warning")
            return
        path = qt.QFileDialog.getOpenFileName(self.parent, "Import prediction", str(self.repo), "JSON files (*.json)")
        if path:
            self.guard(lambda: self.import_prediction_path(path))

    def import_prediction_path(self, path):
        data = load_prediction(path, self.loaded_case)
        paths, note = load_path_evidence(path, data)
        self.apply_prediction(data, "Imported  " + Path(path).name, "blue", paths, note)
        self.notify(f"Imported {len(data['daughters'])} branches", "success", f"Imported {len(data['daughters'])} branches. Select a row to inspect.")

    def apply_prediction(self, data, source, tone="blue", paths=None, path_note=""):
        data = validate_prediction(data, self.loaded_case)
        if not self.scene.ct:
            raise ValueError("Load the matching study first.")
        ui.stop(self.pulse)
        self.pulse = None
        self.path_evidence = paths or {}
        self.path_note = path_note
        self.scene.render_results(data, self.path_evidence)
        self.prediction = data
        self.source_pill.setText(source, tone)
        self.sample_warning.setVisible(self.synthetic)
        self.count_label.set_value(len(data["daughters"]))
        self.readable_view.setHtml(prediction_html(data, self.synthetic))
        self.json_view.setPlainText(json.dumps(data, indent=2, allow_nan=False))
        self.table.blockSignals(True)
        self.table.setRowCount(len(data["daughters"]))
        for i, branch in enumerate(data["daughters"]):
            rgb = COLORS[i % len(COLORS)]
            name = qt.QTableWidgetItem(qt.QIcon(ui.dot_pixmap(rgb, 10)), branch["instance_id"])
            radius = qt.QTableWidgetItem(f"{branch['radius_mm']:.2f}")
            radius.setTextAlignment(qt.Qt.AlignRight | qt.Qt.AlignVCenter)
            radius.setForeground(qt.QBrush(ui.color("text2")))
            self.table.setItem(i, 0, name)
            self.table.setItem(i, 1, radius)
            self.table.setRowHeight(i, 38)
        self.table.blockSignals(False)
        if data["daughters"]:
            self.table_stack.setCurrentIndex(1)
            self.table.selectRow(0)
        else:
            self.table_stack.setCurrentIndex(0)
            self.table_empty.set_text("No branches detected", "The detector returned zero daughters. This does not prove there are no eligible branches; inspect the CT. JSON can be exported.", "info")
            self.details_stack.setCurrentIndex(0)
            self.details_empty.set_text("No branches detected", "Zero predictions, not a verified absence of branches.", "info")
            self.detail_title.setText("No branches detected")
            self.selection_summary.setText("No branches detected. Review the CT for possible misses.")
        self.update_visibility()
        self.update_actions()

    def select_branch(self):
        index = self.table.currentRow()
        if self.prediction is None or index < 0 or index >= len(self.prediction["daughters"]):
            return
        branch = self.prediction["daughters"][index]
        rgb = COLORS[index % len(COLORS)]
        self.detail_swatch.setPixmap(ui.dot_pixmap(rgb, 14))
        self.detail_title.setText(branch["instance_id"])
        for labels, key in ((self.origin_values, "ostium_xyz_mm"), (self.seed_values, "seed_xyz_mm"), (self.direction_values, "direction_xyz")):
            for widget, value in zip(labels, branch[key]):
                widget.setText(f"{value:.2f}")
        self.rose.set_direction(branch["direction_xyz"])
        chord = math.dist(branch["ostium_xyz_mm"], branch["seed_xyz_mm"])
        self.radius_value.setText(f"{branch['radius_mm']:.2f} mm")
        self.chord_value.setText(f"Straight-line origin to seed: {chord:.2f} mm. The challenge seed sits 5 mm along the vessel path, which can be longer than this chord.")
        self.details_stack.setCurrentIndex(1)
        self.selection_summary.setText(f"{branch['instance_id']}  ·  radius {branch['radius_mm']:.2f} mm  ·  chord {chord:.2f} mm\nSlices centred on its origin. Double-click to fly there.")
        evidence = self.path_evidence.get(branch['instance_id'])
        if evidence:
            self.selection_summary.setText(self.selection_summary.text +
                f"\nActual trace: {evidence['path_length_mm']:.2f} mm; "
                f"{evidence.get('tracking_status') or 'status unspecified'}; "
                f"stop: {evidence.get('stop_reason') or 'unspecified'}\n{self.path_note}")
        ui.stop(self.pulse)
        self.scene.highlight(index, self.prediction)
        self.pulse = ui.pulse_opacity(self.scene.selected_displays())

    def step_branch(self, delta):
        if self.prediction is None or not self.prediction["daughters"]:
            return
        count = len(self.prediction["daughters"])
        row = (max(self.table.currentRow(), 0) + delta) % count if self.table.currentRow() >= 0 else 0
        self.table.selectRow(row)
        if self.tabs.currentIndex == 2:
            self.tabs.setCurrentIndex(0)

    def fly_to_branch(self, *args):
        index = self.table.currentRow()
        if self.prediction is None or index < 0 or index >= len(self.prediction["daughters"]):
            return
        branch = self.prediction["daughters"][index]
        self.scene.fly_to(lps_to_ras(branch["ostium_xyz_mm"]), branch["radius_mm"])

    def copy_branch(self):
        index = self.table.currentRow()
        if self.prediction is None or index < 0 or index >= len(self.prediction["daughters"]):
            return
        branch = self.prediction["daughters"][index]
        slicer.app.clipboard().setText(json.dumps(branch, indent=2, allow_nan=False))
        self.notify(f"{branch['instance_id']} copied", "success")

    def export_results(self):
        if self.prediction is None:
            return
        name = self.loaded_case + ("_SYNTHETIC_EXAMPLE" if self.synthetic else "_prediction") + ".json"
        path = qt.QFileDialog.getSaveFileName(self.parent, "Export prediction JSON", str(self.repo / name), "JSON files (*.json)")
        if path:
            self.guard(lambda: self.export_prediction_path(path))

    def export_prediction_path(self, path):
        if self.prediction is None:
            raise ValueError("There is no prediction to export.")
        save_prediction(path, self.prediction)
        self.notify("JSON exported", "success", "JSON exported in the original SimpleITK physical coordinates.")

    def copy_results(self):
        if self.prediction is not None:
            slicer.app.clipboard().setText(json.dumps(self.prediction, indent=2, allow_nan=False))
            self.notify("Prediction JSON copied to clipboard", "success")

    def export_edited_nifti(self):
        if not self.path_evidence or self.synthetic or self.prediction is None:
            return
        path = qt.QFileDialog.getSaveFileName(
            self.parent, "Export edited labelmap (aorta + estimated traces)",
            str(self.repo / (self.loaded_case + "_edited_labels.nii")),
            "NIfTI labelmap (*.nii);;Compressed NIfTI labelmap (*.nii.gz)")
        if path:
            self.guard(lambda: self.export_edited_nifti_path(path))

    def export_edited_nifti_path(self, path):
        if self.process is not None or self.synthetic or self.prediction is None or not self.path_evidence:
            raise ValueError("Run detection to obtain real traces before exporting an edited NIfTI.")
        if set(self.path_evidence) != {item['instance_id'] for item in self.prediction['daughters']}:
            raise ValueError("Some branches are missing traced paths. Run detection again before export.")
        target = self.scene.export_edited_nifti(path, self.path_evidence, (self.loaded_image, self.loaded_mask))
        self.notify("Edited NIfTI exported", "success", "Saved labelmap: 1 = current aorta, 2 = estimated traces outside it. Original CT unchanged.")
        return target

    def capture_view(self):
        if not self.scene.ct:
            return
        path = qt.QFileDialog.getSaveFileName(self.parent, "Save visual check", str(self.repo / (str(self.loaded_case) + "_visual_check.png")), "PNG image (*.png)")
        if path:
            self.guard(lambda: self.save_screenshot(path))

    def save_screenshot(self, path):
        image = ctk.ctkWidgetsUtils.grabWidget(slicer.util.mainWindow())
        if not image.save(str(path)):
            raise OSError("Unable to save the visual check.")
        self.notify("Visual check saved", "success")

    # ------------------------------------------------------------------ display

    def update_visibility(self, *args):
        if not hasattr(self, "opacity"):
            return
        self.opacity_value.setText(f"{self.opacity.value}%")
        self.scene.visibility(self.aorta_check.checked, self.origins_check.checked, self.arrows_check.checked, self.radii_check.checked, self.labels_check.checked, self.opacity.value / 100.)

    def change_window(self, index):
        self.window_index = int(index)
        if self.scene.ct:
            _, window, level = WINDOW_PRESETS[self.window_index]
            self.scene.ct.GetDisplayNode().AutoWindowLevelOff()
            self.scene.ct.GetDisplayNode().SetWindowLevel(window, level)

    def toggle_layout(self):
        lm = slicer.app.layoutManager()
        if lm.layout == slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView:
            lm.setLayout(LAYOUT_ID)
            self.layout_button.setText("3D only")
            self.layout_button.setIcon(ui.icon("layout3d", "text"))
            self.header_layout_button.setIcon(ui.icon("layout3d", "text2"))
        else:
            lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView)
            self.layout_button.setText("3D + slices")
            self.layout_button.setIcon(ui.icon("layout", "text"))
            self.header_layout_button.setIcon(ui.icon("layout", "text2"))
        self.configure_views()

    def fit_view(self):
        self.scene.focus_aorta(animated=True)

    def show_page(self, index):
        self.controls_tabs.setCurrentIndex(int(index))

    def on_page_changed(self, index):
        self.nav.set_index(index, notify=False)
        page = self.controls_tabs.widget(index)
        if page is not None and self.workspace_open:
            ui.fade_in(page, 200, 0.25)

    def update_actions(self):
        if not hasattr(self, "export_button"):
            return
        busy = self.process is not None
        has_study = self.scene.ct is not None
        for widget in self.control_widgets:
            widget.setEnabled(not busy)
        self.run_button.setEnabled(has_study and not self.synthetic and not busy)
        self.import_button.setEnabled(has_study and not busy)
        self.export_button.setEnabled(self.prediction is not None and not busy)
        self.nifti_button.setEnabled(has_study and self.prediction is not None and bool(self.path_evidence) and not self.synthetic and not busy)
        self.copy_button.setEnabled(self.prediction is not None)
        self.capture_button.setEnabled(has_study and self.prediction is not None)
        self.cancel_button.setVisible(busy)
        if busy:
            self.activity.start()
        else:
            self.activity.finish()
        self.log_button.setVisible(bool(self.run_log) and not busy)
        self.refresh_states()

    def refresh_states(self):
        has_study = self.scene.ct is not None
        has_prediction = self.prediction is not None
        states = ["done" if has_study else "active", "pending", "pending"]
        if has_study:
            states[1] = "done" if has_prediction else "active"
        if has_prediction:
            states[2] = "active"
        self.stepper.set_states(states, self.process is not None)
        self.nav.set_done(0, has_study)
        self.nav.set_done(1, has_prediction)

    # ------------------------------------------------------------------ pipeline process

    def run_detection(self):
        self.guard(self._run_detection)

    def _run_detection(self):
        if self.process or not self.loaded_image or self.synthetic:
            return
        executable = self.python_edit.text.strip()
        script = self.pipeline_edit.text.strip()
        if not Path(executable).is_file() or not Path(script).is_file():
            self.show_page(1)
            self.pipeline_section.set_expanded(True)
            raise ValueError("Choose your team's Python executable and run.py under Pipeline. You can also import a prediction JSON while the pipeline is being built.")
        self.settings.setValue("BranchForge/Python", executable)
        self.settings.setValue("BranchForge/Pipeline", script)
        self.run_dir = tempfile.TemporaryDirectory(prefix="branchforge-run-")
        self.output_path = str(Path(self.run_dir.name) / "prediction.json")
        process = qt.QProcess(self.parent)
        # Slicer changes Python and DLL paths. Restore the launch environment for the team's venv.
        env = qt.QProcessEnvironment()
        for key, value in slicer.util.startupEnvironment().items():
            env.insert(key, value)
        process.setProcessEnvironment(env)
        process.setWorkingDirectory(str(Path(script).resolve().parent))
        process.setProcessChannelMode(qt.QProcess.MergedChannels)
        process.connect("readyReadStandardOutput()", self.on_process_output)
        process.connect("finished(int,QProcess::ExitStatus)", self.on_process_finished)
        process.connect("errorOccurred(QProcess::ProcessError)", self.on_process_error)
        self.process = process
        self.run_log = ""
        self.cancelled = False
        self.started = time.monotonic()
        self.clear_prediction()
        self.set_status("Detecting branches... you can still rotate and explore the anatomy.", "info")
        self.elapsed_timer.start()
        self.update_actions()
        if self.toast is not None and self.workspace_open:
            self.toast.show_message("Detection started", "info")
        process.start(executable, detection_arguments(script, self.loaded_image, self.loaded_mask,
                                                       self.output_path, self.loaded_case,
                                                       18 + self.fold_combo.currentIndex if self.fold_combo.currentIndex else None))

    def tick_elapsed(self):
        if self.process is None:
            self.elapsed_timer.stop()
            return
        elapsed = time.monotonic() - self.started
        self.status.setText(f"Detecting branches  ·  {elapsed:.0f} s elapsed. You can still rotate and explore the anatomy.")

    def on_process_output(self):
        if self.process:
            payload = self.process.readAllStandardOutput().data()
            text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
            self.run_log = (self.run_log + text)[-16000:]

    def on_process_error(self, error):
        if self.process and error == qt.QProcess.FailedToStart:
            message = self.process.errorString()
            self.finish_process()
            self.notify("Could not start Python: " + message, "error")

    def on_process_finished(self, code, exit_status):
        if self.process is None:
            return
        elapsed = time.monotonic() - self.started
        try:
            self.on_process_output()
            if self.cancelled:
                self.notify("Detection cancelled", "warning", "Detection cancelled. No partial results were imported.")
            elif code != 0 or exit_status != qt.QProcess.NormalExit:
                self.notify(f"Detection failed (exit {code})", "error", f"Detection failed (exit {code}). Open the pipeline log for details.")
                self.show_log()
            else:
                data = load_prediction(self.output_path, self.loaded_case)
                paths, note = load_path_evidence(self.output_path, data)
                self.apply_prediction(data, f"Pipeline  {elapsed:.1f} s", "mint", paths, note)
                self.notify(f"{len(data['daughters'])} branches found in {elapsed:.1f} s", "success", f"Complete in {elapsed:.1f} s. {len(data['daughters'])} branches ready to explore. {note}")
        except Exception as exc:
            self.notify("Pipeline output rejected: " + str(exc), "error")
            self.run_log += "\n" + str(exc)
            self.show_log()
        finally:
            self.finish_process()

    def show_log(self):
        dialog = qt.QDialog(self.parent)
        dialog.setWindowTitle("BranchForge - Pipeline log")
        dialog.resize(680, 400)
        layout = qt.QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(label("PIPELINE CONSOLE OUTPUT", "BFEyebrow"))
        text = qt.QPlainTextEdit()
        text.setObjectName("BFLog")
        text.setReadOnly(True)
        text.setPlainText(self.run_log or "The pipeline did not write any console output.")
        layout.addWidget(text)
        row = qt.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button("Close", dialog.accept, "secondary", "close"))
        layout.addLayout(row)
        dialog.setAttribute(qt.Qt.WA_DeleteOnClose)
        dialog.show()
        self.log_dialog = dialog

    def cancel_run(self):
        if self.process:
            self.cancelled = True
            self.set_status("Cancelling detection...", "warning")
            process = self.process
            process.terminate()
            qt.QTimer.singleShot(1500, lambda: process.kill() if self.process is process and process.state() != qt.QProcess.NotRunning else None)

    def finish_process(self):
        self.elapsed_timer.stop()
        if self.process:
            self.process.deleteLater()
        self.process = None
        if self.run_dir:
            self.run_dir.cleanup()
            self.run_dir = None
        self.update_actions()

    # ------------------------------------------------------------------ scene lifecycle

    def on_scene_close(self, caller=None, event=None):
        if hasattr(self, "ar_sharing"):
            self.ar_sharing.stop()
        if self.process:
            self.cancel_run()
        ui.stop(self.pulse)
        self.pulse = None
        self.scene = BranchScene()
        self.loaded_case = self.loaded_image = self.loaded_mask = None
        self.synthetic = False
        self.clear_prediction()
        self.header_case.setText("No study loaded", "muted")
        self.study_case.setText("No study loaded")
        self.study_info.setText("Select a CT and its matching aorta mask.")
        self.set_status("Scene cleared. Ready to load a study.", "info")

    def on_scene_closed(self, caller=None, event=None):
        # Closing a scene resets the 3D and slice view nodes; restyle them if we are still open.
        if self.workspace_open:
            qt.QTimer.singleShot(0, self.configure_views)

    def cleanup(self):
        self.ar_sharing.cleanup()
        self.close_workspace()
        self.elapsed_timer.stop()
        if self.process:
            self.process.kill()
            self.process.waitForFinished(2000)
            self.finish_process()
        if self.scene_observer:
            slicer.mrmlScene.RemoveObserver(self.scene_observer)
            self.scene_observer = None
        if self.scene_closed_observer:
            slicer.mrmlScene.RemoveObserver(self.scene_closed_observer)
            self.scene_closed_observer = None
        self.scene.clear()
        slicer.util.mainWindow().removeDockWidget(self.inspector_dock)
        slicer.util.mainWindow().removeToolBar(self.toolbar)
        self.inspector_dock.deleteLater()
        self.toolbar.deleteLater()
