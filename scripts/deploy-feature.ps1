param(
    [Parameter(Mandatory = $true)][string]$RuntimeDirectory,
    [switch]$FreshRuntime
)
$ErrorActionPreference = 'Stop'
$sourceDirectory = Split-Path -Parent $PSScriptRoot
$runtimePath = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$environmentFile = Join-Path $runtimePath '.env'
if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) { throw 'Runtime .env is required' }
$revision = (git -C $sourceDirectory rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve feature revision' }
$pending = git -C $sourceDirectory status --porcelain
if ($pending) { throw 'Commit the reviewed feature snapshot before deployment' }
$env:BACKEND_IMAGE = "cahy-wiki-backend:quality-261022-$($revision.Substring(0, 8))"
$env:FRONTEND_IMAGE = "cahy-wiki-frontend:quality-261022-$($revision.Substring(0, 8))"
$backendDockerfile = if ($FreshRuntime) { 'Dockerfile' } else { 'Dockerfile.runtime' }
if (-not $FreshRuntime) {
    $runtimeBase = docker inspect cahy-wiki-backend:runtime-d489956adcf5 --format '{{.Id}}'
    if ($LASTEXITCODE -ne 0 -or $runtimeBase.Trim() -ne 'sha256:d489956adcf5b4993420db521ec541560cd696f1d2cce0d1d2614681e4774540') {
        throw 'Verified runtime base unavailable; use -FreshRuntime to build pinned dependencies'
    }
}
docker build -f (Join-Path $sourceDirectory $backendDockerfile) --build-arg "BUILD_REVISION=$revision" -t $env:BACKEND_IMAGE $sourceDirectory
if ($LASTEXITCODE -ne 0) { throw 'Backend build failed' }
docker build --build-arg "BUILD_REVISION=$revision" --build-arg NEXT_PUBLIC_API_URL= --build-arg INTERNAL_API_URL=http://api:5055 -t $env:FRONTEND_IMAGE (Join-Path $sourceDirectory 'frontend')
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
# Keep the existing temp-upload bind directory and named durable volumes.
docker compose --project-directory $runtimePath --env-file $environmentFile -f (Join-Path $sourceDirectory 'docker-compose.yml') up -d --no-build api worker worker_skills frontend
if ($LASTEXITCODE -ne 0) { throw 'Runtime deployment failed' }
foreach ($container in @('cahy_wiki_api', 'cahy_wiki_worker', 'cahy_wiki_worker_skills', 'cahy_wiki_frontend')) {
    $actual = docker inspect $container --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'
    if ($LASTEXITCODE -ne 0 -or $actual.Trim() -ne $revision) { throw "Revision mismatch: $container" }
}
Write-Output "Deployed revision $revision"
