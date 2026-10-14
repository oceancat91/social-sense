# 低负载安全训练：默认喂 log 目标 + 异常库回填 C
# 用法（在 social_forecast 目录）:
#   powershell -ExecutionPolicy Bypass -File .\run_safe.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$env:ABLATION_GPU_FRAC = "0.40"
$env:TEXT_CACHE_BS = "1"
$env:PYTORCH_ALLOC_CONF = "expandable_segments:True"

Write-Host "=== full experiment (safe) ==="
Write-Host "GPU frac      = $env:ABLATION_GPU_FRAC"
Write-Host "TEXT_CACHE_BS = $env:TEXT_CACHE_BS"
Write-Host "pipeline      = anomaly → text export → report → train(log+lite)"
Write-Host ""

# 先保证有 log 目标与异常结果
python -u scripts\run_full_experiment.py --capacity lite --template-llm

Write-Host ""
Write-Host "done. see results\ and data\social\report.md"
