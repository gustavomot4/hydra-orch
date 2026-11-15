$ErrorActionPreference = 'Stop'
$launcherRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Compilador .NET Framework não encontrado neste Windows.' }
$launcherOutput = Join-Path $launcherRepoRoot 'Hydra.exe'
& $compiler /nologo /target:winexe /optimize+ "/out:$launcherOutput" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Net.Http.dll (Join-Path $PSScriptRoot 'HydraLauncher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar o executável Hydra.' }
Write-Output $launcherOutput
