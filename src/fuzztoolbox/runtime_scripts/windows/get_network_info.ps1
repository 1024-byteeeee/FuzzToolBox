$configuration = Get-NetIPConfiguration |
    Where-Object { $_.IPv4DefaultGateway -and $_.IPv4Address } |
    Select-Object -First 1

if ($configuration) {
    $address = $configuration.IPv4Address | Select-Object -First 1
    $macAddress = (Get-NetAdapter -InterfaceIndex $configuration.InterfaceIndex).MacAddress
    $values = @(
        $configuration.InterfaceAlias
        $address.IPAddress
        $address.PrefixLength
        $configuration.IPv4DefaultGateway.NextHop
        $macAddress
    )
    Write-Output ($values -join '|')
}
