$ErrorActionPreference = "Stop"
$gccRoot = "C:\NXP\S32DS.3.6.9\S32DS\build_tools\gcc_v11.4\gcc-11.4-arm32-eabi\bin"
$gcc = Join-Path $gccRoot "arm-none-eabi-gcc.exe"
$objcopy = Join-Path $gccRoot "arm-none-eabi-objcopy.exe"
$suite = $PSScriptRoot
$repositoryRoot = (Resolve-Path (Join-Path $suite "..\..")).Path
$output = Join-Path $repositoryRoot "artifacts\s32k148_gemini_source_only_holdout_v6"
New-Item -ItemType Directory -Force -Path $output | Out-Null
$elf = Join-Path $output "star_s32k148_gemini_source_only_holdout_v6.elf"
$hex = Join-Path $output "star_s32k148_gemini_source_only_holdout_v6.hex"
$map = Join-Path $output "star_s32k148_gemini_source_only_holdout_v6.map"
$arguments = @(
    "-mcpu=cortex-m4", "-mthumb", "-O0", "-g3",
    "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror",
    "-nostartfiles", "-Wl,--gc-sections", "-Wl,-Map=$map",
    "-T", (Join-Path $suite "s32k148.ld"),
    (Join-Path $suite "automotive_holdout_v6_tasks.c"),
    (Join-Path $suite "s32k148_holdout_v6_main.c"),
    (Join-Path $suite "baremetal_runtime.c"),
    "-o", $elf
)
& $gcc @arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $objcopy -O ihex $elf $hex
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Get-FileHash $elf -Algorithm SHA256
