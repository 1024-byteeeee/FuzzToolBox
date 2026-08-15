$computer = Get-CimInstance Win32_ComputerSystem
$processor = Get-CimInstance Win32_Processor | Select-Object -First 1
$graphics = @(Get-CimInstance Win32_VideoController | ForEach-Object {
    [PSCustomObject]@{
        Name = $_.Name
        AdapterRAM = $_.AdapterRAM
        DriverVersion = $_.DriverVersion
    }
})
[PSCustomObject]@{
    Manufacturer = $computer.Manufacturer
    Model = $computer.Model
    CPU = $processor.Name
    GPU = $graphics
} | ConvertTo-Json -Depth 4 -Compress
