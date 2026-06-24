Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Paths
pythonExe = "F:\miniconda3\python.exe"
projDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
appScript = projDir & "\app.py"

' Check if already running
alreadyRunning = False
On Error Resume Next
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set procs = wmi.ExecQuery("SELECT CommandLine FROM Win32_Process WHERE Name='python.exe'")
For Each proc In procs
    If InStr(proc.CommandLine, "app.py") > 0 Then
        alreadyRunning = True
        Exit For
    End If
Next
On Error Goto 0

If Not alreadyRunning Then
    ' Load .env
    Dim envFile, envShell, line, eqPos, content
    envFile = projDir & "\.env"
    If objFSO.FileExists(envFile) Then
        Set envShell = CreateObject("WScript.Shell").Environment("Process")
        Set content = objFSO.OpenTextFile(envFile, 1)
        Do Until content.AtEndOfStream
            line = Trim(content.ReadLine)
            If Len(line) > 0 And Left(line, 1) <> "#" Then
                eqPos = InStr(line, "=")
                If eqPos > 0 Then
                    envShell(Left(line, eqPos - 1)) = Mid(line, eqPos + 1)
                End If
            End If
        Loop
        content.Close
    End If

    ' Start the app
    WshShell.Run """" & pythonExe & """ """ & appScript & """", 1, False
End If
