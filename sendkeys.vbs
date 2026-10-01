' sendkeys.vbs - types its first argument into the window that has keyboard
' focus. Run with: cscript.exe //nologo sendkeys.vbs "text"
Dim sh, txt, i, ch, out
Set sh = CreateObject("WScript.Shell")
txt = WScript.Arguments(0)
out = ""
For i = 1 To Len(txt)
    ch = Mid(txt, i, 1)
    If ch = "{" Then
        out = out + "{{}"
    ElseIf ch = "}" Then
        out = out + "{}}"
    Else
        out = out + ch
    End If
Next
sh.SendKeys out
