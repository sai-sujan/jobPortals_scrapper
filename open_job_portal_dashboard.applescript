set dashboardUrl to "http://127.0.0.1:8766"
set projectDir to (POSIX path of (path to home folder)) & "Desktop/jobs_scraping"
set logDir to projectDir & "/logs"
set logFile to logDir & "/dashboard_server.log"
set venvPython to projectDir & "/.venv/bin/python3"

do shell script "mkdir -p " & quoted form of logDir
set pythonCmd to "python3"
try
	do shell script "test -x " & quoted form of venvPython
	set pythonCmd to quoted form of venvPython
on error
	try
		do shell script "test -x /opt/anaconda3/bin/python3"
		set pythonCmd to quoted form of "/opt/anaconda3/bin/python3"
	end try
end try

try
	do shell script "curl -fsS --max-time 2 " & quoted form of (dashboardUrl & "/api/status") & " >/dev/null"
on error
	do shell script "cd " & quoted form of projectDir & " && nohup " & pythonCmd & " job_portal_dashboard.py --port 8766 > " & quoted form of logFile & " 2>&1 &"
	repeat 20 times
		try
			do shell script "curl -fsS --max-time 1 " & quoted form of (dashboardUrl & "/api/status") & " >/dev/null"
			exit repeat
		on error
			delay 0.5
		end try
	end repeat
end try

open location dashboardUrl
