from flask import Flask, render_template_string, request, send_file, jsonify
import os
import re
import math
from pathlib import Path
import io

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ==================== 机器人转换器 ====================

class ABBtoFanuc:
    def __init__(self):
        self.points = {}
        
    def parse_mod(self, content):
        instructions = []
        pattern = r'robtarget\s+(\w+)\s*:=\s*\[\[([-\d.eE]+)\s*,\s*([-\d.eE]+)\s*,\s*([-\d.eE]+)\s*\]\s*,\s*\[([-\d.eE]+)\s*,\s*([-\d.eE]+)\s*,\s*([-\d.eE]+)\s*,\s*([-\d.eE]+)\s*\]'
        
        for m in re.finditer(pattern, content, re.IGNORECASE):
            name, x, y, z, q1, q2, q3, q4 = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)), float(m.group(5)), float(m.group(6)), float(m.group(7)), float(m.group(8))
            w, p, r = self.quaternion_to_euler(q1, q2, q3, q4)
            self.points[name.lower()] = {'x': x, 'y': y, 'z': z, 'w': w, 'p': p, 'r': r}
            self.points[name] = {'x': x, 'y': y, 'z': z, 'w': w, 'p': p, 'r': r}
        
        content_processed = re.sub(r',\s*\n\s*', ', ', content)
        lines = content_processed.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('!'):
                continue
            
            if re.match(r'MoveJ\s+', line, re.IGNORECASE):
                m = re.search(r'MoveJ\s+(\w+),\s*(\w+)', line, re.IGNORECASE)
                if m:
                    point, speed = m.groups()
                    instructions.append({
                        'move_type': 'J',
                        'point': point,
                        'speed': self.convert_speed(speed, False)
                    })
            elif re.match(r'MoveL\s+', line, re.IGNORECASE):
                m = re.search(r'MoveL\s+(\w+),\s*(\w+)', line, re.IGNORECASE)
                if m:
                    point, speed = m.groups()
                    instructions.append({
                        'move_type': 'L',
                        'point': point,
                        'speed': self.convert_speed(speed, True)
                    })
        return instructions
    
    def quaternion_to_euler(self, q1, q2, q3, q4):
        r11 = 1 - 2*(q2**2 + q3**2)
        r21 = 2*(q1*q2 + q3*q4)
        r31 = 2*(q1*q3 - q2*q4)
        r32 = 2*(q2*q3 + q1*q4)
        r33 = 1 - 2*(q1**2 + q2**2)
        w = math.atan2(r21, r11)
        p = math.atan2(-r31, math.sqrt(r32**2 + r33**2))
        r = math.atan2(r32, r33)
        return math.degrees(w), math.degrees(p), math.degrees(r)
    
    def convert_speed(self, speed, is_linear):
        m = re.search(r'\d+', str(speed))
        val = int(m.group()) if m else 1000
        if is_linear:
            return f"{val}mm/sec"
        return f"{min(val//10, 100)}%"

    def generate_ls(self, instructions, prog_name="CONV"):
        lines = []
        lines.append(f"/PROG {prog_name}")
        lines.append("/ATTR")
        lines.append('COMMENT = "Converted from ABB";')
        lines.append("/MN")
        
        for i, inst in enumerate(instructions, 1):
            if inst['move_type'] == 'J':
                lines.append(f"  {i}:J  P[{i}] {inst['speed']} FINE ;")
            else:
                lines.append(f"  {i}:L  P[{i}] {inst['speed']} FINE ;")
        
        lines.append("/POS")
        last_p = {'x':0,'y':0,'z':0,'w':0,'p':0,'r':0}
        
        for i, inst in enumerate(instructions, 1):
            pt = inst['point']
            p = self.points.get(pt, self.points.get(pt.lower(), last_p))
            if pt in self.points or pt.lower() in self.points:
                last_p = p
            
            lines.append(f"P[{i}]{{")
            lines.append("   GP1:")
            lines.append("    UF : 0, UT : 1,")
            lines.append(f"    X = {p['x']:.3f} mm, Y = {p['y']:.3f} mm, Z = {p['z']:.3f} mm,")
            lines.append(f"    W = {p['w']:.3f} deg, P = {p['p']:.3f} deg, R = {p['r']:.3f} deg")
            lines.append("};")
        
        lines.append("/END")
        return '\n'.join(lines)


