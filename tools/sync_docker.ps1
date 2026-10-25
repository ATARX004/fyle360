# Copia el modulo de ESTE repo a la carpeta que monta el Docker local.
#
#   origen  : FYLE360\certum_revision                      (aqui vive el git)
#   destino : (carpeta que monta el Docker)\certum_revision  (copia, SIN .git)
#
# El destino es un espejo: lo que se borra aqui se borra alla. No toca nada
# mas de esa carpeta (ni el git de VALIDA ni los otros modulos).
#
# Uso (PowerShell, desde la raiz del repo):
#   .\tools\sync_docker.ps1
#   .\tools\sync_docker.ps1 -Destino "C:\otra\carpeta\de\addons"
param(
    [string]$Destino = "C:\Users\jesus\OneDrive\Desktop\ODOO MODULOS DE HOMOLOGACION Y DE INSPECCION\cloudclusters\odoo\extra_addons\.claude\.claude\worktrees\kind-cannon-8ab307"
)

$ErrorActionPreference = 'Stop'
$repo   = Split-Path -Parent $PSScriptRoot
$origen = Join-Path $repo 'certum_revision'
$dst    = Join-Path $Destino 'certum_revision'

if (-not (Test-Path (Join-Path $origen '__manifest__.py'))) { throw "No encuentro el modulo en $origen" }
if (-not (Test-Path (Join-Path $Destino 'dev_local\docker-compose.yml'))) {
    throw "$Destino no parece la carpeta que monta el Docker (falta dev_local\docker-compose.yml)"
}

robocopy $origen $dst /MIR /XD __pycache__ .git /XF *.pyc /NFL /NDL /NJH /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy fallo con codigo $LASTEXITCODE" }
Write-Host "OK: $origen  ->  $dst"
exit 0   # robocopy usa 1-7 para "copio/borro algo": no es error
