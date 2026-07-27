'==============================================================================
'  Conjure Finder — double-click THIS file on Windows (share build).
'  First run may flash a setup window briefly; after that it opens silently.
'==============================================================================
Option Explicit

Dim sh, fso, root, bat, marker, needSetup, vpyw, vpy, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
bat = root & "\Conjure Finder.bat"
marker = root & "\venv\.conjure_finder_deps_ok"
vpyw = root & "\venv\Scripts\pythonw.exe"
vpy = root & "\venv\Scripts\python.exe"

If Not fso.FileExists(bat) Then
  MsgBox "Missing:" & vbCrLf & bat, vbCritical, "Conjure Finder"
  WScript.Quit 1
End If

sh.CurrentDirectory = root
needSetup = Not fso.FileExists(marker)

If needSetup Then
  MsgBox "First-time setup: will install Python packages." & vbCrLf & _
    "A console window will open — wait until it finishes." & vbCrLf & vbCrLf & _
    "Then use Settings… inside the app to add your Danbooru / Rule34 API keys.", _
    vbInformation, "Conjure Finder"
  rc = sh.Run("cmd /c """ & bat & """ --setup-only", 1, True)
  If rc <> 0 Or Not fso.FileExists(marker) Then
    MsgBox "Setup failed. Run ""Conjure Finder.bat"" instead and read the error text.", _
      vbCritical, "Conjure Finder"
    WScript.Quit 1
  End If
End If

If fso.FileExists(vpyw) Then
  sh.Run """" & vpyw & """ -m conjure_finder", 1, False
ElseIf fso.FileExists(vpy) Then
  sh.Run """" & vpy & """ -m conjure_finder", 1, False
Else
  MsgBox "Python venv missing after setup. Run ""Conjure Finder.bat"".", vbCritical, "Conjure Finder"
  WScript.Quit 1
End If