# ==================== PLC转换器（新增：欧姆龙→汇川） ====================

class OmronToInovance:
    """欧姆龙PLC (CP/CJ/NX系列) 转 汇川PLC (H3U/H5U/AC800系列)"""
    
    def __init__(self):
        self.variable_decls = []
        
    def convert(self, content):
        """主转换入口"""
        print("🔍 解析欧姆龙ST程序...")
        
        # 尝试提取变量声明区
        var_pattern = r'VAR\s+(.*?)\s+END_VAR'
        program_pattern = r'END_VAR\s+(.*?)\s+END_PROGRAM'
        
        var_match = re.search(var_pattern, content, re.DOTALL | re.IGNORECASE)
        prog_match = re.search(program_pattern, content, re.DOTALL | re.IGNORECASE)
        
        if var_match:
            self.parse_variables(var_match.group(1))
        
        if prog_match:
            program_body = prog_match.group(1)
        else:
            # 如果没有标准结构，尝试分离PROGRAM...END_PROGRAM
            prog_simple = re.search(r'PROGRAM\s+\w+\s+(.*?)\s+END_PROGRAM', content, re.DOTALL | re.IGNORECASE)
            if prog_simple:
                program_body = prog_simple.group(1)
                # 检查是否有VAR区
                var_in_prog = re.search(r'VAR\s+(.*?)END_VAR\s+(.*)', program_body, re.DOTALL | re.IGNORECASE)
                if var_in_prog:
                    self.parse_variables(var_in_prog.group(1))
                    program_body = var_in_prog.group(2)
            else:
                program_body = content  # 原始内容
        
        # 转换程序体
        converted_body = self.convert_body(program_body)
        
        return self.generate_inovance_code(converted_body)
    
    def parse_variables(self, var_content):
        """解析变量声明区"""
        print("  解析变量声明...")
        var_lines = var_content.strip().split('\n')
        
        for line in var_lines:
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('(*'):
                continue
            
            # 匹配：变量名 : 类型 @ 地址
            at_pattern = r'(\w+)\s*:\s*(\w+)\s*AT\s*([^;]+);?'
            normal_pattern = r'(\w+)\s*:\s*([\w\(\)]+);?'
            
            match = re.match(at_pattern, line, re.IGNORECASE)
            if match:
                name, var_type, address = match.groups()
                new_addr = self.convert_address(address.strip())
                self.variable_decls.append({
                    'name': name,
                    'type': self.convert_type(var_type),
                    'address': new_addr,
                    'comment': f'原欧姆龙: {address}'
                })
                print(f"    {name}: {var_type} @ {address} -> {new_addr}")
            else:
                match = re.match(normal_pattern, line, re.IGNORECASE)
                if match:
                    name, var_type = match.groups()
                    self.variable_decls.append({
                        'name': name,
                        'type': self.convert_type(var_type),
                        'address': None,
                        'comment': ''
                    })
    
    def convert_body(self, body):
        """转换程序主体"""
        print("  转换程序逻辑...")
        result = body
        
        # 地址转换（从复杂到简单）
        # CIO位寻址 CIO0.00 -> %QX0.0
        result = re.sub(r'CIO(\d+)\.(\d+)', lambda m: f'%QX{m.group(1)}.{m.group(2)}', result)
        # CIO字寻址 CIO100 -> %QW100
        result = re.sub(r'CIO(\d+)([^.\d])', lambda m: f'%QW{m.group(1)}{m.group(2)}', result)
        
        # W区域 W0.00 -> %MX0.0, W0 -> %MW0
        result = re.sub(r'W(\d+)\.(\d+)', lambda m: f'%MX{m.group(1)}.{m.group(2)}', result)
        result = re.sub(r'W(\d+)([^.\d])', lambda m: f'%MW{m.group(1)}{m.group(2)}', result)
        
        # D区域 D0 -> %MD0
        result = re.sub(r'D(\d+)([^.\d])', lambda m: f'%MD{m.group(1)}{m.group(2)}', result)
        
        # H区域（保持继电器）映射到高位
        result = re.sub(r'H(\d+)\.(\d+)', 
                       lambda m: f'%MX{900+int(m.group(1))}.{m.group(2)}', result)
        
        # T/C定时器计数器
        result = re.sub(r'\bTIM(\d+)\b', r'%MT\1', result)
        result = re.sub(r'\bCNT(\d+)\b', r'%MC\1', result)
        result = re.sub(r'\bT(\d+)\b', r'%MT\1', result)
        result = re.sub(r'\bC(\d+)\b', r'%MC\1', result)
        
        # 指令转换
        result = re.sub(r'MOV\(([^,]+),\s*([^)]+)\)', r'\2 := \1;', result, flags=re.IGNORECASE)
        result = re.sub(r'SET\(([^)]+)\)', r'\1 := TRUE;', result, flags=re.IGNORECASE)
        result = re.sub(r'RSET\(([^)]+)\)', r'\1 := FALSE;', result, flags=re.IGNORECASE)
        
        # 语法标准化
        result = re.sub(r'IF\s+(.+?)\s+THEN', r'IF \1 THEN', result, flags=re.IGNORECASE)
        result = re.sub(r'END_IF', r'END_IF;', result, flags=re.IGNORECASE)
        result = re.sub(r'END_WHILE', r'END_WHILE;', result, flags=re.IGNORECASE)
        result = re.sub(r'END_FOR', r'END_FOR;', result, flags=re.IGNORECASE)
        
        return result
    
    def convert_address(self, addr):
        """转换单个地址"""
        addr = addr.strip().upper()
        
        if addr.startswith('%'):
            addr = addr[1:]  # 去掉前面的%
        
        if addr.startswith('CIO'):
            match = re.match(r'CIO(\d+)\.(\d+)', addr)
            if match:
                return f'%QX{match.group(1)}.{match.group(2)}'
            match = re.match(r'CIO(\d+)', addr)
            if match:
                return f'%QW{match.group(1)}'
        
        if addr.startswith('D'):
            num = re.search(r'\d+', addr)
            if num:
                return f'%MD{num.group()}'
        
        if addr.startswith('W'):
            match = re.match(r'W(\d+)\.(\d+)', addr)
            if match:
                return f'%MX{match.group(1)}.{match.group(2)}'
            match = re.match(r'W(\d+)', addr)
            if match:
                return f'%MW{match.group(1)}'
        
        return f'%{addr}' if not addr.startswith('%') else addr
    
    def convert_type(self, var_type):
        """转换数据类型"""
        type_map = {
            'BOOL': 'BOOL',
            'INT': 'INT',
            'DINT': 'DINT',
            'UINT': 'UINT',
            'UDINT': 'UDINT',
            'REAL': 'REAL',
            'LREAL': 'LREAL',
            'STRING': 'STRING(255)',
            'BYTE': 'BYTE',
            'WORD': 'WORD',
            'DWORD': 'DWORD',
            'TIME': 'TIME',
        }
        upper_type = var_type.upper().split('(')[0]  # 处理STRING(20)这种情况
        return type_map.get(upper_type, var_type)
    
    def generate_inovance_code(self, body):
        """生成汇川ST代码"""
        print("🔧 生成汇川ST程序...")
        
        lines = []
        lines.append("PROGRAM PLC_PRG")
        lines.append("VAR")
        
        if self.variable_decls:
            for var in self.variable_decls:
                if var['address']:
                    lines.append(f"    {var['name']} AT {var['address']} : {var['type']}; (* {var['comment']} *)")
                else:
                    lines.append(f"    {var['name']} : {var['type']};")
        else:
            lines.append("    (* 请在此处声明变量 *)")
        
        lines.append("END_VAR")
        lines.append("")
        lines.append("(* ========================================== *)")
        lines.append("(* 由 Robot_Qu 工业程序转换器生成 *)")
        lines.append("(* 欧姆龙 (Omron) -> 汇川 (Inovance) *)")
        lines.append("(* 生成时间: " + str(__import__('datetime').datetime.now()) + " *)")
        lines.append("(* ========================================== *)")
        lines.append("")
        lines.append(body.strip())
        lines.append("")
        lines.append("END_PROGRAM")
        
        return '\n'.join(lines)


