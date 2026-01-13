#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志监控和分析工具
用于实时监控、搜索和分析应用日志

使用方法:
  python log_monitor.py --watch              # 实时监控日志
  python log_monitor.py --search "错误"      # 搜索关键词
  python log_monitor.py --user 1             # 查看特定用户的日志
  python log_monitor.py --stats              # 显示日志统计
  python log_monitor.py --tail 50            # 显示最后50行日志
"""

import os
import re
import sys
import time
import argparse
from collections import defaultdict
from datetime import datetime, timedelta

class LogMonitor:
    """日志监控类"""
    
    def __init__(self, log_file='app.log'):
        self.log_file = log_file
        self.last_position = 0
        
    def file_exists(self):
        """检查日志文件是否存在"""
        return os.path.exists(self.log_file)
    
    def watch_logs(self):
        """实时监控日志文件"""
        if not self.file_exists():
            print(f"错误: 日志文件 {self.log_file} 不存在")
            return
        
        print(f"开始监控日志文件: {self.log_file}")
        print("按 Ctrl+C 停止监控...\n")
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                # 移到文件末尾
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        print(line.rstrip())
                    else:
                        time.sleep(0.1)  # 等待新日志
        except KeyboardInterrupt:
            print("\n监控已停止")
        except Exception as e:
            print(f"错误: {e}")
    
    def search_logs(self, keyword, case_sensitive=False):
        """搜索日志"""
        if not self.file_exists():
            print(f"错误: 日志文件 {self.log_file} 不存在")
            return
        
        pattern = keyword if case_sensitive else re.compile(keyword, re.IGNORECASE)
        matches = []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    if case_sensitive:
                        if keyword in line:
                            matches.append((i, line.rstrip()))
                    else:
                        if re.search(pattern, line):
                            matches.append((i, line.rstrip()))
        except Exception as e:
            print(f"错误: {e}")
            return
        
        if matches:
            print(f"找到 {len(matches)} 条匹配的日志:\n")
            for line_num, line in matches:
                print(f"{line_num}: {line}")
        else:
            print(f"未找到包含 '{keyword}' 的日志")
    
    def filter_by_user(self, user_id):
        """按用户ID过滤日志"""
        if not self.file_exists():
            print(f"错误: 日志文件 {self.log_file} 不存在")
            return
        
        user_logs = []
        pattern = re.compile(rf"用户(?:ID)?[:\s]+{user_id}")
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    if re.search(pattern, line):
                        user_logs.append((i, line.rstrip()))
        except Exception as e:
            print(f"错误: {e}")
            return
        
        if user_logs:
            print(f"用户 {user_id} 的操作日志 (共 {len(user_logs)} 条):\n")
            for line_num, line in user_logs:
                print(f"{line_num}: {line}")
        else:
            print(f"未找到用户 {user_id} 的日志")
    
    def show_stats(self):
        """显示日志统计"""
        if not self.file_exists():
            print(f"错误: 日志文件 {self.log_file} 不存在")
            return
        
        stats = {
            'total': 0,
            'info': 0,
            'warning': 0,
            'error': 0,
            'operations': defaultdict(int),
            'users': set(),
            'dates': defaultdict(int),
        }
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    stats['total'] += 1
                    
                    if '[INFO]' in line:
                        stats['info'] += 1
                    elif '[WARNING]' in line:
                        stats['warning'] += 1
                    elif '[ERROR]' in line:
                        stats['error'] += 1
                    
                    # 统计操作类型
                    op_match = re.search(r'\[操作\] ([^|]*)\|', line)
                    if op_match:
                        stats['operations'][op_match.group(1).strip()] += 1
                    
                    # 统计用户
                    user_match = re.search(r'用户(?:ID)?[:\s]+(\d+)', line)
                    if user_match:
                        stats['users'].add(int(user_match.group(1)))
                    
                    # 统计日期
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
                    if date_match:
                        stats['dates'][date_match.group(1)] += 1
        except Exception as e:
            print(f"错误: {e}")
            return
        
        # 显示统计信息
        print("=" * 50)
        print("日志统计信息")
        print("=" * 50)
        print(f"\n总日志条数: {stats['total']}")
        print(f"  信息 [INFO]:   {stats['info']}")
        print(f"  警告 [WARNING]: {stats['warning']}")
        print(f"  错误 [ERROR]:  {stats['error']}")
        
        if stats['users']:
            print(f"\n活跃用户数: {len(stats['users'])}")
            print(f"  用户ID: {', '.join(map(str, sorted(stats['users']))[:10])}")
            if len(stats['users']) > 10:
                print(f"  ... 还有 {len(stats['users']) - 10} 个用户")
        
        if stats['operations']:
            print(f"\n操作统计 (Top 10):")
            for op, count in sorted(stats['operations'].items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {op}: {count} 次")
        
        if stats['dates']:
            print(f"\n按日期统计:")
            for date in sorted(stats['dates'].keys(), reverse=True)[:5]:
                print(f"  {date}: {stats['dates'][date]} 条日志")
        
        print("\n" + "=" * 50)
    
    def show_tail(self, lines=20):
        """显示日志末尾的N行"""
        if not self.file_exists():
            print(f"错误: 日志文件 {self.log_file} 不存在")
            return
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            
            start = max(0, len(all_lines) - lines)
            print(f"日志文件末尾 {min(lines, len(all_lines))} 行:\n")
            
            for i, line in enumerate(all_lines[start:], start=start+1):
                print(f"{i}: {line.rstrip()}")
            
            if len(all_lines) == 0:
                print("日志文件为空")
        except Exception as e:
            print(f"错误: {e}")
    
    def find_errors(self):
        """查找所有错误"""
        if not self.file_exists():
            print(f"错误: 日志文件 {self.log_file} 不存在")
            return
        
        errors = []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    if '[ERROR]' in line or '失败' in line or '异常' in line:
                        errors.append((i, line.rstrip()))
        except Exception as e:
            print(f"错误: {e}")
            return
        
        if errors:
            print(f"找到 {len(errors)} 条错误或警告信息:\n")
            for line_num, line in errors[-20:]:  # 显示最后20条
                print(f"{line_num}: {line}")
        else:
            print("未找到错误或警告信息")

def main():
    parser = argparse.ArgumentParser(
        description='日志监控和分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python log_monitor.py --watch              实时监控日志
  python log_monitor.py --search "错误"      搜索包含"错误"的日志
  python log_monitor.py --user 1             查看用户1的日志
  python log_monitor.py --stats              显示日志统计
  python log_monitor.py --tail 50            显示最后50行日志
  python log_monitor.py --errors             查找所有错误
        '''
    )
    
    parser.add_argument('--watch', action='store_true', help='实时监控日志文件')
    parser.add_argument('--search', metavar='关键词', help='搜索日志')
    parser.add_argument('--user', metavar='用户ID', type=int, help='按用户ID过滤日志')
    parser.add_argument('--stats', action='store_true', help='显示日志统计')
    parser.add_argument('--tail', metavar='行数', type=int, nargs='?', const=20, help='显示日志末尾N行')
    parser.add_argument('--errors', action='store_true', help='查找所有错误')
    parser.add_argument('--log-file', default='app.log', help='日志文件路径')
    
    args = parser.parse_args()
    
    monitor = LogMonitor(args.log_file)
    
    # 如果没有指定任何操作，显示帮助
    if not any([args.watch, args.search, args.user is not None, args.stats, args.tail is not None, args.errors]):
        parser.print_help()
        return
    
    # 执行相应的操作
    if args.watch:
        monitor.watch_logs()
    elif args.search:
        monitor.search_logs(args.search)
    elif args.user is not None:
        monitor.filter_by_user(args.user)
    elif args.stats:
        monitor.show_stats()
    elif args.tail is not None:
        monitor.show_tail(args.tail)
    elif args.errors:
        monitor.find_errors()

if __name__ == '__main__':
    main()
