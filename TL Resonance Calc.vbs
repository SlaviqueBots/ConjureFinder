'==============================================================================
'  TL Resonance Calc — personal Torchlight Infinite tool (separate from Conjure Finder).
'  Double-click this file, or use the Desktop shortcut. No console window.
'==============================================================================
Option Explicit

Dim sh, fso, root, bat, vpyw, vpy, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
bat = root & "\TL Resonance Calc.bat"
vpyw = root & "\venv\Scripts\pythonw.exe"
vpy = root & "\venv\Scripts\python.exe"

If Not fso.FileExists(bat) Then
  MsgBox "Missing:" & vbCrLf & bat, vbCritical, "TL Resonance Calc"
  WScript.Quit 1
End If

sh.CurrentDirectory = root

If Not fso.FileExists(vpy) Then
  rc = sh.Run("cmd /c """ & bat & """", 1, True)
  WScript.Quit rc
End If

If fso.FileExists(vpyw) Then
  sh.Run """" & vpyw & """ -m tl_resonance", 1, False
Else
  sh.Run """" & vpy & """ -m tl_resonance", 1, False
End If
