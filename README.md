# 🤖 Robot_Qu 工业程序转换器

<p align="center">
  <img src="https://img.shields.io/badge/Robot-ABB%2FFANUC-orange?style=for-the-badge" alt="Robot">
  <img src="https://img.shields.io/badge/PLC-Omron%2FInovance-blue?style=for-the-badge" alt="PLC">
  <img src="https://img.shields.io/badge/Python-3.8%2B-green?style=for-the-badge" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License">
</p>

<h1 align="center">🤖 Robot_Qu 工业程序转换器</h1>

<p align="center">
  <strong>由 <a href="https://www.robotqu.com">Robot_Qu 机器人社区</a> 提供的工业自动化程序转换工具</strong><br>
  支持机器人和PLC多品牌程序互转
</p>

<p align="center">
  <a href="#-功能特性">功能特性</a> •
  <a href="#-快速开始">快速开始</a> •
  <a href="#-转换示例">转换示例</a> •
  <a href="#-技术架构">技术架构</a> •
  <a href="#-贡献代码">贡献代码</a>
</p>

---

## ✨ 功能特性

### 🤖 机器人程序转换

| 方向 | 状态 | 说明 |
|:---|:---|:---|
| ABB RAPID → FANUC TP/LS | ✅ 已完成 | 支持MoveJ/MoveL，四元数转欧拉角 |
| KUKA KRL ↔ FANUC | 🔄 开发中 | 支持KRL与TP互转 |
| ABB ↔ KUKA | 📋 计划中 | |

### 🔌 PLC程序转换

| 方向 | 状态 | 说明 |
|:---|:---|:---|
| 欧姆龙 Omron (ST) → 汇川 Inovance (ST) | ✅ **已完成** | 地址自动映射，Codesys标准格式 |
| 西门子 SCL ↔ 三菱 ST | 🔄 开发中 | 语法转换，数据类型映射 |
| 西门子 SCL → 欧姆龙 ST | 📋 计划中 | |

---

## 🚀 快速开始

### 环境要求
- Python 3.8+
- Flask 2.0+

### 安装步骤

**1. 克隆仓库**
```bash
git clone https://github.com/qujingyang28/robotqu-converter.git
cd robotqu-converter
2. 安装依赖
bash
复制
pip install -r requirements.txt
3. 运行服务
bash
复制
python app.py
4. 打开浏览器
访问 http://localhost:5000
📁 支持的文件格式
机器人

| 品牌        | 格式    | 文件扩展名        | 说明                |
| :-------- | :---- | :----------- | :---------------- |
| **ABB**   | RAPID | `.mod`       | 程序文件（包含模块和程序）     |
| **FANUC** | TP/LS | `.ls`, `.tp` | LS为ASCII格式，TP为二进制 |

PLC
| 品牌      | 格式         | 文件扩展名         | 说明              |
| :------ | :--------- | :------------ | :-------------- |
| **欧姆龙** | ST         | `.st`, `.txt` | 结构化文本导出         |
| **汇川**  | Codesys ST | `.txt`        | 符合IEC 61131-3标准 |

🔄 转换示例
欧姆龙 → 汇川 地址映射表
| 欧姆龙地址     | 汇川 (Codesys) | 数据类型  | 说明      |
| :-------- | :----------- | :---- | :------ |
| `CIO0.00` | `%QX0.0`     | 输出位   | 第0通道第0位 |
| `CIO100`  | `%QW100`     | 输出字   | 第100通道  |
| `W0.00`   | `%MX0.0`     | 内部位   | 工作区     |
| `W10`     | `%MW10`      | 内部字   | 工作寄存器   |
| `D0`      | `%MD0`       | 数据寄存器 | 32位有符号  |
| `H0.00`   | `%MX900.0`   | 保持位   | 保持继电器   |
| `TIM0`    | `%MT0`       | 定时器   | 定时器完成位  |
| `CNT0`    | `%MC0`       | 计数器   | 计数器完成位  |

指令转换示例
欧姆龙 ST:
iecst
复制
IF StartButton AND NOT StopButton THEN
    Motor := TRUE;
    MOV(100, Speed);
ELSE
    Motor := FALSE;
END_IF;
汇川 ST (转换后):
iecst
复制
IF StartButton AND NOT StopButton THEN
    Motor := TRUE;
    Speed := 100;
ELSE
    Motor := FALSE;
END_IF;
🛠️ 技术架构
复制
robotqu-converter/
├── app.py              # Flask后端主程序
├── requirements.txt    # Python依赖清单
├── README.md          # 项目说明文档
├── LICENSE            # MIT开源协议
└── temp/              # 转换临时文件目录
| 层级       | 技术栈                       | 说明                    |
| :------- | :------------------------ | :-------------------- |
| **后端**   | Python + Flask            | RESTful API，处理文件上传和转换 |
| **前端**   | HTML5 + CSS3 + JavaScript | 响应式设计，原生实现，无依赖        |
| **核心算法** | 正则表达式 + 语法树               | 解析源程序，生成目标语法          |
| **部署**   | 本地/云服务器                   | 支持Windows/Linux/MacOS |

🤝 贡献代码
欢迎提交 Pull Request！
提交规范
✅ 代码通过基本功能测试
✅ 添加必要的注释说明
✅ 更新 README 文档
✅ 描述清楚本次改动内容
待开发功能
[ ] KUKA KRL 转换器
[ ] 西门子 SCL 完整支持
[ ] 梯形图 (LAD) 图形转换
[ ] 批量文件转换
[ ] 在线演示站点
📄 开源协议
本项目采用 MIT License 开源协议。
复制
MIT License

Copyright (c) 2024 Robot_Qu 机器人社区

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
<p align="center">
  <br>
  <strong>🌐 Powered by Robot_Qu 机器人社区</strong><br>
  <a href="https://www.robotqu.com">www.robotqu.com</a>
  <br><br>
  <img src="https://img.shields.io/github/stars/qujingyang28/robotqu-converter?style=social" alt="GitHub stars">
  <img src="https://img.shields.io/github/forks/qujingyang28/robotqu-converter?style=social" alt="GitHub forks">
</p>
```
```

