Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

projDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
pythonExe = "F:\miniconda3\python.exe"
appScript = projDir & "\app.py"

' Check if already running by window title
Set objWMIService = GetObject("winmgmts:\\.\root\cimv2")
Set colProcesses = objWMIService.ExecQuery("SELECT * FROM Win32_Process WHERE Name='python.exe'")

isRunning = False
For Each proc In colProcesses
    If InStr(1, proc.CommandLine, "app.py", vbTextCompare) > 0 Then
        isRunning = True
        Exit For
    End If
Next

If Not isRunning Then
    WshShell.Run """" & pythonExe & """ """ & appScript & """", 1, False
End If
