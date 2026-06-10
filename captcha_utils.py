# -*- coding: utf-8 -*-
"""
验证码生成工具 - 简化版
"""
import random
import io
from PIL import Image, ImageDraw
import base64

# 验证码字符集
CHARACTERS = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'

def generate_captcha(length=4):
    """生成随机验证码"""
    return ''.join(random.choice(CHARACTERS) for _ in range(length))

def generate_captcha_image(captcha_text):
    """生成验证码图片"""
    # 图片尺寸
    width = 130
    height = 45
    
    # 创建图片
    image = Image.new('RGB', (width, height), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    
    # 绘制少量噪点
    for _ in range(20):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        draw.point((x, y), fill=(random.randint(200, 240), random.randint(200, 240), random.randint(200, 240)))
    
    # 绘制2条细线
    for _ in range(2):
        x1 = random.randint(0, width // 4)
        y1 = random.randint(height // 4, height * 3 // 4)
        x2 = random.randint(width * 3 // 4, width)
        y2 = random.randint(height // 4, height * 3 // 4)
        draw.line([(x1, y1), (x2, y2)], fill=(random.randint(200, 220), random.randint(200, 220), random.randint(200, 220)), width=1)
    
    # 绘制字符
    char_width = (width - 20) // len(captcha_text)
    for i, char in enumerate(captcha_text):
        x = 10 + i * char_width + 5
        y = 8
        
        # 深灰色字符保证对比度
        color = (40, 40, 40)
        draw.text((x, y), char, fill=color)
    
    # 返回图片
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf