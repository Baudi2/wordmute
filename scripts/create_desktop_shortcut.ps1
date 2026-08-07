# Creates (or refreshes) a desktop shortcut that launches WordMute
# without a console window. The milestone-8 installer will do this
# properly; this script covers development use until then.

$python = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
if (-not (Test-Path $python)) {
    throw "pythonw.exe not found next to python.exe"
}
$repo = Split-Path $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut((Join-Path $desktop "WordMute.lnk"))
$sc.TargetPath = $python
$sc.Arguments = "-m wordmute_app"
$sc.WorkingDirectory = $repo
$sc.Description = "WordMute - mute unwanted words in video/audio"
$sc.Save()
Write-Host "Shortcut created: $(Join-Path $desktop 'WordMute.lnk')"
