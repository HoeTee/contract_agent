param(
    [string]$Tag = "southernbanker/lexora:latest",
    [string]$KeyFile
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$temporaryKey = $null

try {
    if ($KeyFile) {
        $resolvedKey = (Resolve-Path -LiteralPath $KeyFile).Path
    }
    else {
        $temporaryKey = Join-Path ([System.IO.Path]::GetTempPath()) ("lexora-source-" + [guid]::NewGuid().ToString("N") + ".key")
        $key = New-Object byte[] 32
        $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try {
            $random.GetBytes($key)
        }
        finally {
            $random.Dispose()
        }
        [System.IO.File]::WriteAllBytes($temporaryKey, $key)
        $resolvedKey = $temporaryKey
    }

    $keyLength = (Get-Item -LiteralPath $resolvedKey).Length
    if ($keyLength -ne 32) {
        throw "AES key must contain exactly 32 bytes; received $keyLength bytes."
    }

    docker build `
        --secret "id=source_key,src=$resolvedKey" `
        --tag $Tag `
        $projectRoot

    if ($LASTEXITCODE -ne 0) {
        throw "Docker build failed with exit code $LASTEXITCODE."
    }

    Write-Output "Built protected image: $Tag"
}
finally {
    if ($temporaryKey -and (Test-Path -LiteralPath $temporaryKey)) {
        Remove-Item -LiteralPath $temporaryKey -Force
    }
}
