@echo off
setlocal EnableExtensions
REM HoYoProtect blocks taskkill; TerminateProcess with PROCESS_TERMINATE only still works.
powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='SilentlyContinue';" ^
  "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class N { [DllImport(\"kernel32.dll\", SetLastError=true)] public static extern IntPtr OpenProcess(uint a, bool i, int p); [DllImport(\"kernel32.dll\", SetLastError=true)] public static extern bool TerminateProcess(IntPtr h, uint c); [DllImport(\"kernel32.dll\", SetLastError=true)] public static extern bool CloseHandle(IntPtr h); }';" ^
  "foreach ($n in @('GenshinImpact','YuanShen')) {" ^
  "  Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object {" ^
  "    $h = [N]::OpenProcess(0x0001, $false, $_.Id);" ^
  "    if ($h -ne [IntPtr]::Zero) { [void][N]::TerminateProcess($h, 1); [void][N]::CloseHandle($h) }" ^
  "  }" ^
  "}"
exit /b 0
