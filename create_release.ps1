$token = $env:GITHUB_TOKEN  # Đặt biến môi trường GITHUB_TOKEN trước khi chạy script này
$headers = @{
    Authorization = "token $token"
    Accept        = "application/vnd.github+json"
}

# 1. Tao Release
$releaseBody = [ordered]@{
    tag_name   = "v1.0.0"
    name       = "v1.0.0 - Bo Cong cu Tien ich"
    body       = @"
## Bo Cong cu Xu ly Anh & PDF v1.0.0

### Tinh nang:
- Xu ly Anh: Resize anh hang loat theo pixel hoac phan tram, giu nguyen ten file
- Cong cu PDF: Mo PDF, keo chuot chon vung cat, gop nhieu vung thanh 1 trang PDF
- In PDF: In truc tiep tu ung dung

### Cach dung:
1. Tai file BoConCuTienIch.exe ve
2. Chay thang - khong can cai Python
"@
    draft      = $false
    prerelease = $false
}

$releaseJson = $releaseBody | ConvertTo-Json -Depth 3
$releaseResponse = Invoke-RestMethod `
    -Uri "https://api.github.com/repos/donkma93/bocongcu/releases" `
    -Method POST `
    -Headers $headers `
    -Body $releaseJson `
    -ContentType "application/json; charset=utf-8"

Write-Host "Release tao thanh cong! ID: $($releaseResponse.id)"
Write-Host "URL: $($releaseResponse.html_url)"

# 2. Upload file .exe
$uploadUrlBase = $releaseResponse.upload_url -replace '\{.*\}', ''
$exePath = "dist\BoConCuTienIch.exe"
$exeName = "BoConCuTienIch.exe"
$uploadUrl = "$uploadUrlBase`?name=$exeName"

Write-Host "Dang upload $exeName ..."

$uploadHeaders = @{
    Authorization = "token $token"
    Accept        = "application/vnd.github+json"
    "Content-Type" = "application/octet-stream"
}

$exeBytes = [System.IO.File]::ReadAllBytes((Resolve-Path $exePath))
$uploadResponse = Invoke-RestMethod `
    -Uri $uploadUrl `
    -Method POST `
    -Headers $uploadHeaders `
    -Body $exeBytes

Write-Host "Upload thanh cong! Download URL: $($uploadResponse.browser_download_url)"
