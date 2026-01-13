#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
用户管理工具 - 创建、列出、删除用户

使用方法：
    python manage_users.py add <username> <password>     # 创建新用户
    python manage_users.py list                           # 列出所有用户
    python manage_users.py delete <username>              # 删除用户
    python manage_users.py password <username> <new_pwd>  # 修改密码
"""

import sys
import os
import database

def create_user(username, password):
    """创建新用户"""
    if len(username) < 3 or len(username) > 20:
        print("❌ 错误：用户名长度必须在3-20位之间")
        return False
    
    if len(password) < 6:
        print("❌ 错误：密码长度至少6位")
        return False
    
    # 检查用户名是否只包含字母、数字和下划线
    if not username.replace('_', '').isalnum():
        print("❌ 错误：用户名只能包含字母、数字和下划线")
        return False
    
    user_id = database.create_user(username, password)
    if user_id:
        # 创建用户专属目录
        os.makedirs(f'output/{user_id}', exist_ok=True)
        os.makedirs(f'uploads/{user_id}', exist_ok=True)
        print(f"✅ 用户创建成功！")
        print(f"   用户名: {username}")
        print(f"   用户ID: {user_id}")
        print(f"   输出目录: output/{user_id}/")
        print(f"   上传目录: uploads/{user_id}/")
        return True
    else:
        print(f"❌ 错误：用户名 '{username}' 已存在")
        return False

def list_users():
    """列出所有用户"""
    import sqlite3
    
    conn = sqlite3.connect(database.DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, username, created_at, last_login 
        FROM users 
        ORDER BY id
    ''')
    
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        print("📋 暂无用户")
        return
    
    print(f"\n📋 用户列表 (共 {len(users)} 个用户):")
    print("-" * 80)
    print(f"{'ID':<5} {'用户名':<20} {'创建时间':<20} {'最后登录':<20}")
    print("-" * 80)
    
    for user in users:
        user_dict = dict(user)
        last_login = user_dict['last_login'] or '从未登录'
        print(f"{user_dict['id']:<5} {user_dict['username']:<20} {user_dict['created_at']:<20} {last_login:<20}")
    
    print("-" * 80)

def delete_user(username):
    """删除用户"""
    import sqlite3
    
    # 确认删除
    confirm = input(f"⚠️  确定要删除用户 '{username}' 吗？此操作不可恢复！(yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ 取消删除")
        return False
    
    conn = sqlite3.connect(database.DB_PATH)
    cursor = conn.cursor()
    
    # 检查用户是否存在
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    
    if not user:
        print(f"❌ 错误：用户 '{username}' 不存在")
        conn.close()
        return False
    
    user_id = user[0]
    
    # 删除用户的所有记录
    cursor.execute('DELETE FROM generation_records WHERE user_id = ?', (user_id,))
    records_deleted = cursor.rowcount
    
    # 删除用户
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    
    conn.commit()
    conn.close()
    
    print(f"✅ 用户 '{username}' 删除成功！")
    print(f"   删除了 {records_deleted} 条生成记录")
    print(f"   注意：用户的文件目录未删除，请手动清理：")
    print(f"   - output/{user_id}/")
    print(f"   - uploads/{user_id}/")
    
    return True

def change_password(username, new_password):
    """修改用户密码"""
    import sqlite3
    
    if len(new_password) < 6:
        print("❌ 错误：密码长度至少6位")
        return False
    
    conn = sqlite3.connect(database.DB_PATH)
    cursor = conn.cursor()
    
    # 检查用户是否存在
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    
    if not user:
        print(f"❌ 错误：用户 '{username}' 不存在")
        conn.close()
        return False
    
    # 更新密码
    password_hash = database.hash_password(new_password)
    cursor.execute('UPDATE users SET password_hash = ? WHERE username = ?', 
                   (password_hash, username))
    
    conn.commit()
    conn.close()
    
    print(f"✅ 用户 '{username}' 的密码修改成功！")
    return True

def main():
    """主函数"""
    # 初始化数据库
    database.init_database()
    
    if len(sys.argv) < 2:
        print("用户管理工具")
        print("\n使用方法：")
        print("  python manage_users.py add <username> <password>     # 创建新用户")
        print("  python manage_users.py list                           # 列出所有用户")
        print("  python manage_users.py delete <username>              # 删除用户")
        print("  python manage_users.py password <username> <new_pwd>  # 修改密码")
        print("\n示例：")
        print("  python manage_users.py add john john123")
        print("  python manage_users.py list")
        print("  python manage_users.py password john newpass456")
        print("  python manage_users.py delete john")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == 'add':
        if len(sys.argv) != 4:
            print("❌ 错误：缺少参数")
            print("用法: python manage_users.py add <username> <password>")
            sys.exit(1)
        username = sys.argv[2]
        password = sys.argv[3]
        create_user(username, password)
    
    elif command == 'list':
        list_users()
    
    elif command == 'delete':
        if len(sys.argv) != 3:
            print("❌ 错误：缺少参数")
            print("用法: python manage_users.py delete <username>")
            sys.exit(1)
        username = sys.argv[2]
        delete_user(username)
    
    elif command == 'password':
        if len(sys.argv) != 4:
            print("❌ 错误：缺少参数")
            print("用法: python manage_users.py password <username> <new_password>")
            sys.exit(1)
        username = sys.argv[2]
        new_password = sys.argv[3]
        change_password(username, new_password)
    
    else:
        print(f"❌ 错误：未知命令 '{command}'")
        print("支持的命令: add, list, delete, password")
        sys.exit(1)

if __name__ == '__main__':
    main()
