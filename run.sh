#!/bin/bash
echo "Đang khởi động bot forwarding..."
nohup python3 forwarder.py > forward.log 2>&1 &
nohup python3 bot_control.py > bot.log 2>&1 &
nohup python3 schedule.py > schedule.log 2>&1 &
echo "Bot đã chạy!"
