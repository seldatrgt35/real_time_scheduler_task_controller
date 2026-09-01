param([switch]$EnableCodeCache)
$ErrorActionPreference = "Stop"
$gccRoot = "C:\NXP\S32DS.3.6.9\S32DS\build_tools\gcc_v11.4\gcc-11.4-arm32-eabi\bin"
$gcc = Join-Path $gccRoot "arm-none-eabi-gcc.exe"
$objcopy = Join-Path $gccRoot "arm-none-eabi-objcopy.exe"
$objdump = Join-Path $gccRoot "arm-none-eabi-objdump.exe"
$suite = $PSScriptRoot
$repositoryRoot = (Resolve-Path (Join-Path $suite "..\..")).Path
$variant = if ($EnableCodeCache) { "cache_on" } else { "cache_off" }
$output = Join-Path $repositoryRoot "artifacts\s32k148_manual_instruction_baseline_$variant"
New-Item -ItemType Directory -Force -Path $output | Out-Null
$baseName = "star_s32k148_manual_instruction_baseline_$variant"
$elf = Join-Path $output "$baseName.elf"
$hex = Join-Path $output "$baseName.hex"
$map = Join-Path $output "star_s32k148_manual_instruction_baseline.map"
$disassembly = Join-Path $output "$baseName.disasm.txt"

# -O0 disables optimization passes. The additional -fno-* options make the
# experiment explicit and prevent builtin substitution, inlining, sibling-call
# conversion, frame-pointer omission, interprocedural transforms and LTO.
$compileFlags = @(
    "-mcpu=cortex-m4", "-mthumb", "-O0", "-g3",
    "-fno-builtin", "-fno-inline", "-fno-inline-functions",
    "-fno-omit-frame-pointer", "-fno-optimize-sibling-calls",
    "-fno-ipa-cp", "-fno-ipa-sra", "-fno-ipa-icf", "-fno-lto",
    "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror"
)
if ($EnableCodeCache) {
    $compileFlags += "-DSTAR_ENABLE_CODE_CACHE=1"
}
$arguments = @(
    $compileFlags
    "-nostartfiles", "-Wl,--gc-sections", "-Wl,-Map=$map",
    "-T", (Join-Path $repositoryRoot "experiments\gemini_source_only_holdout_v6\s32k148.ld"),
    (Join-Path $suite "manual_automotive_task.c"),
    (Join-Path $suite "s32k148_manual_main.c"),
    (Join-Path $repositoryRoot "experiments\gemini_source_only_holdout_v6\baremetal_runtime.c"),
    "-o", $elf
)
& $gcc @arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $objcopy -O ihex $elf $hex
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $objdump -d $elf | Set-Content -Encoding utf8 $disassembly
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $gcc --version | Select-Object -First 1
"Compile flags: $($compileFlags -join ' ')"
Get-FileHash $elf -Algorithm SHA256
