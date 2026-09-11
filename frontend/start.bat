@echo off
echo ========================================
echo   AudioInsight 前端开发服务器
echo ========================================
echo.
echo 正在启动 HTTP 服务器...
echo 访问地址: http://localhost:8080
echo.
echo 按 Ctrl+C 停止服务器
echo.
echo ========================================

cd /d "%~dp0"
python -m http.server 8080