# ==================== 转换器注册 ====================

CONVERTERS = {
    'robot': {
        ('ABB', 'FANUC'): ABBtoFanuc,
    },
    'plc': {
        ('Omron', 'Inovance'): OmronToInovance,  # 新增
        ('Siemens', 'Mitsubishi'): None,  # 预留
    }
}

# ==================== HTML前端 ====================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Robot_Qu 工业程序转换器 | Robot & PLC Converter</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            min-height: calc(100vh - 40px);
        }
        
        /* Header */
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
        }
        
        .header-left {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        
        .logo-container {
            background: white;
            padding: 8px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        
        .logo-container svg {
            height: 40px;
            width: 80px;
        }
        
        .header-title {
            display: flex;
            flex-direction: column;
        }
        
        h1 {
            font-size: 26px;
            margin: 0;
            font-weight: 700;
        }
        
        .subtitle {
            font-size: 13px;
            opacity: 0.95;
            margin-top: 4px;
        }
        
        .community-badge {
            background: rgba(255, 255, 255, 0.15);
            backdrop-filter: blur(10px);
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 50px;
            padding: 10px 20px;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            font-weight: 500;
        }
        
        /* 主内容 */
        .main-content {
            flex: 1;
            padding: 30px 40px;
            background: #f8f9fa;
        }
        
        .module-title {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 20px;
            font-size: 20px;
            font-weight: 700;
            color: #333;
        }
        
        .module-icon {
            width: 40px;
            height: 40px;
            background: linear-gradient(135deg, #ff69b4, #ff1493);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-size: 20px;
        }
        
        .module-icon.plc { background: linear-gradient(135deg, #00c6ff, #0072ff); }
        
        .converter-wrapper {
            background: white;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            border: 1px solid #e9ecef;
        }
        
        .converter-area {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 20px;
            flex-wrap: wrap;
        }
        
        .panel {
            flex: 1;
            min-width: 250px;
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            border: 2px solid #e9ecef;
            transition: all 0.3s ease;
        }
        
        .panel:hover {
            border-color: #ff69b4;
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(255, 105, 180, 0.1);
        }
        
        .panel.plc:hover {
            border-color: #0072ff;
            box-shadow: 0 5px 20px rgba(0, 114, 255, 0.1);
        }
        
        .panel-title {
            font-size: 16px;
            font-weight: 600;
            color: #333;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .icon-num {
            width: 24px;
            height: 24px;
            background: linear-gradient(135deg, #ff69b4, #ff1493);
            color: white;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
        }
        
        .icon-num.plc { background: linear-gradient(135deg, #00c6ff, #0072ff); }
        
        select {
            width: 100%;
            padding: 10px 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            background: white;
            cursor: pointer;
            transition: border-color 0.3s;
            margin-bottom: 15px;
        }
        
        select:focus { outline: none; border-color: #ff69b4; }
        .panel.plc select:focus { border-color: #0072ff; }
        
        .file-upload {
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            background: white;
            font-size: 13px;
        }
        
        .file-upload:hover {
            border-color: #ff69b4;
            background: #fff0f5;
        }
        
        .panel.plc .file-upload:hover {
            border-color: #0072ff;
            background: #f0f8ff;
        }
        
        .file-upload.active {
            border-color: #28a745;
            background: #d4edda;
        }
        
        input[type="file"] { display: none; }
        
        .upload-filename {
            color: #ff1493;
            font-weight: 600;
            margin-top: 8px;
            word-break: break-all;
            font-size: 12px;
        }
        
        .panel.plc .upload-filename { color: #0072ff; }
        
        .center-area {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 15px;
        }
        
        .convert-btn {
            background: linear-gradient(135deg, #ff69b4 0%, #ff1493 100%);
            color: white;
            border: none;
            padding: 12px 30px;
            border-radius: 50px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            box-shadow: 0 4px 15px rgba(255, 20, 147, 0.4);
            display: flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
        }
        
        .convert-btn.plc {
            background: linear-gradient(135deg, #00c6ff 0%, #0072ff 100%);
            box-shadow: 0 4px 15px rgba(0, 114, 255, 0.4);
        }
        
        .convert-btn:hover:not(:disabled) {
            transform: translateY(-2px) scale(1.05);
        }
        
        .convert-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .arrow {
            font-size: 28px;
            color: #ff69b4;
            animation: pulse 2s infinite;
        }
        
        .center-area.plc .arrow { color: #0072ff; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; transform: translateX(0); }
            50% { opacity: 0.6; transform: translateX(5px); }
        }
        
        .status {
            margin-top: 10px;
            padding: 8px 15px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            display: none;
            text-align: center;
        }
        
        .status.success {
            background: #d4edda;
            color: #155724;
            border: 2px solid #c3e6cb;
            display: block;
        }
        
        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 2px solid #f5c6cb;
            display: block;
        }
        
        .status.loading {
            background: #fff3cd;
            color: #856404;
            border: 2px solid #ffeaa7;
            display: block;
        }
        
        .download-link {
            display: inline-block;
            margin-top: 10px;
            padding: 8px 20px;
            background: linear-gradient(135deg, #28a745, #20c997);
            color: white;
            text-decoration: none;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
        }
        
        .divider {
            height: 1px;
            background: linear-gradient(90deg, transparent, #ddd, transparent);
            margin: 20px 0;
        }
        
        /* Footer */
        footer {
            background: #f8f9fa;
            border-top: 1px solid #e9ecef;
            padding: 20px 40px;
            text-align: center;
            color: #666;
            font-size: 13px;
        }
        
        .footer-text strong { color: #ff1493; }
        
        @media (max-width: 768px) {
            header { flex-direction: column; text-align: center; padding: 20px; }
            .header-left { flex-direction: column; }
            .converter-area { flex-direction: column; }
            .arrow { transform: rotate(90deg); }
            .main-content { padding: 20px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="header-left">
                <div class="logo-container">
                    <svg viewBox="0 0 200 80">
                        <text x="10" y="55" font-family="Arial" font-size="45" font-weight="bold" fill="#ff1493">RQ</text>
                        <text x="75" y="30" font-family="Arial" font-size="11" fill="#333">robotqu.com</text>
                        <path d="M 160 40 L 175 25 L 175 35 L 185 35 L 185 45 L 175 45 L 175 55 Z" fill="#333"/>
                    </svg>
                </div>
                <div class="header-title">
                    <h1>🤖 工业程序转换器</h1>
                    <div class="subtitle">Robot & PLC Program Converter | 支持多品牌互转</div>
                </div>
            </div>
            
            <div class="community-badge">
                <span style="font-size:20px;">🌐</span>
                <span>Robot_Qu 机器人社区<br><small>提供设计支持</small></span>
            </div>
        </header>
        
        <!-- 主内容 -->
        <div class="main-content">
            
            <!-- ==================== 机器人转换模块 ==================== -->
            <div class="converter-wrapper">
                <div class="module-title">
                    <div class="module-icon">🦾</div>
                    <span>机器人程序转换 (Robot)</span>
                </div>
                
                <div class="converter-area">
                    <div class="panel">
                        <div class="panel-title">
                            <span class="icon-num">1</span>
                            源程序（Source）
                        </div>
                        <select id="robotSource">
                            <option value="">选择品牌...</option>
                            <option value="ABB" selected>ABB (RAPID)</option>
                            <option value="FANUC">FANUC (TP/LS)</option>
                            <option value="KUKA" disabled>KUKA (KRL)</option>
                        </select>
                        <div class="file-upload" onclick="document.getElementById('robotFile').click()">
                            <input type="file" id="robotFile" accept=".mod,.ls,.src" onchange="handleFileSelect('robot', this)">
                            <div>📁 点击上传机器人程序<br><small>.mod / .ls / .src</small></div>
                            <div class="upload-filename" id="robotFilename"></div>
                        </div>
                    </div>
                    
                    <div class="center-area">
                        <div class="arrow">➡️</div>
                        <button class="convert-btn" id="robotBtn" onclick="convert('robot')">
                            <span>⚡</span><span>转换</span>
                        </button>
                        <div id="robotStatus" class="status"></div>
                    </div>
                    
                    <div class="panel">
                        <div class="panel-title">
                            <span class="icon-num">2</span>
                            目标程序（Target）
                        </div>
                        <select id="robotTarget">
                            <option value="">选择品牌...</option>
                            <option value="ABB">ABB (RAPID)</option>
                            <option value="FANUC" selected>FANUC (TP/LS)</option>
                            <option value="KUKA" disabled>KUKA (KRL)</option>
                        </select>
                        <div id="robotResult" style="display:none; text-align:center; margin-top:10px;">
                            <div style="font-size:36px; margin-bottom:5px;">✅</div>
                            <div style="font-size:13px; font-weight:600; color:#28a745; margin-bottom:8px;">转换成功</div>
                            <a id="robotDownload" class="download-link" href="#">下载文件</a>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="divider"></div>
            
            <!-- ==================== PLC转换模块（更新：新增欧姆龙→汇川） ==================== -->
            <div class="converter-wrapper">
                <div class="module-title">
                    <div class="module-icon plc">🔌</div>
                    <span>PLC程序转换 (PLC)</span>
                </div>
                
                <div class="converter-area">
                    <div class="panel plc">
                        <div class="panel-title">
                            <span class="icon-num plc">1</span>
                            源程序（Source）
                        </div>
                        <select id="plcSource">
                            <option value="">选择品牌...</option>
                            <!-- 更新：欧姆龙可用，西门子预留 -->
                            <option value="Omron" selected>欧姆龙 Omron (ST)</option>
                            <option value="Siemens">西门子 Siemens (SCL)</option>
                            <option value="Mitsubishi" disabled>三菱 Mitsubishi (ST)</option>
                        </select>
                        <div class="file-upload" onclick="document.getElementById('plcFile').click()">
                            <input type="file" id="plcFile" accept=".st,.scl,.txt,.csv" onchange="handleFileSelect('plc', this)">
                            <div>📁 点击上传PLC程序<br><small>.st / .scl / .txt / 导出文件</small></div>
                            <div class="upload-filename" id="plcFilename"></div>
                        </div>
                    </div>
                    
                    <div class="center-area plc">
                        <div class="arrow">➡️</div>
                        <button class="convert-btn plc" id="plcBtn" onclick="convert('plc')">
                            <span>⚡</span><span>转换</span>
                        </button>
                        <div id="plcStatus" class="status"></div>
                    </div>
                    
                    <div class="panel plc">
                        <div class="panel-title">
                            <span class="icon-num plc">2</span>
                            目标程序（Target）
                        </div>
                        <select id="plcTarget">
                            <option value="">选择品牌...</option>
                            <option value="Inovance" selected>汇川 Inovance (ST)</option>
                            <option value="Mitsubishi" disabled>三菱 Mitsubishi (ST)</option>
                            <option value="Siemens" disabled>西门子 Siemens (SCL)</option>
                        </select>
                        <div id="plcResult" style="display:none; text-align:center; margin-top:10px;">
                            <div style="font-size:36px; margin-bottom:5px;">✅</div>
                            <div style="font-size:13px; font-weight:600; color:#28a745; margin-bottom:8px;">转换成功</div>
                            <a id="plcDownload" class="download-link" href="#">下载文件</a>
                        </div>
                    </div>
                </div>
            </div>
            
        </div>
        
        <!-- Footer -->
        <footer>
            <div class="footer-content">
                <span>© 2024-2025</span>
                <span class="footer-text">
                    本应用由 <strong>Robot_Qu 机器人社区</strong> 提供设计支持
                </span>
                <span>|</span>
                <span style="color:#ff69b4; font-weight:600;">www.robotqu.com</span>
            </div>
        </footer>
    </div>

    <script>
        const files = { robot: null, plc: null };
        
        function handleFileSelect(type, input) {
            if (input.files && input.files[0]) {
                files[type] = input.files[0];
                document.getElementById(type + 'Filename').textContent = input.files[0].name;
                input.parentElement.classList.add('active');
                document.getElementById(type + 'Result').style.display = 'none';
            }
        }
        
        async function convert(type) {
            const source = document.getElementById(type + 'Source').value;
            const target = document.getElementById(type + 'Target').value;
            const file = files[type];
            const status = document.getElementById(type + 'Status');
            const btn = document.getElementById(type + 'Btn');
            const resultDiv = document.getElementById(type + 'Result');
            
            if (!source || !target) {
                status.className = 'status error';
                status.textContent = '❌ 请选择品牌';
                return;
            }
            if (source === target) {
                status.className = 'status error';
                status.textContent = '❌ 源和目标不能相同';
                return;
            }
            if (!file) {
                status.className = 'status error';
                status.textContent = '❌ 请上传文件';
                return;
            }
            
            btn.disabled = true;
            status.className = 'status loading';
            status.textContent = '🔄 转换中...';
            resultDiv.style.display = 'none';
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('source', source);
            formData.append('target', target);
            formData.append('type', type);
            
            try {
                const response = await fetch('/convert', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    status.className = 'status success';
                    status.textContent = '✅ ' + result.message;
                    
                    const downloadLink = document.getElementById(type + 'Download');
                    downloadLink.href = result.download_url;
                    downloadLink.download = result.filename;
                    resultDiv.style.display = 'block';
                } else {
                    status.className = 'status error';
                    status.textContent = '❌ ' + result.message;
                }
            } catch (error) {
                status.className = 'status error';
                status.textContent = '❌ 网络错误';
            } finally {
                btn.disabled = false;
            }
        }
        
        ['robot', 'plc'].forEach(type => {
            document.getElementById(type + 'Source').addEventListener('change', function() {
                const target = document.getElementById(type + 'Target');
                if (this.value === target.value) {
                    target.value = '';
                }
            });
        });
    </script>
</body>
</html>
"""

# ==================== 后端路由 ====================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/convert', methods=['POST'])
def convert():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有上传文件'})
    
    file = request.files['file']
    source = request.form.get('source')
    target = request.form.get('target')
    conv_type = request.form.get('type', 'robot')
    
    if file.filename == '':
        return jsonify({'success': False, 'message': '文件名为空'})
    
    try:
        content = file.read().decode('utf-8', errors='ignore')
        
        # 查找转换器
        type_converters = CONVERTERS.get(conv_type, {})
        converter_class = type_converters.get((source, target))
        
        if converter_class is None:
            available = [f"{k[0]}->{k[1]}" for k in type_converters.keys() if type_converters[k]]
            return jsonify({
                'success': False, 
                'message': f'暂不支持 {source} -> {target}。可用转换: {", ".join(available)}'
            })
        
        # 执行转换
        if conv_type == 'robot':
            converter = converter_class()
            instructions = converter.parse_mod(content)
            result = converter.generate_ls(instructions)
            output_ext = "ls"
            
        elif conv_type == 'plc':
            converter = converter_class()
            result = converter.convert(content)
            output_ext = "txt"  # PLC输出为ST文本
            
        else:
            return jsonify({'success': False, 'message': '未知的转换类型'})
        
        # 保存文件
        safe_filename = "".join(c for c in file.filename if c.isalnum() or c in ('.', '-', '_')).rstrip()
        output_filename = f"{safe_filename.rsplit('.', 1)[0]}_{source}to{target}.{output_ext}"
        output_path = os.path.join('temp', output_filename)
        os.makedirs('temp', exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        
        return jsonify({
            'success': True,
            'message': f'转换成功 ({len(result)} 字符)',
            'download_url': f'/download/{output_filename}',
            'filename': output_filename
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())  # 服务器端打印详细错误
        return jsonify({
            'success': False,
            'message': f'转换出错: {str(e)}'
        })

@app.route('/download/<filename>')
def download(filename):
    try:
        file_path = os.path.join('temp', filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return "文件不存在", 404
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    print("="*70)
    print("🚀 Robot_Qu 工业程序转换器")
    print("支持：")
    print("  - 机器人: ABB → FANUC")
    print("  - PLC: 欧姆龙(Omron) → 汇川(Inovance)")
    print("="*70)
    print("访问: http://localhost:5000")
    print("按 Ctrl+C 停止")
    print("="*70)
    # 生产环境建议关闭debug
    app.run(debug=True, port=5000, host='0.0.0.0')