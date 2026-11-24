[CmdletBinding()]
param(
    [ValidateSet('Dev','Deploy')][string]$Mode='Dev',
    [switch]$CheckOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$configPath=Join-Path $project '.local/system.local.json'
$recordPath=Join-Path $project '.local/system-processes.json'
$releasePath=Join-Path $project '.local/current-release.json'
$systemScript=Join-Path $PSScriptRoot 'system.ps1'
$settings=$null
if (Test-Path -LiteralPath $configPath) {
    $settings=Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Setting([string]$Name,[string]$Fallback) {
    if ($settings -and $settings.Environment) {
        $property=$settings.Environment.PSObject.Properties[$Name]
        if ($property -and [string]$property.Value) { return [string]$property.Value }
    }
    $value=[Environment]::GetEnvironmentVariable($Name,'Process')
    if ($value) { return $value }
    return $Fallback
}

function Require-Tool([string]$Name,[string]$Fallback) {
    $value=$Fallback
    if ($settings -and $settings.PSObject.Properties[$Name] -and $settings.$Name) {
        $value=[string]$settings.$Name
    }
    if (-not (Get-Command $value -ErrorAction SilentlyContinue)) {
        throw "找不到 $Name。请安装运行环境，并检查 .local/system.local.json 中的路径。"
    }
    Write-Host "  $Name 已找到" -ForegroundColor DarkGray
}

function Port-Open([string]$ServerName,[int]$Port) {
    $client=New-Object Net.Sockets.TcpClient
    try {
        $task=$client.ConnectAsync($ServerName,$Port)
        return ($task.Wait(1200) -and $client.Connected)
    } catch { return $false } finally { $client.Dispose() }
}

function Ensure-Database {
    $serverName=Setting 'TFIELD_MYSQL_HOST' '127.0.0.1'
    $port=[int](Setting 'TFIELD_MYSQL_PORT' '3306')
    $jdbc=Setting 'TFIELD_JDBC_URL' ''
    if ($jdbc) {
        if (-not $jdbc.StartsWith('jdbc:mysql://')) { throw '无法识别 TFIELD_JDBC_URL，请检查 MySQL 连接地址。' }
        $address=[uri]$jdbc.Substring(5)
        $serverName=$address.Host
        $port=3306
        if ($address.Port -gt 0) { $port=$address.Port }
    }
    if (Port-Open $serverName $port) {
        Write-Host "  数据库端口可连接：${serverName}:$port" -ForegroundColor Green
        return
    }
    if ($CheckOnly) { throw "数据库端口无法连接：${serverName}:$port。检查模式不会启动服务。" }
    if ($serverName -notin @('127.0.0.1','localhost','::1',[Environment]::MachineName)) {
        throw '远程数据库无法连接，请先检查数据库地址和网络。'
    }
    $serviceName=Setting 'TFIELD_MYSQL_SERVICE' 'MySQL80'
    try {
        $service=Get-Service -Name $serviceName -ErrorAction Stop
        if ($service.Status -ne 'Running') {
            Write-Host "  正在启动数据库服务 $serviceName …"
            Start-Service -Name $serviceName -ErrorAction Stop
        }
    } catch {
        throw "无法启动数据库服务 $serviceName。请在管理员 PowerShell 中运行 Start-Service -Name '$serviceName'，然后重新双击启动入口。服务名不同时可在本机配置的 Environment 中设置 TFIELD_MYSQL_SERVICE。"
    }
    for ($attempt=0;$attempt -lt 15;$attempt++) {
        if (Port-Open $serverName $port) { Write-Host '  数据库端口已就绪' -ForegroundColor Green; return }
        Start-Sleep -Seconds 1
    }
    throw "数据库服务已检查，但 ${serverName}:$port 仍无法连接。请核对数据库端口。"
}

function Wait-Page([string]$Url) {
    for ($attempt=0;$attempt -lt 30;$attempt++) {
        try {
            $response=Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Seconds 1
    }
    throw '前端页面未就绪，请查看上方运行记录中的 logs 目录。'
}

function Start-AssistantServices {
    $serviceRoot=Join-Path $project '.local/assistant/services'
    if (-not (Test-Path -LiteralPath (Join-Path $serviceRoot 'installation.json'))) {
        Write-Host '  未安装本地知识服务；助手知识检索需按文档另行配置。' -ForegroundColor DarkYellow
        return
    }
    try {
        $processFile=Join-Path $serviceRoot 'processes.json'
        if (Test-Path -LiteralPath $processFile) {
            $records=@(Get-Content -LiteralPath $processFile -Raw -Encoding UTF8 | ConvertFrom-Json)
            $active=@($records | Where-Object {
                $process=Get-Process -Id $_.pid -ErrorAction SilentlyContinue
                $process -and $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $_.started
            })
            if ($active.Count -gt 0) {
                if ($active.Count -eq $records.Count) { Write-Host '  已复用助手知识服务进程' }
                else { Write-Warning '助手知识服务只有部分进程运行，请用 scripts/assistant-services.ps1 Status 检查。' }
                return
            }
            & (Join-Path $PSScriptRoot 'assistant-services.ps1') Stop
        }
        & (Join-Path $PSScriptRoot 'assistant-services.ps1') Start
        Write-Host '  助手知识服务已提交启动；嵌入模型冷启动需要一些时间。'
    } catch {
        Write-Warning ('助手知识服务启动未完成：'+$_.Exception.Message+'。核心前后端继续启动；日志位于 .local/assistant/services。')
    }
}

try {
    Write-Host '棚式空间温度场系统启动入口' -ForegroundColor Cyan
    Write-Host "项目目录：$project"
    Write-Host "启动模式：$Mode"
    Write-Host '[1/4] 检查运行环境与数据库'
    Require-Tool 'PythonExe' 'python'
    Require-Tool 'JavaExe' 'java'
    if ($Mode -eq 'Dev') {
        Require-Tool 'NodeExe' 'node'
        if (-not (Test-Path -LiteralPath (Join-Path $project 'frontend/node_modules/vite/bin/vite.js'))) {
            throw '缺少前端依赖。请进入 frontend 目录执行 npm ci，然后重新启动。'
        }
    }
    Ensure-Database
    if ($CheckOnly) {
        Write-Host '环境检查通过。检查模式未启动服务、构建发布包或打开浏览器。' -ForegroundColor Green
        return
    }

    Write-Host '[2/4] 检查现有运行记录'
    $status=$null
    if (Test-Path -LiteralPath $recordPath) {
        $status=(& $systemScript Status -Config $configPath | Out-String) | ConvertFrom-Json
        $active=@($status.services | Where-Object { $_.running })
        if ($active.Count -gt 0) {
            if ($active.Count -ne $status.services.Count -or $status.health -ne 'ok') {
                throw '已有服务仅部分运行或后端未就绪。请先用 scripts/system.ps1 Status 检查；确认没有训练任务后停止原服务，再重新启动。'
            }
            Write-Host '  前后端已正常运行，复用当前实例。' -ForegroundColor Green
        } else {
            # 原入口会再核对 PID、启动时刻与命令标记，只清理已退出的托管记录。
            & $systemScript Stop -Config $configPath -Force
            $status=$null
        }
    }

    if (-not $status) {
        $needsBuild=-not (Test-Path -LiteralPath $releasePath)
        if (-not $needsBuild) {
            $release=(Get-Content -LiteralPath $releasePath -Raw -Encoding UTF8 | ConvertFrom-Json).path
            $jar=Join-Path $release 'business.jar'
            $needsBuild=-not (Test-Path -LiteralPath $jar)
            if (-not $needsBuild) {
                $jarTime=(Get-Item -LiteralPath $jar).LastWriteTimeUtc
                $newer=@(Get-ChildItem -LiteralPath (Join-Path $project 'backend-java/src/main') -Recurse -File | Where-Object { $_.LastWriteTimeUtc -gt $jarTime })
                $needsBuild=$newer.Count -gt 0 -or (Get-Item -LiteralPath (Join-Path $project 'backend-java/pom.xml')).LastWriteTimeUtc -gt $jarTime
            }
        }
        if ($needsBuild) {
            Write-Host '  发布包缺失或 Java 源文件较新，正在构建，首次运行可能需要几分钟。'
            & $systemScript Build -Config $configPath
        }
    }

    Write-Host '[3/4] 启动后端、前端与已安装的助手知识服务'
    Start-AssistantServices
    if (-not $status) { & $systemScript Start -Mode $Mode -Config $configPath }
    $record=Get-Content -LiteralPath $recordPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $page=$record.url
    if ($record.frontend_url) { $page=$record.frontend_url }
    Wait-Page $page

    Write-Host '[4/4] 启动完成' -ForegroundColor Green
    Write-Host "前端页面：$page"
    Write-Host ('业务后端：'+$record.url)
    Write-Host ('运行日志：'+$record.logs)
    Write-Host '关闭本窗口不会停止后台服务。'
    Write-Host '停止命令：powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\system.ps1 Stop'
    if (-not $NoBrowser) { Start-Process -FilePath ($page+'/live') -WindowStyle Hidden | Out-Null }
} catch {
    Write-Host ''
    Write-Host ('启动未完成：'+$_.Exception.Message) -ForegroundColor Red
    Write-Host '配置文件：.local/system.local.json；运行日志：.local/runtime'
    exit 1
}
