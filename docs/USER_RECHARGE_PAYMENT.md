# 用户充值与支付中心对接说明

本文档描述外部用户在用户中心发起充值时，本系统与内部支付中心之间的字段约定、状态流转与回调要求。

## 页面流程

1. 用户在 `用户中心` 选择充值金额：`100 / 500 / 1000 / 自定义`
2. 前端调用 `POST /api/user/recharge-orders`
3. 本系统先生成本地充值订单，再调用支付中心创建微信 Native 支付单
4. 支付中心返回二维码信息
5. 前端展示二维码，并轮询 `GET /api/user/recharge-orders/{order_no}`
6. 支付中心异步回调 `POST /api/payment-center/recharge-callback`
7. 本系统验签、校验金额、幂等入账、更新订单状态

## 本地订单表

表名：`recharge_orders`

核心字段：

- `order_no`：本系统充值订单号，唯一
- `user_id` / `username`：充值用户
- `amount_cent`：充值金额，单位分
- `status`：`pending / paying / paid / failed / closed / refunded`
- `payment_channel`：当前固定 `wechat_native`
- `payment_center_order_no`：支付中心订单号
- `channel_trade_no`：微信侧交易号
- `qr_code_url` / `qr_code_img_url`：支付二维码内容与图片地址
- `expire_at`：支付过期时间
- `paid_at`：到账时间
- `fail_reason`：失败原因
- `request_payload_json`：发给支付中心的请求体快照
- `callback_payload_json`：支付中心回调快照
- `metadata_json`：业务扩展字段

## 你方 API

### `GET /api/user/recharge-config`

返回充值配置：

- `enabled`
- `preset_amounts_cent`
- `min_amount_cent`
- `max_amount_cent`
- `payment_channel`

### `POST /api/user/recharge-orders`

请求体：

```json
{
  "amount_yuan": "500",
  "selected_option": "preset-50000"
}
```

返回：

```json
{
  "success": true,
  "data": {
    "order": {
      "order_no": "RC20260610123000ABCDEF1234",
      "amount_cent": 50000,
      "amount_yuan": "500.00",
      "status": "paying",
      "payment_channel": "wechat_native",
      "payment_center_order_no": "pc_123456",
      "qr_code_url": "weixin://wxpay/bizpayurl?...",
      "qr_code_img_url": "https://payment-center/.../qr.png",
      "expire_at": "2026-06-10 12:45:00"
    }
  }
}
```

### `GET /api/user/recharge-orders/{order_no}`

用于前端轮询支付状态。

## 发给支付中心的请求字段

请求地址：`PAYMENT_CENTER_BASE_URL + PAYMENT_CENTER_CREATE_ORDER_PATH`

请求头：

- `X-Merchant-Id`
- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

签名算法：

- 原文：`timestamp + "\n" + nonce + "\n" + canonical_json(payload)`
- 算法：`HMAC-SHA256`
- 密钥：`PAYMENT_CENTER_SIGN_SECRET`

请求体字段：

- `merchant_id`
- `app_id`
- `merchant_order_no`
- `user_id`
- `username`
- `amount_cent`
- `currency`
- `product_name`
- `product_desc`
- `pay_channel`
- `client_type`
- `callback_url`
- `return_url`
- `attach`
- `expire_minutes`

## 支付中心创建订单返回字段

建议支付中心返回：

- `success`
- `payment_center_order_no`
- `pay_status`
- `amount_cent`
- `currency`
- `pay_channel`
- `qr_code_url`
- `qr_code_img_url`
- `expire_at`
- `message`

## 支付中心异步回调字段

回调地址：`POST /api/payment-center/recharge-callback`

请求头建议：

- `X-Timestamp`
- `X-Nonce`
- `X-Signature`

回调 JSON 建议包含：

- `merchant_order_no`
- `payment_center_order_no`
- `channel_trade_no`
- `status`：`paid / failed / closed / refunded`
- `amount_cent`
- `currency`
- `paid_at`
- `fail_reason`
- `message`
- `attach`

如果签名放在 JSON 中，也支持：

- `sign`
- `timestamp`
- `nonce`

## 回调处理规则

1. 验签
2. 根据 `merchant_order_no` 查本地订单
3. 校验 `amount_cent`
4. 若 `status=paid`：
   - 幂等写入 `account_ledger`
   - 增加 `users.balance_cent`
   - 更新 `recharge_orders.status=paid`
5. 若 `status=failed/closed/refunded`：
   - 更新本地订单状态
   - 记录失败原因

## 台账入账规则

充值到账时写入：

- `entry_type = credit`
- `biz_type = recharge`
- `biz_id = order_no`

这样充值和消费都统一落在 `account_ledger` 中，便于对账。
