$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
java -jar "$SCRIPT_DIR\copybara_deploy.jar" $args
