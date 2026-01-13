#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志系统测试脚本
测试日志系统的各项功能

运行: python test_logging.py
"""

import os
import sys
import logging
import tempfile
from pathlib import Path

def test_logging_setup():
    """测试日志系统设置"""
    print("=" * 60)
    print("测试日志系统")
    print("=" * 60)
    
    # 创建临时目录用于测试
    import tempfile
    tmpdir = tempfile.mkdtemp()
    
    try:
        test_log_file = os.path.join(tmpdir, 'test_app.log')
        
        # 配置测试日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - [%(levelname)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(test_log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        logger = logging.getLogger(__name__)
        
        # 定义日志函数
        def log_operation(operation, details=None, level='INFO'):
            """记录操作日志"""
            msg = f"[操作] {operation}"
            if details:
                msg += f" | {details}"
            if level == 'ERROR':
                logger.error(msg)
            elif level == 'WARNING':
                logger.warning(msg)
            else:
                logger.info(msg)
        
        def log_request(method, endpoint, user_id=None, params=None):
            """记录请求"""
            msg = f"[请求] {method} {endpoint}"
            if user_id:
                msg += f" | 用户: {user_id}"
            if params:
                msg += f" | 参数: {params}"
            logger.info(msg)
        
        # 测试用例
        print("\n1️⃣  测试用户登录日志...")
        log_request('POST', '/login')
        log_operation('用户登录', '用户ID: 1, 用户名: admin')
        
        print("\n2️⃣  测试图片生成日志...")
        log_request('POST', '/api/generate', user_id=1, params='提示词长度: 256')
        log_operation('生成图片成功', '用户ID: 1, 输出目录: output/1, 生成图片: 4')
        
        print("\n3️⃣  测试错误日志...")
        log_request('POST', '/api/generate', user_id=2)
        log_operation('生成图片失败', '用户ID: 2, 错误: API超时', 'ERROR')
        
        print("\n4️⃣  测试警告日志...")
        log_operation('部分操作失败', '用户ID: 3, 成功: 5, 失败: 2', 'WARNING')
        
        print("\n5️⃣  测试批量操作日志...")
        log_request('POST', '/api/batch-delete', user_id=1, params='记录数: 10')
        log_operation('批量删除记录', '用户ID: 1, 成功: 9, 失败: 1')
        
        print("\n6️⃣  测试特殊字符...")
        log_operation('测试特殊字符', '内容: 😀, 数字: 12345, 符号: @#$%')
        
        print("\n7️⃣  测试长日志...", end='')
        long_msg = '用户ID: 1, ' + '详细信息: ' * 50
        log_operation('长日志测试', long_msg[:100])
        print(" ✓")
        
        print("\n8️⃣  测试空参数...")
        log_request('GET', '/api/records')  # 无用户ID
        log_operation('测试操作')  # 无详细信息
        
        # 验证日志文件
        print("\n\n验证日志文件...")
        if os.path.exists(test_log_file):
            with open(test_log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            print(f"✓ 日志文件已创建")
            print(f"✓ 日志行数: {len(lines)}")
            
            # 检查各类日志
            info_count = sum(1 for line in lines if '[INFO]' in line)
            warning_count = sum(1 for line in lines if '[WARNING]' in line)
            error_count = sum(1 for line in lines if '[ERROR]' in line)
            
            print(f"✓ INFO级别: {info_count} 条")
            print(f"✓ WARNING级别: {warning_count} 条")
            print(f"✓ ERROR级别: {error_count} 条")
            
            # 检查日志内容
            has_operation = any('[操作]' in line for line in lines)
            has_request = any('[请求]' in line for line in lines)
            
            print(f"✓ 包含操作日志: {has_operation}")
            print(f"✓ 包含请求日志: {has_request}")
            
            # 显示前几行和最后几行
            print("\n日志文件内容预览 (前3行):")
            for line in lines[:3]:
                print(f"  {line.rstrip()}")
            
            print("\n日志文件内容预览 (最后3行):")
            for line in lines[-3:]:
                print(f"  {line.rstrip()}")
        else:
            print("✗ 日志文件未创建！")
            return False
    
        print("\n" + "=" * 60)
        print("✅ 日志系统测试通过！")
        print("=" * 60)
        return True
    finally:
        # 清理临时文件
        import shutil
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except:
            pass

def test_log_monitor_import():
    """测试log_monitor模块是否可以导入"""
    print("\n\n检查log_monitor模块...")
    try:
        # 尝试导入log_monitor
        if os.path.exists('log_monitor.py'):
            print("✓ log_monitor.py 文件存在")
            
            # 检查基本语法
            with open('log_monitor.py', 'r', encoding='utf-8') as f:
                code = f.read()
            try:
                compile(code, 'log_monitor.py', 'exec')
                print("✓ log_monitor.py 语法正确")
            except SyntaxError as e:
                print(f"✗ log_monitor.py 语法错误: {e}")
                return False
        else:
            print("✗ log_monitor.py 文件不存在")
            return False
    except Exception as e:
        print(f"✗ 检查失败: {e}")
        return False
    
    return True

def main():
    """主函数"""
    # 测试日志系统
    success = test_logging_setup()
    
    # 测试log_monitor
    monitor_ok = test_log_monitor_import()
    
    if success and monitor_ok:
        print("\n\n🎉 所有测试都通过了！")
        print("\n后续步骤:")
        print("  1. 启动应用: python web_app.py")
        print("  2. 实时监控: python log_monitor.py --watch")
        print("  3. 查看帮助: python log_monitor.py --help")
        return 0
    else:
        print("\n\n⚠️  某些测试失败，请检查错误信息")
        return 1

if __name__ == '__main__':
    sys.exit(main())
