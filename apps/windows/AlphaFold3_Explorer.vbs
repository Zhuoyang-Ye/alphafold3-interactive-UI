Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = scriptDir
WshShell.Run Chr(34) & scriptDir & "\AlphaFold3_Explorer.bat" & Chr(34), 1
Set WshShell = Nothing
Set fso = Nothing
