#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
火山引擎账户余额查询程序
使用火山引擎官方SDK
"""

import json
from datetime import datetime

import volcenginesdkcore
import volcenginesdkbilling
from volcenginesdkcore.rest import ApiException


def load_config(config_path: str = "config.json") -> dict:
    """从配置文件加载API密钥"""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_balance(amount: float) -> str:
    """格式化余额显示"""
    return f"¥{amount:,.2f}"


def query_account_balance(access_key: str, secret_key: str) -> dict:
    """
    查询火山引擎账户余额

    使用官方SDK: volcenginesdkbilling
    """
    # 配置认证信息
    configuration = volcenginesdkcore.Configuration()
    configuration.ak = access_key
    configuration.sk = secret_key
    configuration.region = "cn-beijing"

    # 设置默认配置
    volcenginesdkcore.Configuration.set_default(configuration)

    # 创建API实例并查询
    api_instance = volcenginesdkbilling.BILLINGApi()
    request = volcenginesdkbilling.QueryBalanceAcctRequest()

    return api_instance.query_balance_acct(request)


def main():
    """主函数"""
    print("=" * 50)
    print("火山引擎账户余额查询")
    print("=" * 50)

    try:
        # 加载配置
        config = load_config()
        access_key = config.get("access_key", "")
        secret_key = config.get("secret_key", "")

        if not access_key or not secret_key:
            print("错误：请先在 config.json 中配置 access_key 和 secret_key")
            return

        # 显示查询时间
        query_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n查询时间: {query_time}")
        print("-" * 50)

        # 查询余额
        result = query_account_balance(access_key, secret_key)

        # 解析结果
        # SDK返回对象，需要转换为字典处理
        if hasattr(result, 'available_balance'):
            balance = float(result.available_balance) if result.available_balance else 0
            print(f"账户余额: {format_balance(balance)}")
        elif hasattr(result, 'balance_amount'):
            balance = float(result.balance_amount) if result.balance_amount else 0
            print(f"账户余额: {format_balance(balance)}")
        elif hasattr(result, 'result'):
            # 如果返回的是包含result的对象
            data = result.result
            if hasattr(data, 'available_balance'):
                balance = float(data.available_balance) if data.available_balance else 0
                print(f"账户余额: {format_balance(balance)}")
            elif hasattr(data, 'balance_amount'):
                balance = float(data.balance_amount) if data.balance_amount else 0
                print(f"账户余额: {format_balance(balance)}")
        else:
            # 打印完整响应以供调试
            print(f"账户余额信息:")
            print(result)

    except ApiException as e:
        print(f"API错误: {e}")
    except FileNotFoundError:
        print("错误：未找到 config.json 文件，请确保配置文件存在")
    except json.JSONDecodeError:
        print("错误：config.json 格式不正确，请检查JSON格式")
    except Exception as e:
        print(f"发生错误: {type(e).__name__}: {e}")

    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()