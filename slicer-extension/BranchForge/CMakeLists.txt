set(MODULE_NAME BranchForge)
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  BranchForgeLib/__init__.py
  BranchForgeLib/contract.py
  BranchForgeLib/integration.py
  BranchForgeLib/scene.py
  BranchForgeLib/sample.py
  BranchForgeLib/ui.py
  BranchForgeLib/report.py
  BranchForgeLib/ar_export.py
  BranchForgeLib/ar_share.py
)
file(GLOB MODULE_ICON_FILES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR} Resources/Icons/*.svg)
set(MODULE_PYTHON_RESOURCES
  ${MODULE_ICON_FILES}
  Resources/theme.qss
)
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
)
