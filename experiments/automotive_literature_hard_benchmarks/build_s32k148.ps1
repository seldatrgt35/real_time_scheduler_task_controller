$ErrorActionPreference = "Stop"
$gccRoot = "C:\NXP\S32DS.3.6.9\S32DS\build_tools\gcc_v11.4\gcc-11.4-arm32-eabi\bin"
$gcc = Join-Path $gccRoot "arm-none-eabi-gcc.exe"
$objcopy = Join-Path $gccRoot "arm-none-eabi-objcopy.exe"
$objdump = Join-Path $gccRoot "arm-none-eabi-objdump.exe"
$suite = $PSScriptRoot
$root = (Resolve-Path (Join-Path $suite "..\..")).Path
$output = Join-Path $root "artifacts\s32k148_automotive_literature_hard_benchmarks"
New-Item -ItemType Directory -Force -Path $output | Out-Null
$base = "star_s32k148_literature_hard_benchmarks"
$elf = Join-Path $output "$base.elf"
$flags = @(
    "-mcpu=cortex-m4", "-mthumb", "-O0", "-g3", "-fno-builtin",
    "-fno-inline", "-fno-inline-functions", "-fno-omit-frame-pointer",
    "-fno-optimize-sibling-calls", "-fno-ipa-cp", "-fno-ipa-sra",
    "-fno-ipa-icf", "-fno-lto", "-ffunction-sections", "-fdata-sections",
    "-Wall", "-Wextra", "-Werror"
)
& $gcc @flags "-nostartfiles" "-Wl,--gc-sections" `
    "-Wl,-Map=$(Join-Path $output "$base.map")" `
    "-T" (Join-Path $root "experiments\gemini_source_only_holdout_v6\s32k148.ld") `
    (Join-Path $suite "automotive_literature_hard_benchmarks.c") `
    (Join-Path $suite "s32k148_literature_hard_benchmarks_main.c") `
    (Join-Path $root "experiments\gemini_source_only_holdout_v6\baremetal_runtime.c") `
    "-o" $elf
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $objcopy -O ihex $elf (Join-Path $output "$base.hex")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $objdump -d $elf | Set-Content -Encoding utf8 (Join-Path $output "$base.disasm.txt")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Get-FileHash $elf -Algorithm SHA256
