"""確認状況は機種定義に残し、図面の注記へは出さない。"""
import re


def drawing_text(text):
    return ''.join(part for part in re.split(r'(?<=[。\n])', str(text))
                   if not any(word in part for word in ('未確認', '要確認', '未検証', '未照合'))).strip()
