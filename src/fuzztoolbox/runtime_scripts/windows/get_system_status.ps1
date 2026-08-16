# Win32_Processor.LoadPercentage 直接读取系统性能计数器，
# 避免依赖进程内采样差值导致 CPU 使用率始终为 0% 的问题。
# 同时返回各盘符卷标，供磁盘列表显示友好名称。
$load = @(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$volumes = @(Get-Volume | Where-Object { $_.DriveLetter } | ForEach-Object {
    [PSCustomObject]@{
        DriveLetter = "$($_.DriveLetter):"
        Label = $_.FileSystemLabel
    }
})
[PSCustomObject]@{
    LoadPercentage = [math]::Round([double]$load, 1)
    Volumes = $volumes
} | ConvertTo-Json -Depth 4 -Compress
