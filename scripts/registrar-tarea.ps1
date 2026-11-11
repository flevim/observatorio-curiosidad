# Registra (o actualiza) una tarea diaria en el Programador de tareas de Windows para el usuario actual.
# Uso:   powershell -ExecutionPolicy Bypass -File scripts\registrar-tarea.ps1 [-Hora 09:00]
# Quitar: schtasks /Delete /TN "ObservatorioCuriosidad-diario" /F
param([string]$Hora = '09:00')

$script = Join-Path $PSScriptRoot 'actualizar-diario.ps1'
$accion = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$script`""
schtasks /Create /TN 'ObservatorioCuriosidad-diario' /TR $accion /SC DAILY /ST $Hora /F
if ($LASTEXITCODE -eq 0) {
    Write-Output "Tarea registrada: todos los días a las $Hora. Registro en data\daily.log."
}
