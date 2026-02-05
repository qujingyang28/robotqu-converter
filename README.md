# 🤖 Robot_Qu 工业程序转换器

<p align="center">
  <img src="https://img.shields.io/badge/Robot-ABB%2FFANUC-orange" alt="Robot">
  <img src="https://img.shields.io/badge/PLC-Omron%2FInovance-blue" alt="PLC">
  <img src="https://img.shields.io/badge/Python-3.8%2B-green" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License">
</p>

由 [Robot_Qu 机器人社区](https://www.robotqu.com) 提供的工业自动化程序转换工具，支持机器人和PLC多品牌程序互转。

## ✨ 功能特性

### 🤖 机器人转换
- ✅ **ABB RAPID** → **FANUC TP/LS**
- 🔄 KUKA KRL（开发中）

### 🔌 PLC转换
- ✅ **欧姆龙 Omron (ST)** → **汇川 Inovance (ST)**
- 🔄 西门子 SCL ↔ 三菱 ST（开发中）

## 🚀 快速开始

### 本地运行

1. **克隆仓库**
```bash
git clone https://github.com/你的用户名/robotqu-converter.git
cd robotqu-converter
安装依赖
bash
复制
pip install -r requirements.txt
运行服务
bash
复制
python app.py
打开浏览器
访问 http://localhost:5000
支持的文件格式
表格
复制
类型	品牌	格式	说明
机器人	ABB	.mod	RAPID程序文件
机器人	FANUC	.ls	TP程序ASCII格式
PLC	欧姆龙	.st, .txt	ST语言导出
PLC	汇川	.txt	Codesys ST格式
🛠️ 技术架构
后端: Python Flask
前端: 原生 HTML5 + CSS3 + JavaScript
核心算法: 正则表达式解析 + 语法树转换
📋 转换示例
欧姆龙 → 汇川 地址映射
表格
复制
欧姆龙	汇川 (Codesys)	类型
CIO0.00	%QX0.0	输出位
D0	%MD0	数据寄存器
TIM0	%MT0	定时器
CNT0	%MC0	计数器
🤝 贡献代码
欢迎提交 Pull Request！请确保：
代码通过基本测试
添加必要的注释
更新 README 文档
📄 开源协议
本项目采用 MIT License 开源协议。
<p align="center">
  <strong>Powered by Robot_Qu 机器人社区</strong><br>
  <a href="https://www.robotqu.com">www.robotqu.com</a>
</p>
```