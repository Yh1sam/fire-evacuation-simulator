param(
  [string]$InDir = (Join-Path $PSScriptRoot '..\in'),
  [string]$Keep = 'arena_cshape_80x50_4x4.txt',
  [switch]$DryRun
)
if(!(Test-Path -LiteralPath $InDir)){
  Write-Error ("Input dir not found: {0}" -f $InDir)
  exit 1
}
$files = Get-ChildItem -LiteralPath $InDir -File
$toDelete = $files | Where-Object { $_.Name -ne $Keep }
Write-Host ("Keeping: {0}" -f $Keep)
if($toDelete){
  Write-Host ("Deleting: {0}" -f ($toDelete.Name -join ', '))
  if(-not $DryRun){ $toDelete | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction Stop } }
  else { Write-Host 'DryRun set: no files deleted.' }
}else{
  Write-Host 'Nothing to delete.'
}
