param(
    [ValidateSet("up", "down", "logs")]
    [string]$Action = "up"
)

$composeFiles = @("-f", "compose.yaml", "-f", "compose.spiders.yaml")

if ($Action -eq "up") {
    docker compose @composeFiles up -d --no-build --force-recreate api
    exit $LASTEXITCODE
}

if ($Action -eq "down") {
    docker compose @composeFiles down
    exit $LASTEXITCODE
}

docker compose @composeFiles logs -f api
