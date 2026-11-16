$ErrorActionPreference = 'Stop'
$launcherRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$compiler = Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Compilador .NET Framework não encontrado neste Windows.' }
$launcherOutput = Join-Path $launcherRepoRoot 'Hydra.exe'
$launcherBuildDirectory = Join-Path $launcherRepoRoot '.orchestrator/launcher-build'
New-Item -ItemType Directory -Path $launcherBuildDirectory -Force | Out-Null
$launcherBuildId = [Guid]::NewGuid().ToString('N')
$launcherCandidate = Join-Path $launcherBuildDirectory "Hydra-$launcherBuildId.exe"
$launcherPrevious = Join-Path $launcherBuildDirectory "Hydra-previous-$launcherBuildId.exe"
& $compiler /nologo /target:winexe /optimize+ "/out:$launcherCandidate" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Net.Http.dll (Join-Path $PSScriptRoot 'HydraLauncher.cs')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar o executável Hydra.' }
# Rename preserves a running launcher's image and avoids terminating its agents.
foreach ($launcherTarget in @($launcherOutput, $launcherCandidate, $launcherPrevious)) {
    if (-not ([IO.Path]::GetFullPath($launcherTarget).StartsWith($launcherRepoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase))) {
        throw 'O destino do build está fora do repositório Hydra.'
    }
}
try {
    if (Test-Path -LiteralPath $launcherOutput) { Move-Item -LiteralPath $launcherOutput -Destination $launcherPrevious }
    Move-Item -LiteralPath $launcherCandidate -Destination $launcherOutput
} catch {
    if (-not (Test-Path -LiteralPath $launcherOutput) -and (Test-Path -LiteralPath $launcherPrevious)) {
        Move-Item -LiteralPath $launcherPrevious -Destination $launcherOutput
    }
    throw "O build foi preservado em $launcherCandidate. Feche o controle Hydra e execute o build novamente. $($_.Exception.Message)"
}
Write-Output $launcherOutput
