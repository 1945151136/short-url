"""网页端表单。"""
from django import forms


class ShortenForm(forms.Form):
    original_url = forms.CharField(
        label='原始链接',
        max_length=2048,
        widget=forms.URLInput(attrs={
            'class': 'input',
            'placeholder': '粘贴需要缩短的长链接，例如 https://www.example.com/very/long/url',
        }),
    )
    alias = forms.CharField(
        label='自定义短码（可选）',
        max_length=32, required=False,
        widget=forms.TextInput(attrs={
            'class': 'input', 'placeholder': '4-32 位字母/数字/-/_，留空则自动生成',
        }),
    )
    remarks = forms.CharField(
        label='备注（可选）',
        max_length=255, required=False,
        widget=forms.TextInput(attrs={'class': 'input', 'placeholder': '给这条链接起个名字，方便管理'}),
    )
    expires_at = forms.DateField(
        label='过期日期（可选）',
        required=False,
        widget=forms.DateInput(attrs={'class': 'input', 'type': 'date'}),
    )
