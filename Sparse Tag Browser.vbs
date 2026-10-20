'==============================================================================
'  Sparse Tag Browser — personal tool (separate from Conjure Finder).
'  Double-click this file, or use the Desktop shortcut.
'==============================================================================
Option Explicit

Dim sh, fso, root, bat, marker, vpyw, vpy, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
bat = root & "\Sparse Tag Browser.bat"
marker = root & "\venv\.sparse_tags_deps_ok"
vpyw = root & "\venv\Scripts\pythonw.exe"
vpy = root & "\venv\Scripts\python.exe"

If Not fso.FileExists(bat) Then
  MsgBox "Missing:" & vbCrLf & bat, vbCritical, "Sparse Tag Browser"
  WScript.Quit 1
End If

sh.CurrentDirectory = root

If Not fso.FileExists(vpy) Then
  rc = sh.Run("cmd /c """ & bat & """", 1, True)
  WScript.Quit rc
End If

' Deps already in this venv (httpx/dotenv) — mark ready and launch without pip.exe.
If Not fso.FileExists(marker) Then
  Dim ts
  Set ts = fso.CreateTextFile(marker, True)
  ts.WriteLine "ok"
  ts.Close
End If

If fso.FileExists(vpyw) Then
  sh.Run """" & vpyw & """ -m sparse_tags", 1, False
Else
  sh.Run """" & vpy & """ -m sparse_tags", 1, False
End If
