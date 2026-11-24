param([ValidateSet('Start','Status','Stop')][string]$Action='Status')
$ErrorActionPreference='Stop'
$project = Split-Path $PSScriptRoot -Parent
$serviceRoot = Join-Path $project '.local/assistant/services'
$recordPath = Join-Path $serviceRoot 'processes.json'
function Owned($record) {
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if ($process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $record.started) { return $process }
    return $null
}
if ($Action -eq 'Status') {
    if (-not (Test-Path -LiteralPath $recordPath)) { Write-Output 'Assistant services have not been started.'; return }
    $records = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    foreach ($record in $records) { Write-Output ($record.name+': '+[bool](Owned $record)+' (pid '+$record.pid+')') }
    return
}
if ($Action -eq 'Stop') {
    if (Test-Path -LiteralPath $recordPath) {
        foreach ($record in (Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json)) {
            $ownedProcess=Owned $record
            if ($ownedProcess) { Stop-Process -Id $ownedProcess.Id; $ownedProcess.WaitForExit(10000) | Out-Null }
        }
        Remove-Item -LiteralPath $recordPath
    }
    Write-Output 'Assistant services stopped; model files and database retained.'
    return
}
if (Test-Path -LiteralPath $recordPath) { throw 'Service record exists; inspect Status and use Stop before Start.' }
$installation = Get-Content -LiteralPath (Join-Path $serviceRoot 'installation.json') -Raw | ConvertFrom-Json
foreach ($port in @(6333,6334,8001)) {
    $probe = New-Object Net.Sockets.TcpClient
    try { $task = $probe.ConnectAsync('127.0.0.1',$port); if ($task.Wait(500) -and $probe.Connected) { throw "Port $port already in use." } }
    catch [System.AggregateException] { }
    finally { $probe.Dispose() }
}
$storage = (Join-Path $serviceRoot 'qdrant-storage').Replace('\','/')
$snapshots = (Join-Path $serviceRoot 'qdrant-snapshots').Replace('\','/')
$yaml = "log_level: WARN`ntelemetry_disabled: true`nstorage:`n  storage_path: `"$storage`"`n  snapshots_path: `"$snapshots`"`nservice:`n  host: 127.0.0.1`n  http_port: 6333`n  grpc_port: 6334`ncluster:`n  enabled: false`n"
$configPath = Join-Path $serviceRoot 'qdrant.yaml'
[IO.File]::WriteAllText($configPath,$yaml,[Text.UTF8Encoding]::new($false))
$python = (Get-Command python).Source
$localConfig = Join-Path $project '.local/system.local.json'
if (Test-Path -LiteralPath $localConfig) {
    $settings = Get-Content -LiteralPath $localConfig -Raw | ConvertFrom-Json
    if ($settings.PythonExe) { $python = $settings.PythonExe }
}
$services=@()
try {
    $qdrant = Start-Process -FilePath $installation.qdrant_exe -ArgumentList @('--config-path',('"'+$configPath+'"')) -WorkingDirectory $serviceRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $serviceRoot 'qdrant.out.log') -RedirectStandardError (Join-Path $serviceRoot 'qdrant.err.log')
    $services += @{name='qdrant';pid=$qdrant.Id;started=$qdrant.StartTime.ToUniversalTime().Ticks.ToString()}
    $env:USE_TF='0'; $env:USE_FLAX='0'; $env:PYTHONUNBUFFERED='1'
    $embedding = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','api.assistant.embedding_service:app','--host','127.0.0.1','--port','8001') -WorkingDirectory (Join-Path $project 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $serviceRoot 'embedding.out.log') -RedirectStandardError (Join-Path $serviceRoot 'embedding.err.log')
    $services += @{name='embeddings';pid=$embedding.Id;started=$embedding.StartTime.ToUniversalTime().Ticks.ToString()}
    $services | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding utf8
    Write-Output 'Services starting on localhost: Qdrant 6333, embeddings 8001. Inspect Status and health endpoints.'
} catch {
    foreach ($record in $services) { $ownedProcess=Owned $record; if ($ownedProcess) { Stop-Process -Id $ownedProcess.Id } }
    throw
}
