Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

projDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
pythonExe = "F:\miniconda3\python.exe"

' Check if server already running
serverRunning = False
On Error Resume Next
Dim http: Set http = CreateObject("MSXML2.ServerXMLHTTP")
http.Open "GET", "http://localhost:8765/api/status", False
http.Send
If Err.Number = 0 And http.Status = 200 Then serverRunning = True
On Error Goto 0

If Not serverRunning Then
    ' Kill stale processes on port 8765
    WshShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -ano ^| findstr :8765') do taskkill /pid %a /f >nul 2>&1", 0, True
    ' Start Python server (hidden)
    WshShell.Run """" & pythonExe & """ """ & projDir & "\backend\server.py""", 0, False
    ' Wait for ready
    For i = 1 To 15
        WScript.Sleep 1000
        Err.Clear
        On Error Resume Next
        Dim http2: Set http2 = CreateObject("MSXML2.ServerXMLHTTP")
        http2.Open "GET", "http://localhost:8765/api/status", False
        http2.Send
        If Err.Number = 0 And http2.Status = 200 Then Exit For
        On Error Goto 0
    Next
End If

' Open browser (always — focus existing if possible, or open new)
WScript.Sleep 300
chrome = WshShell.ExpandEnvironmentStrings("%ProgramFiles%") & "\Google\Chrome\Application\chrome.exe"
edge = WshShell.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe"

If objFSO.FileExists(chrome) Then
    WshShell.Run """" & chrome & """ --app=http://localhost:8765 --window-size=1200,800"
ElseIf objFSO.FileExists(edge) Then
    WshShell.Run """" & edge & """ --app=http://localhost:8765 --window-size=1200,800"
Else
    WshShell.Run "http://localhost:8765"
End If
