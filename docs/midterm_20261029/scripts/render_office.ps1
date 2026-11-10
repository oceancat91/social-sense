param([string]$InputPath,[string]$OutputDir,[string]$Kind='pptx')
$ErrorActionPreference='Stop'
$resolvedInput=(Resolve-Path -LiteralPath $InputPath).Path
$resolvedOutput=[System.IO.Path]::GetFullPath($OutputDir)
[System.IO.Directory]::CreateDirectory($resolvedOutput) | Out-Null
if($Kind -eq 'pptx') {
  $pptApplication=New-Object -ComObject PowerPoint.Application
  try {
    $deck=$pptApplication.Presentations.Open($resolvedInput,$true,$false,$false)
    $deck.Export($resolvedOutput,'PNG',1600,900)
    $deck.SaveAs((Join-Path $resolvedOutput 'render.pdf'),32)
    Write-Output ('Rendered slides: '+$deck.Slides.Count)
    $deck.Close()
  } finally {$pptApplication.Quit()}
} else {
  $wordApplication=New-Object -ComObject Word.Application
  $wordApplication.Visible=$false
  try {
    $document=$wordApplication.Documents.Open($resolvedInput,$false,$true)
    $document.ExportAsFixedFormat((Join-Path $resolvedOutput 'render.pdf'),17)
    Write-Output ('Rendered pages: '+$document.ComputeStatistics(2))
    $document.Close(0)
  } finally {$wordApplication.Quit()}
}
