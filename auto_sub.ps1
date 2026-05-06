param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Url,

    [switch]$Summarize,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Error "Python was not found in PATH."
    exit 1
}

$pythonArgs = @("$ScriptDir\bili_groq.py", $Url, "--pdf")
if ($Summarize) {
    $pythonArgs += "--summarize"
}
if ($ExtraArgs) {
    $pythonArgs += $ExtraArgs
}

& $pythonCmd.Source @pythonArgs
exit $LASTEXITCODE
