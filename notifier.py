# -*- coding: utf-8 -*-
"""邮件推送模块"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import EMAIL_CONFIG


def send_email(subject, body):
    """发送邮件"""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['sender']
        msg['To'] = EMAIL_CONFIG['receiver']
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html', 'utf-8'))

        # 使用SSL连接
        server = smtplib.SMTP_SSL(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.login(EMAIL_CONFIG['sender'], EMAIL_CONFIG['password'])
        server.send_message(msg)
        server.quit()

        print(f"邮件发送成功: {subject}")
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False


def send_buy_signal(stocks):
    """发送买入信号"""
    if not stocks:
        subject = "【选股系统】今日无符合条件的股票"
        body = "<p>今日未筛选出符合条件的股票，暂停操作。</p>"
    else:
        subject = f"【选股系统】买入信号 ({len(stocks)}只)"
        body = "<h2>买入信号</h2><table border='1' cellpadding='5' cellspacing='0'>"
        body += "<tr><th>代码</th><th>名称</th><th>价格</th><th>涨幅</th><th>换手率</th><th>量比</th><th>市值(亿)</th></tr>"

        for stock in stocks:
            body += f"<tr>"
            body += f"<td>{stock['code']}</td>"
            body += f"<td>{stock['name']}</td>"
            body += f"<td>{stock['price']:.2f}</td>"
            body += f"<td>{stock['gain']*100:.2f}%</td>"
            body += f"<td>{stock['turnover']*100:.2f}%</td>"
            body += f"<td>{stock['volume_ratio']:.2f}</td>"
            body += f"<td>{stock['market_cap']:.2f}</td>"
            body += f"</tr>"

        body += "</table>"
        body += "<p><strong>操作建议：</strong>14:50 前买入，单只仓位 ≤10%，总仓位 ≤50%</p>"

    return send_email(subject, body)


def send_sell_signal(positions):
    """发送卖出信号"""
    subject = f"【选股系统】卖出信号 ({len(positions)}只)"
    body = "<h2>卖出信号</h2><table border='1' cellpadding='5' cellspacing='0'>"
    body += "<tr><th>代码</th><th>名称</th><th>买入价</th><th>当前价</th><th>收益率</th><th>操作</th></tr>"

    for pos in positions:
        gain = (pos['current_price'] - pos['buy_price']) / pos['buy_price']
        action = "止盈" if gain >= 0.02 else ("止损" if gain <= -0.02 else "清仓")

        body += f"<tr>"
        body += f"<td>{pos['code']}</td>"
        body += f"<td>{pos['name']}</td>"
        body += f"<td>{pos['buy_price']:.2f}</td>"
        body += f"<td>{pos['current_price']:.2f}</td>"
        body += f"<td style='color:{'red' if gain > 0 else 'green'}'>{gain*100:.2f}%</td>"
        body += f"<td><strong>{action}</strong></td>"
        body += f"</tr>"

    body += "</table>"
    body += "<p><strong>操作建议：</strong>10:00 前全部清仓，不管盈亏</p>"

    return send_email(subject, body)
