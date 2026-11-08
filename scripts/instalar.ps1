# Instalador do Optimus para Windows 10 e 11.
# Rode no PowerShell, dentro da pasta do Optimus:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
#   (acrescente -SemIA para não instalar o Ollama nem baixar o modelo)
param([switch]$SemIA)
$ErrorActionPreference = "Stop"
function Ok($t)    { Write-Host "OK  $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "!   $t" -ForegroundColor Yellow }

$Pasta = Split-Path -Parent $PSScriptRoot
Write-Host "== Instalando o Optimus ==" -ForegroundColor Cyan

# 1. Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python -or -not (& python -c "import sys; print(sys.version_info >= (3,10))" 2>$null | Select-String True)) {
    Aviso "Python 3.10+ não encontrado. Instalando pelo winget..."
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
Ok ("Python " + (& python --version))

# 2. Ambiente do Optimus
$Dados = Join-Path $env:LOCALAPPDATA "Optimus"
New-Item -ItemType Directory -Force -Path $Dados | Out-Null
& python -m venv (Join-Path $Dados "venv")
$Py = Join-Path $Dados "venv\Scripts\python.exe"
$Optimus = Join-Path $Dados "venv\Scripts\optimus.exe"
& $Py -m pip install --upgrade pip | Out-Null
& $Py -m pip install "$Pasta[completo]"
if ($LASTEXITCODE -ne 0) { & $Py -m pip install "$Pasta" }
Ok "Optimus instalado"

# Comando 'optimus' disponível em qualquer terminal
$Scripts = Join-Path $Dados "venv\Scripts"
$PathUsuario = [Environment]::GetEnvironmentVariable("Path", "User")
if ($PathUsuario -notlike "*$Scripts*") {
    [Environment]::SetEnvironmentVariable("Path", "$PathUsuario;$Scripts", "User")
    Ok "Comando 'optimus' adicionado ao PATH (abra um terminal novo)"
}

# 3. Vozes naturais offline (feminina e masculina) já prontas
& $Optimus vozes --baixar
if ($LASTEXITCODE -ne 0) { Aviso "Vozes offline não baixadas. Rode depois: optimus vozes --baixar" }

# 4. Motor de IA local (Ollama) e modelo ideal para este PC
if (-not $SemIA) {
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Write-Host "Instalando o Ollama (motor de IA local, https://ollama.com)..."
        winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    }
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
        Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 4
        & $Optimus hardware
        & $Optimus instalar-modelo
        if ($LASTEXITCODE -ne 0) { Aviso "Rode depois: optimus instalar-modelo" }
    } else { Aviso "Instale o Ollama em https://ollama.com/download" }
}

# 5. Atalhos na área de trabalho e no menu Iniciar
$Shell = New-Object -ComObject WScript.Shell
foreach ($Destino in @([Environment]::GetFolderPath("Desktop"), (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))) {
    $Atalho = $Shell.CreateShortcut((Join-Path $Destino "Optimus.lnk"))
    $Atalho.TargetPath = (Join-Path $Dados "venv\Scripts\pythonw.exe")
    $Atalho.Arguments = "-m optimus gui"
    $Atalho.WorkingDirectory = $env:USERPROFILE
    $Atalho.Description = "Optimus - assistente de IA local"
    $Atalho.Save()
}
Ok "Atalho 'Optimus' criado na área de trabalho e no menu Iniciar"

Write-Host ""
Ok "Pronto! Abra pelo atalho ou rode: optimus gui"
Write-Host "Aviso: o Optimus executa ações reais no seu computador. O uso é de sua responsabilidade." -ForegroundColor Yellow
