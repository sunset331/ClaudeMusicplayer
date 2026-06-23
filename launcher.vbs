Set WshShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

projDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
pythonExe = "F:\miniconda3\python.exe"
serverScript = projDir & "\backend\server.py"

' Check if server already running
serverRunning = False
On Error Resume Next
Dim http: Set http = CreateObject("MSXML2.ServerXMLHTTP")
http.Open "GET", "http://localhost:8765/api/queue", False
http.SetTimeouts 3000, 3000, 3000, 3000
http.Send
If Err.Number = 0 And http.Status = 200 Then serverRunning = True
On Error Goto 0

If Not serverRunning Then
    ' Start Python backend server
    WshShell.Run """" & pythonExe & """ """ & serverScript & """", 0, False

    ' Wait up to 30 seconds for server to be ready
    For i = 1 To 30
        WScript.Sleep 1000
        Err.Clear
        On Error Resume Next
        Dim http2: Set http2 = CreateObject("MSXML2.ServerXMLHTTP")
        http2.Open "GET", "http://localhost:8765/api/queue", False
        http2.SetTimeouts 2000, 2000, 2000, 2000
        http2.Send
        If Err.Number = 0 And http2.Status = 200 Then Exit For
        On Error Goto 0
    Next
End If

WScript.Sleep 500

' Launch in app mode — no browser chrome, looks like native window
chrome = WshShell.ExpandEnvironmentStrings("%LocalAppData%") & "\Google\Chrome\Application\chrome.exe"
edge = WshShell.ExpandEnvironmentStrings("%ProgramFiles(x86)%") & "\Microsoft\Edge\Application\msedge.exe"

Dim browserExe, foundBrowser
foundBrowser = False

' Check Edge first (it's installed), then Chrome, then all common paths
Dim browsers(4)
browsers(0) = edge
browsers(1) = chrome
browsers(2) = "C:\Program Files\Google\Chrome\Application\chrome.exe"
browsers(3) = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

For i = 0 To 3
    If objFSO.FileExists(browsers(i)) Then
        browserExe = browsers(i)
        foundBrowser = True
        Exit For
    End If
Next

If foundBrowser Then
    WshShell.Run """" & browserExe & """ --app=http://localhost:8765 --window-size=1200,800"
Else
    WshShell.Run "http://localhost:8765"
End If
