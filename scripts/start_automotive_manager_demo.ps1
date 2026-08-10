$controllerRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $controllerRoot
python -m task_admission_framework.main gui
