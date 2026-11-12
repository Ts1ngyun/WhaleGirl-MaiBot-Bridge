$ErrorActionPreference='Stop'
$path=Join-Path $PSScriptRoot 'data\image-policy.json'
try {
    $current=if(Test-Path $path){(Get-Content $path -Raw | ConvertFrom-Json).mode}else{'request'}
    Write-Host "当前模式：$current"
    Write-Host '1. 自动识别普通图片（不识别表情包）'
    Write-Host '2. 仅 /识图 后 60 秒内的下一张普通图片'
    Write-Host '3. 关闭图片识别'
    Write-Host '其他输入：不修改'
    $choice=Read-Host '请选择 1 / 2 / 3'
    $mode=switch($choice){'1'{'auto'} '2'{'request'} '3'{'off'} default{''}}
    if($mode){
        $temp="$path.tmp"
        @{mode=$mode} | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding utf8
        Move-Item -LiteralPath $temp -Destination $path -Force
        Write-Host '已保存。新桥接模块首次安装需重连一次；之后修改即时生效。'
    }
} catch {Write-Host $_.Exception.Message -ForegroundColor Red;exit 1}
