Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

projDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
pythonExe = "F:\miniconda3\python.exe"
appScript = projDir & "\app.py"

WshShell.Run """" & pythonExe & """ """ & appScript & """", 1, False
