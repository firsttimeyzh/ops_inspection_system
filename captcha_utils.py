# -*- coding: utf-8 -*-
"""
验证码生成工具 - 清晰大字体版
"""
import random
import io
from PIL import Image, ImageDraw, ImageFont
import base64

# 验证码字符集
CHARACTERS = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'

def generate_captcha(length=4):
    """生成随机验证码"""
    return ''.join(random.choice(CHARACTERS) for _ in range(length))

def generate_captcha_image(captcha_text):
    """生成验证码图片 - 大字体清晰版"""
    # 图片尺寸 - 增大尺寸
    width = 150
    height = 60

    # 创建图片 - 使用浅灰色背景
    image = Image.new('RGB', (width, height), (248, 248, 248))
    draw = ImageDraw.Draw(image)

    # 绘制少量噪点 - 减少噪点避免干扰
    for _ in range(10):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        draw.point((x, y), fill=(random.randint(220, 240), random.randint(220, 240), random.randint(220, 240)))

    # 绘制1条细线作为干扰
    x1 = random.randint(0, width // 3)
    y1 = random.randint(height // 3, height * 2 // 3)
    x2 = random.randint(width * 2 // 3, width)
    y2 = random.randint(height // 3, height * 2 // 3)
    draw.line([(x1, y1), (x2, y2)], fill=(random.randint(210, 230), random.randint(210, 230), random.randint(210, 230)), width=1)

    # 尝试加载字体，如果没有则使用默认字体但设置大字号
    try:
        # 使用系统字体，24号大小
        font_size = 28
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except:
            try:
                font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", font_size)
            except:
                font = ImageFont.load_default()
    except Exception:
        font = None

    # 绘制字符 - 大字体，清晰可见
    char_width = (width - 30) // len(captcha_text)
    for i, char in enumerate(captcha_text):
        x = 15 + i * char_width + 10
        # 垂直居中
        y = 12

        # 深灰色字符保证高对比度
        color = (35, 35, 35)

        if font:
            draw.text((x, y), char, fill=color, font=font)
        else:
            draw.text((x, y), char, fill=color)

    # 返回图片
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    return buf
