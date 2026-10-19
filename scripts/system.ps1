# Windows PowerShell 5.1 / PowerShell 7；从任意目录调用。
[CmdletBinding()]
param(
    [Parameter(Position=0)][ValidateSet('Build','Start','Stop','Restart','Status')][string]$Action='Status',
    [ValidateSet('Deploy','Dev')][string]$Mode='Deploy',
    [string]$Config,
    [string]$Release,
    [switch]$Force
)
$ErrorActionPreference='Stop'
$savedEnvironment=@{}
foreach ($name in [Environment]::GetEnvironmentVariables('Process').Keys) {
    if ($name -like 'TFIELD_*' -or $name -eq 'PYTHONPATH') { $savedEnvironment[$name]=[Environment]::GetEnvironmentVariable($name,'Process') }
}
try {
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$local=Join-Path $project '.local'
New-Item -ItemType Directory -Path $local -Force | Out-Null
if (-not $Config) { $Config=Join-Path $local 'system.local.json' }
$Config=[IO.Path]::GetFullPath($Config)
$settings=@{}
if (Test-Path -LiteralPath $Config) {
    $parsed=Get-Content -LiteralPath $Config -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($item in $parsed.PSObject.Properties) { $settings[$item.Name]=$item.Value }
}
if ($settings.Environment) {
    foreach ($item in $settings.Environment.PSObject.Properties) {
        if ($item.Name -notmatch '^TFIELD_[A-Z0-9_]+$') { throw 'Environment 只接受 TFIELD_ 开头的配置。' }
        [Environment]::SetEnvironmentVariable($item.Name,[string]$item.Value,'Process')
    }
}
function Tool([string]$Name,[string]$Fallback) {
    $value=$Fallback
    if ($settings[$Name]) { $value=[string]$settings[$Name] }
    return (Get-Command $value -ErrorAction Stop).Source
}
function Default-Env([string]$Name,[string]$Value) {
    if (-not [Environment]::GetEnvironmentVariable($Name,'Process')) { [Environment]::SetEnvironmentVariable($Name,$Value,'Process') }
}
Default-Env 'TFIELD_JAVA_PORT' '8080'
Default-Env 'TFIELD_PYTHON_PORT' '8503'
$javaPort=[int]$env:TFIELD_JAVA_PORT
$pythonPort=[int]$env:TFIELD_PYTHON_PORT
if ($javaPort -lt 1 -or $javaPort -gt 65535 -or $pythonPort -lt 1 -or $pythonPort -gt 65535 -or $javaPort -eq $pythonPort) { throw '服务端口配置无效。' }
$base="http://127.0.0.1:$javaPort"
$recordFile=Join-Path $local 'system-processes.json'
$currentFile=Join-Path $local 'current-release.json'
function Read-Record { if (Test-Path -LiteralPath $recordFile) { return Get-Content -LiteralPath $recordFile -Raw -Encoding UTF8 | ConvertFrom-Json }; return $null }
function Owned-Process($Item) {
    $process=Get-Process -Id $Item.pid -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    $details=Get-CimInstance Win32_Process -Filter ("ProcessId="+$Item.pid)
    if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne $Item.started -or
        -not $details.CommandLine.Contains([string]$Item.marker)) { throw "进程编号 $($Item.pid) 已被其他程序占用，拒绝操作。" }
    return $process
}
function Api([string]$Url) { Invoke-RestMethod -Uri $Url -TimeoutSec 5 }
function Show-Status {
    $record=Read-Record
    if (-not $record) { Write-Output '没有由统一入口管理的服务。'; return }
    $items=@($record.services | ForEach-Object { $p=Owned-Process $_; [PSCustomObject]@{service=$_.name;pid=$_.pid;running=([bool]$p)} })
    $health='unavailable'
    try { $health=(Api ($record.url+'/ops/health')).status } catch { }
    $page=$record.url
    if ($record.frontend_url) { $page=$record.frontend_url }
    [PSCustomObject]@{mode=$record.mode;url=$page;api=$record.url;release=$record.release;health=$health;services=$items;logs=$record.logs} | ConvertTo-Json -Depth 5
}
function Stop-System {
    $record=Read-Record
    if (-not $record) { Write-Output '没有需要停止的托管服务。'; return }
    # 先核对全部身份，再做任何停止动作；绝不按端口批量杀进程。
    foreach ($item in $record.services) { $null=Owned-Process $item }
    if (-not $Force) {
        try {
            $calibration=Api ($record.url+'/api/calibration')
            if ($calibration.job.state -eq 'running') { throw '仍有训练任务，请先完成或取消训练。' }
            $live=Api ($record.url+'/api/live/status')
            if ($live.pending_session_id -or $live.preparing) { throw '实时准备尚未完成，请先确认准备结果。' }
            if ($live.running) {
                $null=Invoke-RestMethod -Uri ($record.url+'/api/live/pause') -Method Post -Headers @{'Idempotency-Key'=[guid]::NewGuid().ToString();'X-TField-Expected-Session'=$live.session_id} -TimeoutSec 30
            }
        } catch { throw ('停止前未能确认业务状态：'+$_.Exception.Message+' 若服务已失联，可显式使用 -Force 中断进程。') }
    }
    foreach ($name in @('frontend','java','python')) {
        foreach ($item in @($record.services | Where-Object { $_.name -eq $name })) {
            $process=Owned-Process $item
            if ($process) { Stop-Process -Id $process.Id; Wait-Process -Id $process.Id -Timeout 30 -ErrorAction SilentlyContinue }
        }
    }
    Remove-Item -LiteralPath $recordFile
    Write-Output '托管服务已停止，数据库和业务文件保留。'
}
function Port-Busy([int]$Port) {
    $client=New-Object Net.Sockets.TcpClient
    try { $task=$client.ConnectAsync('127.0.0.1',$Port); return ($task.Wait(500) -and $client.Connected) } catch { return $false } finally { $client.Dispose() }
}
function Launch([string]$Name,[string]$Exe,[string[]]$Arguments,[string]$Directory,[string]$Marker,[string]$Logs) {
    $p=Start-Process -FilePath $Exe -ArgumentList $Arguments -WorkingDirectory $Directory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs ($Name+'.out.log')) -RedirectStandardError (Join-Path $Logs ($Name+'.err.log')) -PassThru
    return [PSCustomObject]@{name=$Name;pid=$p.Id;started=$p.StartTime.ToUniversalTime().Ticks.ToString();marker=$Marker}
}
$lock=$null
try {
    $lock=[IO.File]::Open((Join-Path $local 'system.lock'),'OpenOrCreate','ReadWrite','None')
    if ($Action -eq 'Status') { Show-Status; return }
    if ($Action -eq 'Stop' -or $Action -eq 'Restart') { Stop-System; if ($Action -eq 'Stop') { return } }
    if ($Action -eq 'Build') {
        $npm=Tool 'NpmExe' 'npm.cmd'
        $maven=Tool 'MavenExe' (Join-Path $project 'backend-java/mvnw.cmd')
        Push-Location (Join-Path $project 'frontend')
        try { & $npm run build; if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' } } finally { Pop-Location }
        $arguments=@('-f',(Join-Path $project 'backend-java/pom.xml'),'-Dmaven.test.skip=true','package')
        if ($settings.MavenSettings) { $arguments=@('-s',[string]$settings.MavenSettings)+$arguments }
        if ($settings.MavenRepository) { $arguments=@('-Dmaven.repo.local='+[string]$settings.MavenRepository)+$arguments }
        & $maven @arguments
        if ($LASTEXITCODE -ne 0) { throw 'Java 构建失败。' }
        $target=Join-Path $local ('releases/'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
        $python=Tool 'PythonExe' 'python'
        & $python -X utf8 (Join-Path $project 'backend/scripts/package_release.py') --destination $target
        if ($LASTEXITCODE -ne 0) { throw '部署包生成失败。' }
        @{path=$target} | ConvertTo-Json | Set-Content -LiteralPath $currentFile -Encoding UTF8
        Write-Output '构建完成；使用 Start 启动，或 Restart 切换到新版本。'
        return
    }
    $record=Read-Record
    if ($record) {
        $active=@($record.services | Where-Object { [bool](Owned-Process $_) })
        if ($record.url -ne $base -or ($record.config -and $record.config -ne $Config)) { throw '已有其他配置启动的服务，请先明确停止原服务。' }
        if ($Release -and [IO.Path]::GetFullPath($Release) -ne $record.release) { throw 'Start 不切换已运行版本，请使用 Restart -Release。' }
        if ($active.Count -eq $record.services.Count -and $record.mode -eq $Mode) { Show-Status; return }
        throw '已有托管记录；请先 Stop（故障时可用 -Force），再 Start。'
    }
    if (-not $Release) {
        if (-not (Test-Path -LiteralPath $currentFile)) { throw '请先 Build 生成部署包。' }
        $Release=(Get-Content -LiteralPath $currentFile -Raw -Encoding UTF8 | ConvertFrom-Json).path
    }
    $Release=(Resolve-Path -LiteralPath $Release).Path
    $manifest=Get-Content -LiteralPath (Join-Path $Release 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($file in $manifest.sha256.PSObject.Properties) {
        $path=Join-Path $Release $file.Name
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $file.Value) { throw ('部署包内容已改变：'+$file.Name) }
    }
    $ports=@($javaPort,$pythonPort)
    if ($Mode -eq 'Dev') { $ports+=5173 }
    foreach ($port in $ports) { if (Port-Busy $port) { throw "端口 $port 已占用。请核对旧进程后停止，不会自动终止其他服务。" } }
    Default-Env 'TFIELD_JAVA_HOST' '127.0.0.1'
    Default-Env 'TFIELD_MODEL_STORE_MODE' 'java'
    if ($env:TFIELD_MODEL_STORE_MODE -ne 'java') { throw '统一部署仅支持 java 模型管理模式。' }
    Default-Env 'TFIELD_DATASET_STORAGE_ROOT' (Join-Path $project 'backend/configs/datasets')
    Default-Env 'TFIELD_TRAINING_ROOT' (Join-Path $project 'backend/configs/training-jobs')
    Default-Env 'TFIELD_LIVE_SESSION_ROOT' (Join-Path $project 'backend/configs/live-sessions')
    Default-Env 'TFIELD_LIVE_SOURCE_ROOT' (Join-Path $project 'backend/configs/live')
    Default-Env 'TFIELD_INTERNAL_TOKEN_FILE' (Join-Path $local 'service-token')
    $env:TFIELD_PYTHON_URL="http://127.0.0.1:$pythonPort"
    $env:TFIELD_BUSINESS_URL=$base
    Default-Env 'TFIELD_DEPLOYMENT_ID' (Split-Path $Release -Leaf)
    $backend=Join-Path $Release 'backend'
    if ($Mode -eq 'Dev') { $backend=Join-Path $project 'backend'; Remove-Item Env:TFIELD_FRONTEND_DIST -ErrorAction SilentlyContinue }
    else { $env:TFIELD_FRONTEND_DIST=Join-Path $Release 'frontend' }
    $env:PYTHONPATH=Join-Path $backend 'src'
    $logs=Join-Path $local ('runtime/'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-unified')
    New-Item -ItemType Directory -Path $logs | Out-Null
    $services=@()
    try {
        $python=Tool 'PythonExe' 'python'; $java=Tool 'JavaExe' 'java'
        $services+=Launch 'python' $python @('-X','utf8','-m','uvicorn','api.main:app','--host','127.0.0.1','--port',"$pythonPort") $backend 'uvicorn api.main:app' $logs
        $jar=Join-Path $Release 'business.jar'
        $services+=Launch 'java' $java @('-Dfile.encoding=UTF-8','-jar',('"'+$jar+'"')) $project $jar $logs
        $record=@{mode=$Mode;url=$base;release=$Release;logs=$logs;services=$services;config=$Config}
        $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
        $ready=$false
        for ($attempt=0;$attempt -lt 45;$attempt++) {
            foreach ($item in $services) { if (-not (Owned-Process $item)) { throw ($item.name+' 进程已退出，请检查 '+$logs) } }
            try { if ((Api ($base+'/ops/health')).status -eq 'ok') { $ready=$true; break } } catch { }
            Start-Sleep -Milliseconds 1000
        }
        if (-not $ready) { throw ('后端未就绪，请检查 '+$logs) }
        if ($Mode -eq 'Dev') {
            $node=Tool 'NodeExe' 'node'
            $env:TFIELD_API_TARGET=$base
            $services+=Launch 'frontend' $node @('node_modules/vite/bin/vite.js','--host','127.0.0.1') (Join-Path $project 'frontend') 'node_modules/vite/bin/vite.js' $logs
            $record.services=$services; $record.frontend_url='http://127.0.0.1:5173'
            $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
        }
        Show-Status
    } catch {
        foreach ($item in $services) { $p=Owned-Process $item; if ($p) { Stop-Process -Id $p.Id } }
        if (Test-Path -LiteralPath $recordFile) { Remove-Item -LiteralPath $recordFile }
        throw
    }
} finally { if ($lock) { $lock.Dispose() } }
} finally {
    $names=@($savedEnvironment.Keys)+@([Environment]::GetEnvironmentVariables('Process').Keys | Where-Object { $_ -like 'TFIELD_*' -or $_ -eq 'PYTHONPATH' })
    foreach ($name in ($names | Select-Object -Unique)) {
        if ($savedEnvironment.ContainsKey($name)) { [Environment]::SetEnvironmentVariable($name,$savedEnvironment[$name],'Process') }
        else { Remove-Item -LiteralPath ('Env:'+$name) -ErrorAction SilentlyContinue }
    }
}
