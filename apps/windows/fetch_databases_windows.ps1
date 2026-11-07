# Automated Database Fetcher for Windows
# Usage: powershell -ExecutionPolicy Bypass -File .\fetch_databases_windows.ps1 [[-TargetDir] "D:\AlphaFold3_Databases"]

param (
    [string]$TargetDir = "$env:USERPROFILE\public_databases"
)

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "         AlphaFold 3 Database Downloader for Windows" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Target Directory: $TargetDir" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
}

$Source = "https://storage.googleapis.com/alphafold-databases/v3.0"

$Files = @(
    "pdb_2022_09_28_mmcif_files.tar.zst",
    "mgy_clusters_2022_05.fa.zst",
    "bfd-first_non_consensus_sequences.fasta.zst",
    "uniref90_2022_05.fa.zst",
    "uniprot_all_2021_04.fa.zst",
    "pdb_seqres_2022_09_28.fasta.zst",
    "rnacentral_active_seq_id_90_cov_80_linclust.fasta.zst",
    "nt_rna_2023_02_23_clust_seq_id_90_cov_80_rep_seq.fasta.zst",
    "rfam_14_9_clust_seq_id_90_cov_80_rep_seq.fasta.zst"
)

# Check available disk space
$Drive = (Get-Item $TargetDir).PSDrive
$FreeGB = [math]::Round($Drive.Free / 1GB, 1)
Write-Host "Available disk space on $($Drive.Name): $FreeGB GB" -ForegroundColor Cyan
if ($FreeGB -lt 650) {
    Write-Host "[WARNING] Recommended disk space is >= 650 GB for full uncompressed databases." -ForegroundColor Red
    Write-Host "If you have an external SSD with more space, pass its path like:" -ForegroundColor Yellow
    Write-Host ".\fetch_databases_windows.ps1 -TargetDir D:\public_databases" -ForegroundColor Yellow
    Write-Host ""
}

foreach ($File in $Files) {
    $Dest = Join-Path $TargetDir $File
    $Url = "$Source/$File"
    if (Test-Path $Dest) {
        Write-Host "[SKIP] $File already exists." -ForegroundColor Gray
        continue
    }
    Write-Host "[DOWNLOADING] $File ..." -ForegroundColor Green
    try {
        Start-BitsTransfer -Source $Url -Destination $Dest -DisplayName "AlphaFold3: $File" -Priority Foreground
    } catch {
        Write-Host "BITS failed, falling back to WebRequest..." -ForegroundColor Yellow
        Invoke-WebRequest -Uri $Url -OutFile $Dest
    }
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host "Downloads Finished! Decompressing .zst files..." -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Green

# Check for zstd
if (Get-Command zstd -ErrorAction SilentlyContinue) {
    foreach ($File in $Files) {
        $Compressed = Join-Path $TargetDir $File
        Write-Host "Decompressing $File ..." -ForegroundColor Yellow
        & zstd -d --rm $Compressed
    }
} else {
    Write-Host "zstd is not in PATH. Please install zstd (e.g. 'winget install facebook.zstd') to unpack .zst archives." -ForegroundColor Yellow
}

Write-Host "Database preparation complete in $TargetDir" -ForegroundColor Green
