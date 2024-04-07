# 这个脚本用于编译所有的.po文件为对应的.mo文件

$lastLocation = Get-Location

Set-Location $PSScriptRoot

Get-ChildItem -Filter *.po | ForEach-Object {
    $poFile = $_.FullName
    $moFile = $_.BaseName + '.mo'  # Generate the corresponding .mo file name
    msgfmt -o $moFile $poFile
}

Set-Location $lastLocation
