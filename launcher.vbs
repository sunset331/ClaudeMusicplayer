Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Kill existing process on port 8765
WshShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -ano ^| findstr :8765') do taskkill /pid %a /f >nul 2>&1", 0, True

' Start Python server (hidden)
projDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = projDir
WshShell.Run "pythonw.exe backend\server.py", 0, False

' Wait for server to be ready
For i = 1 To 15
    WScript.Sleep 1000
    On Error Resume Next
    Dim http: Set http = CreateObject("MSXML2.ServerXMLHTTP")
    http.Open "GET", "http://localhost:8765/api/status", False
    http.Send
    If http.Status = 200 Then Exit For
    On Error Goto 0
Next

' Open browser in app mode
WScript.Sleep 500
chrome = WshShell.ExpandEnvironmentStrings("%ProgramFiles%") & "\Google\Chrome\Application\chrome.exe"
chrome86 = WshShell.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Google\Chrome\Application\chrome.exe"
edge = WshShell.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe"

If objFSO.FileExists(chrome) Then
    WshShell.Run """" & chrome & """ --app=http://localhost:8765 --window-size=1200,800"
ElseIf objFSO.FileExists(chrome86) Then
    WshShell.Run """" & chrome86 & """ --app=http://localhost:8765 --window-size=1200,800"
ElseIf objFSO.FileExists(edge) Then
    WshShell.Run """" & edge & """ --app=http://localhost:8765 --window-size=1200,800"
Else
    WshShell.Run "http://localhost:8765"
End If
