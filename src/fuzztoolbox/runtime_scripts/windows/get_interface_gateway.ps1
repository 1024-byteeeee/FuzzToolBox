param(
    [Parameter(Mandatory = $true)]
    [string] $InterfaceAlias
)

$configuration = Get-NetIPConfiguration `
    -InterfaceAlias $InterfaceAlias `
    -ErrorAction SilentlyContinue

if ($configuration.IPv4DefaultGateway) {
    Write-Output $configuration.IPv4DefaultGateway.NextHop
}
