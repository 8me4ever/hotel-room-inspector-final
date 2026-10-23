@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 见净 - 客房交付检查 Demo
echo 电脑打开 http://127.0.0.1:8766/
echo 如该地址已运行，请直接使用，不要重复启动。
echo 手机同一Wi-Fi连接；电脑 我的 - 手机访问 查看地址和配对码。
echo 保留本窗口以维持后台服务。
where py >nul 2>nul
if not errorlevel 1 (
  py -3 server.py --port 8766 --lan
  goto done
)
where python >nul 2>nul
if not errorlevel 1 (
  python server.py --port 8766 --lan
  goto done
)
echo 请先安装 Python 3.10 或以上版本。
:done
pause
