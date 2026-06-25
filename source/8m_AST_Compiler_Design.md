# 网络交换芯片 AST 编译器设计方案

## 基于 8mSpec_0821.c 和 tinyReg.txt 规范的编译器开发

---

## 目录

1. [概述](#1-概述)
2. [语言特征分析](#2-语言特征分析)
3. [编译器整体架构](#3-编译器整体架构)
4. [词法分析器设计](#4-词法分析器设计)
5. [语法分析器与AST数据结构](#5-语法分析器与ast数据结构)
6. [语义分析器设计](#6-语义分析器设计)
7. [C 代码生成器](#7-c-代码生成器)
8. [RTL/Verilog 生成器](#8-rtlverilog-生成器)
9. [编译管道与工具链](#9-编译管道与工具链)
10. [实现优先级与迭代路线](#10-实现优先级与迭代路线)
11. [关键难点与应对策略](#11-关键难点与应对策略)
12. [代码文件结构建议](#12-代码文件结构建议)

---

## 1. 概述

### 1.1 项目目标

开发一套面向网络交换芯片规范的 AST（抽象语法树）编译器，能够对 `tinyReg.txt` 和 `8mSpec_0821.c` 中定义的伪代码和寄存器规范进行：

- **词法分析（Lexical Analysis）**：将源文件拆解为 Token 流
- **语法分析（Syntax Analysis）**：构建抽象语法树（AST）
- **语义分析（Semantic Analysis）**：类型检查、符号解析、依赖性分析
- **代码生成（Code Generation）**：
  - **C 代码生成器**：输出可编译的 C 仿真模型和寄存器驱动
  - **RTL 代码生成器**：输出可综合的 Verilog/SystemVerilog 硬件描述

### 1.2 输入文件说明

| 文件 | 格式 | 内容 | 用途 |
|------|------|------|------|
| `tinyReg.txt` | 表格格式 DSL | 寄存器/内存表定义、地址映射、位域描述 | 寄存器模型、地址解码、驱动代码 |
| `8mSpec_0821.c` | 类 C 行为 DSL | 包处理流程、转发逻辑、老化机制、优先级分配 | 硬件行为、仿真模型、RTL 生成 |

### 1.3 DSL 语言本质

两个规范文件的本质是**硬件描述语言（HDL）** 的 DSL 变体，具有以下核心特征：

- **tinyReg.txt**：声明式 DSL，定义寄存器和内存映射表的结构
- **8mSpec_0821.c**：行为式 DSL，使用 C 语法描述硬件并发行为

两者的共同点是都围绕**寄存器-内存-位域**模型展开，有别于标准软件语言的硬件事物语义。

---

## 2. 语言特征分析

### 2.1 tinyReg.txt 语法特征

#### 2.1.1 文件结构

```
FileName    Prefix      AddrUpper   AddrLower   FlopInput
tinyReg     TINY_       17          2           Y
```

- 第1行为**列头**（Header），定义后续数据行的字段名
- 第2行为全局配置（文件名前缀、地址位宽范围等）

#### 2.1.2 内存表定义（MemReg）

```
RegMem      FullName    NumOfEntries  Words  MemAddrBits  DecodeAddress              Description
DsMac       DsMac       2048          1      11           16'b00_100?_????_????_??   DsMac RamTable
```

| 字段 | 含义 | 示例 |
|------|------|------|
| `RegMem` | 内存表名称（短名） | `DsMac` |
| `FullName` | 全名 | `DsMac` |
| `NumOfEntries` | 条目数（深度） | `2048` |
| `Words` | 每条目占 Word 数 | `1` |
| `MemAddrBits` | 地址位宽 | `11` |
| `DecodeAddress` | 地址解码模式 | `16'b00_100?_????_????_??` |
| `Description` | 描述 | `DsMac RamTable` |

其中 `DecodeAddress` 的 `?` 表示通配位，用于地址解码匹配。

#### 2.1.3 内存表字段定义（MemRegFields）

```
MemRegFields    DsMac
Fields  Offset  HiBit   LoBit   ReadTrigger WriteTrigger    Description
destMap 0       9       0       Y           N               destMap field
prior   0       13      12      N           Y               prior field
```

| 字段 | 含义 | 示例 |
|------|------|------|
| `Fields` | 字段名称 | `destMap` |
| `Offset` | 所在 Word 偏移 | `0` |
| `HiBit` | 高位位置 | `9` |
| `LoBit` | 低位位置 | `0` |
| `ReadTrigger` | 读触发（Y/N） | `Y` |
| `WriteTrigger` | 写触发（Y/N） | `N` |

#### 2.1.4 寄存器定义（Register）

```
Register        FullName        Words   DecodeAddress               Description
L2AgingCtl      L2AgingCtl      2       16'b10_1000_0000_0000_0?   L2AgingCtl register
```

#### 2.1.5 寄存器字段定义（Fields）

```
Fields  Offset  HiBit   LoBit   ReadOnly  ReadIndicate  WriteIndicate  WriteOneIndicate  Description            L2AgingCtl
agingEn 0       1       1       N         N             N              N                 agingEn register       1
```

寄存器字段比内存表字段多了：
- `ReadOnly`：是否只读
- `ReadIndicate`：读指示
- `WriteIndicate`：写指示
- `WriteOneIndicate`：写1指示
- **最后一列**是默认/复位值（如 `1`、`4'b0`、`32'b0`）

### 2.2 8mSpec_0821.c 语法特征

#### 2.2.1 类型系统

| 伪C类型 | 含义 | 宽度（bit） | 对应 Verilog 类型 |
|---------|------|-------------|-------------------|
| `bool` | 布尔值 | 1 | `wire/reg` |
| `uint3` | 无符号3位整数 | 3 | `[2:0]` |
| `uint4` | 无符号4位整数 | 4 | `[3:0]` |
| `uint8` | 无符号8位整数 | 8 | `[7:0]` |
| `uint12` | 无符号12位整数 | 12 | `[11:0]` |
| `uint16` | 无符号16位整数 | 16 | `[15:0]` |
| `uint48` | 无符号48位整数 | 48 | `[47:0]` |
| `uintN` | 通用N位无符号整数 | N | `[N-1:0]` |

#### 2.2.2 变量声明语法

```
// 无类型全局数组
uint8 PacketByte[];

// 定宽全局变量 + 位域定义
uint16 piSrcPort[2:0] = channelId[2:0];
uint16 piPktLength[11:0] = packetLength[11:0];

// 过程内变量
giStormIdx[4:0] = 0;
giAgingIdx[10:0] = 0;
giCycleCnt[31:0]++;
```

语法特点：
- 声明时使用 `[hi:lo]` 同时表示位宽和初始赋值
- 类型可省略（如 `giStormIdx[4:0] = 0;`）
- `++` 操作符支持任意位宽

#### 2.2.3 结构体定义

```
struct ParserResult{
    uint48 macDa;
    uint48 macSa;
    uint3  vlanPrior;
    uint12 vlanId;
    uint2  vlanTagged;
    bool   isLoopDetection;
    uint4  loopTtl;
    bool   isArp;
    bool   isIpv4;
    bool   isIpv6;
    uint8  ipDscp;
    bool   isUnknownPkt;
}
```

注意：结构体末尾**没有分号**，与标准 C 不同。

#### 2.2.4 并发过程（Process）

```
process forward() {
    while(1) {
        parser();
        switchX();
        egress();
    }
}
```

- `process XXX() { ... }` 定义硬件并发过程
- `while(1)` 在硬件语义中表示"每周期执行"或"持续运行"
- 多个 `process` 块之间隐含并发关系

#### 2.2.5 Table 访问语法

```
// 读表
DsMac = DsMac Table[ giHashIdx ];
DsPort = DsPort Table[ piSrcPort ];
DsMacKey = DsMacKey Table[ giHashIdx ];

// 写表
update DsMacKey using newDsMacKeyEntry at { giLrnHash }.{ giLrnSubIdx };
update DsMac using newDsMacEntry at { giLrnHash, giLrnSubIdx };
```

语法结构：
```
<target> = <table_name> Table[ <index_expr> ];
update <table_name> using <value_expr> at <address_expr>;
```

#### 2.2.6 位域操作

```
// 位切片读取
prMacDa[47:0] = {PacketByte0, ..., PacketByte5};
prVlanPrior[2:0] = PacketByte[ giPldOffset ][7:5];
DsMac.destMap[ L2AgingCtl.portId[3:0] ]

// 位切片写入
DsMacValid.valid[ giAgingPtr[1:0] ] = 0;
DsMacValid.valid[ giAgingPtr[1:0] ] = 1'b0;

// 复合字段访问（特殊语法）
DsMacKey.{ fid[11:0], macAddr[47:0] } == { giFid, prMacDa }
DsMacKey.{ fid{i}, macAddr{i} } == { giFid, prMacSa }

// 字段索引（花括号下标）
DsMacAging.aging{ giAgingIdx[1:0] } < 3
DsMacAging.aging{ giLrnSubIdx } = 0
```

关键语法点：
- `[hi:lo]` — 位域范围选取
- `[expr]` — 数组索引或位索引
- `.{ field1, field2 }` — 复合字段访问（连续位域组合）
- `{ expr1, expr2 }` — 位拼接
- `field{ idx_expr }` — 字段内子索引（通过位宽对齐间接寻址）
- `{ subscript1, subscript2 }` — 多维地址

#### 2.2.7 硬件原语操作

```
// 延迟
Delay( StormCfgCtl.delayInterval[31:0] );

// 发送包
send Loop Detect packet { 0xFFFF_FFFF_FFFF, ..., 352'b0};

// 替换包字节
Replace PacketBypte[6] to PacketBypte[11] using LoopDetectCtl.loopMac[47:0];

// 插入包字节
Insert newVlanTag after PacketByte[11];

// 移除包字节
remove PacketByte[12] ... PacketByte[15];

// 入队
Enqueue PacketByte with updated header waiting for outgoing;
```

#### 2.2.8 case 范围匹配

```
switch( prMacDa[7:0] ) {
    0x00: if( piRmaMode ) { piDiscard = 1; }
    0x11~1f: if( piRmaMode ) { piDiscard = 1; }
    0x31~3f: if( piRmaMode ) { piDiscard = 1; }
}
```

`~` 用于表示 case 值的连续范围匹配，非标准 C 语法。

---

## 3. 编译器整体架构

### 3.1 架构总览

```
┌───────────────────────────────────────────────────────────────────────┐
│                          Source Files                                │
│                 tinyReg.txt            8mSpec_0821.c                  │
└─────────────────────────┬─────────────────────┬───────────────────────┘
                          │                     │
                          ▼                     ▼
              ┌─────────────────────┐ ┌─────────────────────┐
              │   RegMap Lexer      │ │   PseudoC Lexer     │
              │   (tabular parser)  │ │   (tokenizer)       │
              └──────────┬──────────┘ └──────────┬──────────┘
                         │                       │
                         ▼                       ▼
              ┌─────────────────────┐ ┌─────────────────────┐
              │   RegMap Parser     │ │   PseudoC Parser    │
              │   (build RegMapIR)  │ │   (build PseudoCIR) │
              └──────────┬──────────┘ └──────────┬──────────┘
                         │                       │
                         ▼                       ▼
              ┌────────────────────────────────────────────────────┐
              │              Semantic Analyzer                    │
              │   • Type checking (bit-width validation)          │
              │   • Symbol resolution (register/field lookup)    │
              │   • Table access validation                      │
              │   • Trigger dependency analysis                  │
              └──────────────────────┬─────────────────────────────┘
                                     │
                                     ▼
              ┌────────────────────────────────────────────────────┐
              │               Unified AST (IR)                    │
              │   • Module hierarchy                              │
              │   • Process graph                                 │
              │   • Type definitions                              │
              │   • Register/memory map                           │
              │   • Control flow graph                            │
              │   • Data flow graph                               │
              └──────┬─────────────────────────────┬───────────────┘
                     │                             │
                     ▼                             ▼
    ┌──────────────────────────────┐  ┌──────────────────────────────┐
    │      C Code Generator        │  │     RTL Code Generator      │
    │                              │  │                              │
    │  • Behavior model (sim)      │  │  • Verilog/VHDL output      │
    │  • Register driver code      │  │  • Register RTL             │
    │  • Testbench generation      │  │  • Memory/RAM instances     │
    │  • uC firmware skeleton      │  │  • FSM + datapath           │
    └─────────────┬────────────────┘  └──────────────┬───────────────┘
                  │                                   │
                  ▼                                   ▼
          [8m_c_model.c]                    [8m_rtl.v / 8m_rtl.sv]
          [8m_reg_drv.c/.h]                [8m_reg_rtl.v]
          [8m_tb.c]                         [8m_ram_wrap_*.v]
```

### 3.2 各阶段职责

| 阶段 | 输入 | 输出 | 职责 |
|------|------|------|------|
| **预处理** | `.c` / `.txt` | 清理后的源码 | 移除注释、展开宏、处理 `...` 占位符 |
| **词法分析** | 源码字符串 | Token 流 | 将源码拆解为有意义的词法单元 |
| **语法分析** | Token 流 | AST | 根据文法规则构建抽象语法树 |
| **语义分析** | AST | 标注后的 AST | 类型检查、符号解析、依赖分析 |
| **IR 构建** | 标注 AST | 统一中间表示 | 合并两个源文件的 IR，统一数据模型 |
| **代码生成** | IR | 目标代码 | 根据目标语言生成代码 |
| **代码输出** | 目标代码字符串 | `.c` / `.v` / `.sv` 文件 | 格式化输出到文件 |

### 3.3 数据流

```
tinyReg.txt ──► RegMap解析 ──┐
                              ├──► 符号表合并 ──► 语义分析 ──► IR ──► 代码生成
8mSpec.c    ──► PseudoC解析 ─┘
```

RegMap 解析器先运行，为 PseudoC 解析器提供寄存器/内存表符号定义，PseudoC 解析器在语义分析阶段可以正确解析 `DsMac.field`、`L2AgingCtl.agingEn` 等符号。

---

## 4. 词法分析器设计

### 4.1 RegMap Lexer（针对 tinyReg.txt）

由于 tinyReg.txt 是表格格式，词法分析相对简单，按行解析并分割字段。

#### 4.1.1 Token 类型

| Token 类型 | 匹配模式 | 示例 |
|-----------|---------|------|
| `SECTION_HEADER` | `RegMem`、`MemRegFields`、`Register`、`Fields` | `RegMem` |
| `COLUMN_HEADER` | 第1行各列名 | `FullName`、`NumOfEntries` |
| `IDENTIFIER` | 字母数字组合 | `DsMac`、`prior`、`L2AgingCtl` |
| `INTEGER` | 十进制数字 | `8`、`64`、`2048`、`512` |
| `BIN_PATTERN` | `N'b` 格式 | `16'b00_100?_????_????_??` |
| `BIN_VALUE` | `N'b` 数值 | `1'b0`、`12'b0`、`32'b0` |
| `TRIGGER` | `Y` / `N` | `Y`、`N` |
| `SEPARATOR` | 制表符 `\t` | — |
| `NEWLINE` | 换行符 `\n` | — |

#### 4.1.2 解析策略

```
行类型判断:
  第1行 → 列头行，读取所有列名
  第2行 → 全局配置行（文件名、前缀等）
  RegMem 开头的行 → 内存表声明
  MemRegFields 开头的行 → 内存表字段段的开始
  Register 开头的行 → 寄存器声明
  Fields 开头的行 → 寄存器字段段的开始
  其他 → 根据当前段类型解析为对应数据行

每行解析:
  以制表符 \t 分割
  根据当前段的列头映射到对应字段
```

### 4.2 PseudoC Lexer（针对 8mSpec_0821.c）

需要更复杂的正则表达式基础词法分析。

#### 4.2.1 关键字列表

```
process, void, while, for, switch, case, break, default,
if, else, return, struct, bool, uint, int,
Table, Delay, Enqueue, Replace, Insert, remove, update,
send, using, at, to, after
```

#### 4.2.2 操作符/分隔符

| 符号 | Token 名称 | 说明 |
|------|-----------|------|
| `{` | `LBRACE` | 块开始 / 拼接开始 |
| `}` | `RBRACE` | 块结束 / 拼接结束 |
| `[` | `LBRACKET` | 数组下标 / 位域开始 |
| `]` | `RBRACKET` | 数组结束 / 位域结束 |
| `(` | `LPAREN` | 表达式分组 / 函数调用 |
| `)` | `RPAREN` | 分组结束 |
| `.` | `DOT` | 成员访问 |
| `:` | `COLON` | 位域范围 |
| `;` | `SEMICOLON` | 语句结束 |
| `=` | `ASSIGN` | 赋值 |
| `==` | `EQ` | 相等比较 |
| `!=` | `NE` | 不等比较 |
| `&&` | `LOGICAL_AND` | 逻辑与 |
| `\|\|` | `LOGICAL_OR` | 逻辑或 |
| `!` | `LOGICAL_NOT` | 逻辑非 |
| `&` | `BITWISE_AND` | 位与 |
| `\|` | `BITWISE_OR` | 位或 |
| `~` | `BITWISE_NOT` | 位非 / 范围 |
| `<<` | `SHIFT_LEFT` | 左移 |
| `>>` | `SHIFT_RIGHT` | 右移 |
| `+` | `PLUS` | 加 |
| `-` | `MINUS` | 减 / 负号 |
| `*` | `STAR` | 乘 |
| `/` | `SLASH` | 除 |
| `%` | `MOD` | 取模 |
| `>` | `GT` | 大于 |
| `>=` | `GE` | 大于等于 |
| `<` | `LT` | 小于 |
| `<=` | `LE` | 小于等于 |
| `,` | `COMMA` | 逗号分隔 |
| `++` | `INC` | 自增 |
| `--` | `DEC` | 自减 |
| `+=` | `ADD_ASSIGN` | 加赋值 |
| `-=` | `SUB_ASSIGN` | 减赋值 |
| `&=` | `AND_ASSIGN` | 位与赋值 |
| `\|=` | `OR_ASSIGN` | 位或赋值 |
| `<<=` | `SHL_ASSIGN` | 左移赋值 |
| `>>=` | `SHR_ASSIGN` | 右移赋值 |
| `?:` | `TERNARY` | 三目运算符 |
| `~` | `RANGE` | 范围（case 中 `0x11~1f`） |
| `...` | `ELLIPSIS` | 连续省略（`PacketByte0, ..., PacketByte5`） |
| `_` | `UNDERSCORE` | 数字字面量分隔符（`0xFFFF_FFFF`） |

#### 4.2.3 字面量格式

```
整数常量:
  十进制:    123, 0, 1
  二进制:    1'b0, 2'b01, 16'b0
  十六进制:  0xFFFF, 0x8899, 0x7FF, 0x0180c20000
  带下划线:  0xFFFF_FFFF, 0x00_0000_0000_000?

类型字面量:
  uint3, uint4, uint8, uint12, uint48
  bool
  int
```

#### 4.2.4 注释处理

```
块注释:    /* ... */
行注释:    // ...
特殊注释:  // none (空操作标记)
```

#### 4.2.5 特殊 Token 序列

```
// 复合字段访问前缀
.{   →   DOT LBRACE  (但需要语义标记为 COMPOSITE_FIELD_ACCESS)

// 范围 Case
0x11~1f  →  0x11 RANGE 0x1f  (范围表达式)

// 二进制字面量
16'b00_100?_????_????_??  →  BIN_LITERAL("00_100?_????_????_??")
```

### 4.3 词法分析器代码示例（Python 框架）

```python
from enum import Enum, auto

class TokenType(Enum):
    # 关键字
    PROCESS = auto()
    VOID = auto()
    WHILE = auto()
    FOR = auto()
    SWITCH = auto()
    CASE = auto()
    BREAK = auto()
    DEFAULT = auto()
    IF = auto()
    ELSE = auto()
    RETURN = auto()
    STRUCT = auto()
    BOOL = auto()
    UINT = auto()

    # 操作符
    ASSIGN = auto()
    EQ = auto()
    NE = auto()
    LOGICAL_AND = auto()
    LOGICAL_OR = auto()
    # ... 省略其他

    # 字面量
    IDENTIFIER = auto()
    INT_LITERAL = auto()
    BIN_LITERAL = auto()
    HEX_LITERAL = auto()

    # 符号
    LBRACE = auto()
    RBRACE = auto()
    SEMICOLON = auto()
    DOT = auto()
    COLON = auto()
    COMMA = auto()


class Token:
    def __init__(self, type: TokenType, value: str, line: int, column: int):
        self.type = type
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self):
        return f"Token({self.type}, '{self.value}', L{self.line}:{self.column})"


class PseudoCLexer:
    """8mSpec_0821.c 词法分析器"""

    # 关键字映射
    keywords = {
        'process': TokenType.PROCESS,
        'void': TokenType.VOID,
        'while': TokenType.WHILE,
        'for': TokenType.FOR,
        'switch': TokenType.SWITCH,
        'case': TokenType.CASE,
        'if': TokenType.IF,
        'else': TokenType.ELSE,
        'struct': TokenType.STRUCT,
        'bool': TokenType.BOOL,
        'uint': TokenType.UINT,
        'Table': TokenType.TABLE,
        'Delay': TokenType.DELAY,
        'Enqueue': TokenType.ENQUEUE,
        'Replace': TokenType.REPLACE,
        'Insert': TokenType.INSERT,
        'remove': TokenType.REMOVE,
        'update': TokenType.UPDATE,
        'send': TokenType.SEND,
        'using': TokenType.USING,
        'at': TokenType.AT,
        'to': TokenType.TO,
        'after': TokenType.AFTER,
    }

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens = []

    def tokenize(self) -> list[Token]:
        """执行词法分析，返回 Token 列表"""
        while self.pos < len(self.source):
            char = self.source[self.pos]

            if char.isspace() and char != '\n':
                self._advance()
            elif char == '\n':
                self._newline()
            elif char == '/':
                self._handle_comment_or_divide()
            elif char.isdigit() or char == '0':
                self._read_number()
            elif char.isalpha() or char == '_':
                self._read_identifier_or_keyword()
            else:
                self._read_operator_or_symbol()

        return self.tokens

    def _advance(self):
        """前进一个字符"""
        self.pos += 1
        self.column += 1

    def _newline(self):
        """处理换行"""
        self.tokens.append(Token(TokenType.NEWLINE, '\n', self.line, self.column))
        self.pos += 1
        self.line += 1
        self.column = 1

    def _handle_comment_or_divide(self):
        """处理注释或除号"""
        if self.pos + 1 < len(self.source):
            if self.source[self.pos + 1] == '/':
                self._skip_line_comment()
            elif self.source[self.pos + 1] == '*':
                self._skip_block_comment()
            else:
                self.tokens.append(Token(TokenType.SLASH, '/', self.line, self.column))
                self._advance()

    def _skip_line_comment(self):
        """跳过行注释 //"""
        while self.pos < len(self.source) and self.source[self.pos] != '\n':
            self._advance()

    def _skip_block_comment(self):
        """跳过块注释 /* */"""
        self._advance()
        self._advance()
        while self.pos + 1 < len(self.source):
            if self.source[self.pos] == '*' and self.source[self.pos + 1] == '/':
                self._advance()
                self._advance()
                return
            if self.source[self.pos] == '\n':
                self.line += 1
                self.column = 1
            self._advance()

    def _read_number(self):
        """读取数字字面量"""
        start = self.pos
        # 检测二进制字面量: N'b...
        if self.pos + 2 < len(self.source):
            if self.source[self.pos].isdigit() and \
               self.source[self.pos + 1] == "'" and \
               self.source[self.pos + 2] in 'bB':
                # 二进制字面量
                while self.pos < len(self.source) and \
                      (self.source[self.pos].isdigit() or \
                       self.source[self.pos] in "'bB_?"):
                    self._advance()
                value = self.source[start:self.pos]
                self.tokens.append(Token(TokenType.BIN_LITERAL, value, self.line, start))
                return

        # 检测十六进制: 0x...
        if self.source[self.pos] == '0' and self.pos + 1 < len(self.source) and \
           self.source[self.pos + 1] in 'xX':
            self._advance()
            self._advance()
            while self.pos < len(self.source) and \
                  (self.source[self.pos].isdigit() or \
                   self.source[self.pos] in 'abcdefABCDEF_'):
                self._advance()
            value = self.source[start:self.pos]
            self.tokens.append(Token(TokenType.HEX_LITERAL, value, self.line, start))
            return

        # 十进制
        while self.pos < len(self.source) and self.source[self.pos].isdigit():
            self._advance()
        value = self.source[start:self.pos]
        self.tokens.append(Token(TokenType.INT_LITERAL, value, self.line, start))

    def _read_identifier_or_keyword(self):
        """读取标识符或关键字"""
        start = self.pos
        while self.pos < len(self.source) and \
              (self.source[self.pos].isalnum() or self.source[self.pos] == '_'):
            self._advance()
        word = self.source[start:self.pos]

        # 检测 uint3、uint12 等类型字
        if word.startswith('uint') and word[4:].isdigit():
            self.tokens.append(Token(TokenType.UINT_TYPE, word, self.line, start))
        elif word in self.keywords:
            self.tokens.append(Token(self.keywords[word], word, self.line, start))
        else:
            self.tokens.append(Token(TokenType.IDENTIFIER, word, self.line, start))

    def _read_operator_or_symbol(self):
        """读取操作符或符号"""
        char = self.source[self.pos]
        next_char = self.source[self.pos + 1] if self.pos + 1 < len(self.source) else ''

        # 复合操作符
        if char == '=' and next_char == '=':
            self.tokens.append(Token(TokenType.EQ, '==', self.line, self.column))
            self._advance(); self._advance()
        elif char == '!' and next_char == '=':
            self.tokens.append(Token(TokenType.NE, '!=', self.line, self.column))
            self._advance(); self._advance()
        elif char == '&' and next_char == '&':
            self.tokens.append(Token(TokenType.LOGICAL_AND, '&&', self.line, self.column))
            self._advance(); self._advance()
        # ... 其他操作符
        elif char == '.':
            self.tokens.append(Token(TokenType.DOT, '.', self.line, self.column))
            self._advance()
        elif char == '{':
            self.tokens.append(Token(TokenType.LBRACE, '{', self.line, self.column))
            self._advance()
        elif char == '}':
            self.tokens.append(Token(TokenType.RBRACE, '}', self.line, self.column))
            self._advance()
        elif char == ';':
            self.tokens.append(Token(TokenType.SEMICOLON, ';', self.line, self.column))
            self._advance()
        else:
            # 单字符操作符
            self.tokens.append(Token(TokenType(char), char, self.line, self.column))
            self._advance()
```

---

## 5. 语法分析器与AST数据结构

### 5.1 解析策略选择

推荐使用**递归下降解析（Recursive Descent Parsing）** + **算符优先级解析（Precedence Climbing）**：

| 方法 | 适用场景 | 优点 |
|------|---------|------|
| 递归下降 | 语句级解析、声明解析 | 直观易实现、错误定位准确 |
| 算符优先级 | 表达式解析 | 简洁、易于扩展运算符 |
| Table-Driven | 整体语法 | 适合 LALR(1) 文法但实现复杂 |

### 5.2 AST 节点层次结构

```
ASTNode (抽象基类)
│
├── TranslationUnit           # 顶层节点，包含所有定义
│   ├── regMapDefs: RegMapDef[]
│   └── pseudoCModel: PseudoCModel
│
├── RegMapDef                 # tinyReg.txt 顶层定义
│   ├── MemTableDecl          # 内存表声明
│   └── RegisterDecl          # 寄存器声明
│
├── FieldDecl                 # 位域声明 (通用)
│   ├── name: string
│   ├── offset: int           # Word 偏移
│   ├── hiBit: int            # 高位
│   ├── loBit: int            # 低位
│   ├── readTrigger: bool     # 读触发
│   ├── writeTrigger: bool    # 写触发
│   ├── readOnly: bool        # [Register] 只读
│   ├── defaultValue: Expr    # [Register] 默认值
│   └── description: string
│
├── PseudoCModel              # 8mSpec_0821.c 模型
│   ├── globalDecls: GlobalVarDecl[]
│   ├── structDefs: StructDef[]
│   ├── processDefs: ProcessDef[]
│   └── functionDefs: FunctionDef[]
│
├── Type (类型系统)
│   ├── BitVectorType(width: int)    # uint3, uint12, etc.
│   ├── BoolType
│   ├── StructType(name, fields)
│   ├── ArrayType(baseType, size?)
│   └── TableType(baseType, indexWidth)
│
├── Stmt (语句基类)
│   ├── CompoundStmt
│   ├── WhileStmt
│   ├── ForStmt
│   ├── IfStmt
│   ├── SwitchStmt
│   ├── CaseStmt
│   ├── AssignStmt
│   ├── CompoundAssignStmt    # +=, -=, &=, etc.
│   ├── IncDecStmt            # ++, --
│   ├── TableReadStmt
│   ├── TableWriteStmt
│   ├── ExprStmt
│   ├── ReturnStmt
│   ├── BreakStmt
│   ├── VarDeclStmt
│   ├── DelayStmt
│   ├── EnqueueStmt
│   ├── ReplaceStmt
│   ├── InsertStmt
│   ├── RemoveStmt
│   └── SendStmt
│
├── Expr (表达式基类)
│   ├── IdentifierExpr
│   ├── IntLiteral
│   ├── BinLiteral
│   ├── HexLiteral
│   ├── BoolLiteral
│   ├── BinaryOpExpr
│   ├── UnaryOpExpr
│   ├── TernaryExpr
│   ├── FieldAccessExpr
│   ├── BitSliceExpr
│   ├── BitIndexExpr
│   ├── FieldIndexExpr       # aging{ idx } 花括号索引
│   ├── CompositeFieldExpr   # .{ fid, macAddr }
│   ├── ConcatExpr           # { a, b, c }
│   ├── FunctionCallExpr
│   ├── MaxMinExpr           # Max(a, b, c)
│   ├── RangeExpr            # 0x11~0x1f
│   └── EllipsisExpr         # ... (占位符)
```

### 5.3 Parser 文法规则（EBNF）

```
// === 顶层结构 ===
translation_unit
    : global_declaration*
    | struct_definition*
    | process_definition*
    | function_definition*
    ;

// === 声明 ===
global_declaration
    : type_spec identifier bit_range? ('=' expr)? ';'
    ;

struct_definition
    : 'struct' identifier '{' field_declaration* '}'
    ;

field_declaration
    : type_spec identifier ';'
    ;

// === 过程/函数 ===
process_definition
    : 'process' identifier '(' ')' compound_statement
    ;

function_definition
    : type_spec identifier '(' parameter_list? ')' compound_statement
    ;

// === 语句 ===
statement
    : compound_statement
    | if_statement
    | while_statement
    | for_statement
    | switch_statement
    | assignment_statement
    | table_read_statement
    | table_write_statement
    | hw_primitive_statement
    | expression_statement
    | return_statement
    | break_statement
    ;

compound_statement
    : '{' statement* '}'
    ;

if_statement
    : 'if' '(' expression ')' statement ('else' statement)?
    ;

while_statement
    : 'while' '(' expression ')' statement
    ;

for_statement
    : 'for' '(' expression? ';' expression? ';' expression? ')' statement
    ;

switch_statement
    : 'switch' '(' expression ')' '{' case_statement* '}'
    ;

case_statement
    : 'case' expression ( '~' expression )? ':' statement
    ;

assignment_statement
    : lhs_expression assignment_operator expression ';'
    ;

assignment_operator
    : '='
    | '+='
    | '-='
    | '&='
    | '|='
    ;

table_read_statement
    : identifier '=' identifier 'Table' '[' expression ']' ';'
    ;

table_write_statement
    : 'update' identifier 'using' expression 'at' address_expression ';'
    ;

address_expression
    : '{' expression ( ',' expression )* '}' ( '.' '{' expression '}' )?
    ;

hw_primitive_statement
    : 'Delay' '(' expression ')' ';'
    | 'Enqueue' expression ';'
    | 'Replace' identifier '[' expression ']' 'to' identifier '[' expression ']' 'using' expression ';'
    | 'Insert' expression 'after' identifier '[' expression ']' ';'
    | 'remove' identifier '[' expression ']' '...' identifier '[' expression ']' ';'
    | 'send' identifier? '{' expression_list '}' ';'
    ;

// === 表达式（算符优先级） ===
expression
    : ternary_expression
    ;

ternary_expression
    : logical_or_expression ('?' expression ':' expression)?
    ;

logical_or_expression
    : logical_and_expression ('||' logical_and_expression)*
    ;

logical_and_expression
    : bitwise_or_expression ('&&' bitwise_or_expression)*
    ;

bitwise_or_expression
    : bitwise_xor_expression ('|' bitwise_xor_expression)*
    ;

bitwise_xor_expression
    : bitwise_and_expression ('^' bitwise_and_expression)*
    ;

bitwise_and_expression
    : equality_expression ('&' equality_expression)*
    ;

equality_expression
    : relational_expression (('==' | '!=') relational_expression)*
    ;

relational_expression
    : shift_expression (('<' | '>' | '<=' | '>=') shift_expression)*
    ;

shift_expression
    : additive_expression (('<<' | '>>') additive_expression)*
    ;

additive_expression
    : multiplicative_expression (('+' | '-') multiplicative_expression)*
    ;

multiplicative_expression
    : unary_expression (('*' | '/' | '%') unary_expression)*
    ;

unary_expression
    : ('!' | '~' | '-') unary_expression
    | postfix_expression
    ;

postfix_expression
    : primary_expression
    | postfix_expression '[' expression ']'            // 数组/位域下标
    | postfix_expression '[' expression ':' expression ']'  // 位域范围
    | postfix_expression '{' expression '}'            // 字段索引 (aging{idx})
    | postfix_expression '.' identifier                // 字段访问
    | postfix_expression '.' '{' identifier_list '}'   // 复合字段访问
    | postfix_expression '(' expression_list? ')'       // 函数调用
    | postfix_expression ('++' | '--')                 // 后置自增/减
    ;

primary_expression
    : identifier
    | int_literal
    | bin_literal
    | hex_literal
    | '(' expression ')'
    | '{' expression_list '}'                          // 拼接表达式
    | 'Max' '(' expression_list ')'
    ;
```

### 5.4 特殊语法解析策略

#### 5.4.1 复合字段访问 `.{…}`

```python
def parse_postfix_expression(self):
    """解析后缀表达式"""
    expr = self.parse_primary_expression()

    while True:
        if self.peek() == '.':
            self.advance()
            if self.peek() == '{':
                # .{ fid[11:0], macAddr[47:0] }  复合字段访问
                self.advance()  # 跳过 {
                fields = []
                while self.peek() != '}':
                    field_name = self.expect(TokenType.IDENTIFIER)
                    bit_slice = None
                    if self.peek() == '[':
                        hi = self.advance()  # [
                        lo = self.advance()  # :
                        bit_slice = (hi, lo)
                        self.advance()  # ]
                    fields.append((field_name, bit_slice))
                    if self.peek() == ',':
                        self.advance()
                self.advance()  # 跳过 }
                expr = CompositeFieldExpr(expr, fields)
            else:
                # .field  普通字段访问
                name = self.expect(TokenType.IDENTIFIER)
                expr = FieldAccessExpr(expr, name)
        elif self.peek() == '{':
            # aging{ idx }  花括号索引
            self.advance()
            idx = self.parse_expression()
            self.expect('}')
            expr = FieldIndexExpr(expr, idx)
        # ... 其他后缀操作
        else:
            break
```

#### 5.4.2 Table 读写语句

```python
def parse_table_read_statement(self):
    """解析 'table_var = table_var Table[ index ];'"""
    target = IdentifierExpr(self.expect(TokenType.IDENTIFIER))
    self.expect('=')
    table_name = self.expect(TokenType.IDENTIFIER)
    self.expect(TokenType.TABLE)
    self.expect('[')
    index = self.parse_expression()
    self.expect(']')
    self.expect(';')
    return TableReadStmt(target, table_name, index)

def parse_table_write_statement(self):
    """解析 'update table using value at address;'"""
    self.expect(TokenType.UPDATE)
    table_name = self.expect(TokenType.IDENTIFIER)
    self.expect(TokenType.USING)
    value = self.parse_expression()
    self.expect(TokenType.AT)
    address = self.parse_address_expression()
    self.expect(';')
    return TableWriteStmt(table_name, value, address)
```

#### 5.4.3 范围 Case

```python
def parse_case_statement(self):
    """解析 case 分支，支持 0x11~1f 范围语法"""
    self.expect(TokenType.CASE)
    start = self.parse_expression()

    if self.peek() == '~':
        self.advance()  # 跳过 ~
        end = self.parse_expression()
        case_value = RangeExpr(start, end)
    else:
        case_value = start

    self.expect(':')
    body = self.parse_statement()
    return CaseStmt(case_value, body)
```

### 5.5 AST Node 定义（Python 框架）

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ==================== 类型系统 ====================

class Type(ABC):
    pass

@dataclass
class BitVectorType(Type):
    width: int

@dataclass
class BoolType(Type):
    pass

@dataclass
class StructType(Type):
    name: str
    fields: list  # list of (name, Type)

@dataclass
class ArrayType(Type):
    base_type: Type
    size: Optional[int] = None  # None = 不定长


# ==================== 表达式 ====================

class Expr(ABC):
    """表达式基类"""
    @property
    @abstractmethod
    def type(self) -> Optional[Type]:
        """表达式的类型（语义分析后填充）"""
        pass

@dataclass
class IdentifierExpr(Expr):
    name: str

@dataclass
class IntLiteral(Expr):
    value: int

@dataclass
class BinLiteral(Expr):
    value: str  # 二进制字符串，如 "00_100?_????_????_??"
    width: int

@dataclass
class HexLiteral(Expr):
    value: int
    width: Optional[int] = None

@dataclass
class BinaryOpExpr(Expr):
    op: str  # '+', '-', '&', '|', '==', '<', etc.
    left: Expr
    right: Expr

@dataclass
class UnaryOpExpr(Expr):
    op: str  # '!', '~', '-'
    operand: Expr

@dataclass
class FieldAccessExpr(Expr):
    """obj.field 字段访问"""
    obj: Expr
    field: str

@dataclass
class BitSliceExpr(Expr):
    """expr[hi:lo] 位域切片"""
    obj: Expr
    hi: Expr
    lo: Expr

@dataclass
class BitIndexExpr(Expr):
    """expr[index] 位索引"""
    obj: Expr
    index: Expr

@dataclass
class FieldIndexExpr(Expr):
    """field{idx} 字段内子索引（花括号下标）"""
    obj: Expr
    index: Expr

@dataclass
class CompositeFieldExpr(Expr):
    """obj.{ field1, field2 } 复合字段访问"""
    obj: Expr
    fields: list  # list of (name: str, bit_slice: (hi, lo)?)

@dataclass
class ConcatExpr(Expr):
    """{ a, b, c } 位拼接"""
    parts: list  # list of Expr

@dataclass
class FunctionCallExpr(Expr):
    name: str
    args: list  # list of Expr

@dataclass
class MaxMinExpr(Expr):
    """Max(a, b, c) 求最大值"""
    func: str  # 'Max' or 'Min'
    args: list  # list of Expr

@dataclass
class RangeExpr(Expr):
    """0x11~0x1f 范围表达式（case中使用）"""
    start: Expr
    end: Expr

@dataclass
class EllipsisExpr(Expr):
    """... 省略占位符"""
    pass


# ==================== 语句 ====================

class Stmt(ABC):
    pass

@dataclass
class CompoundStmt(Stmt):
    stmts: list  # list of Stmt

@dataclass
class WhileStmt(Stmt):
    cond: Expr
    body: Stmt

@dataclass
class ForStmt(Stmt):
    init: Optional[Expr]
    cond: Optional[Expr]
    update: Optional[Expr]
    body: Stmt

@dataclass
class IfStmt(Stmt):
    cond: Expr
    then_body: Stmt
    else_body: Optional[Stmt] = None

@dataclass
class SwitchStmt(Stmt):
    expr: Expr
    cases: list  # list of CaseStmt

@dataclass
class CaseStmt(Stmt):
    value: Expr  # 可为 RangeExpr
    body: Stmt

@dataclass
class AssignStmt(Stmt):
    lhs: Expr
    rhs: Expr

@dataclass
class CompoundAssignStmt(Stmt):
    """+=, -=, &=, |= 等复合赋值"""
    lhs: Expr
    op: str
    rhs: Expr

@dataclass
class IncDecStmt(Stmt):
    """++ / -- 语句"""
    expr: Expr
    is_increment: bool
    is_prefix: bool = True  # true: ++i, false: i++

@dataclass
class TableReadStmt(Stmt):
    """target = table_name Table[index]"""
    target: Expr
    table_name: str
    index: Expr

@dataclass
class TableWriteStmt(Stmt):
    """update table_name using value at address"""
    table_name: str
    value: Expr
    address: Expr

@dataclass
class ExprStmt(Stmt):
    expr: Expr

@dataclass
class VarDeclStmt(Stmt):
    """giStormIdx[4:0] = 0;"""
    name: str
    bit_width: Optional[tuple] = None  # (hi, lo)
    initializer: Optional[Expr] = None

@dataclass
class DelayStmt(Stmt):
    expr: Expr

@dataclass
class EnqueueStmt(Stmt):
    """Enqueue PacketByte with updated header waiting for outgoing;"""
    target: str
    attributes: dict = field(default_factory=dict)

@dataclass
class ReplaceStmt(Stmt):
    """Replace Byte[a] to Byte[b] using value;"""
    target: Expr
    start_byte: Expr
    end_byte: Expr
    source: Expr

@dataclass
class InsertStmt(Stmt):
    """Insert value after Byte[n];"""
    value: Expr
    position: Expr  # after which byte

@dataclass
class RemoveStmt(Stmt):
    """remove Byte[a] ... Byte[b];"""
    start_byte: Expr
    end_byte: Expr

@dataclass
class SendStmt(Stmt):
    """send packet { ... };"""
    name: Optional[str]
    fields: list  # list of Expr, each element in the braces


# ==================== 声明/定义 ====================

@dataclass
class FieldDecl:
    """位域声明"""
    name: str
    offset: int
    hi_bit: int
    lo_bit: int
    read_trigger: bool = False
    write_trigger: bool = False
    read_only: bool = False
    read_indicate: bool = False
    write_indicate: bool = False
    write_one_indicate: bool = False
    default_value: Optional[Expr] = None
    description: str = ""

@dataclass
class MemTableDecl:
    """内存表声明（来自 tinyReg.txt）"""
    name: str
    full_name: str
    num_entries: int
    words: int
    addr_bits: int
    decode_pattern: str
    description: str
    fields: list  # list of FieldDecl

@dataclass
class RegisterDecl:
    """寄存器声明（来自 tinyReg.txt）"""
    name: str
    full_name: str
    words: int
    decode_pattern: str
    description: str
    fields: list  # list of FieldDecl

@dataclass
class RegMapDef:
    """tinyReg.txt 整体定义"""
    file_name: str
    prefix: str
    addr_upper: int
    addr_lower: int
    mem_tables: list  # list of MemTableDecl
    registers: list  # list of RegisterDecl

@dataclass
class GlobalVarDecl:
    """全局变量声明"""
    type: Optional[Type]
    name: str
    bit_width: Optional[tuple] = None  # (hi, lo)
    bit_width_expr: Optional[Expr] = None  # [hi:lo] 表达式形式
    initializer: Optional[Expr] = None

@dataclass
class StructDef:
    """结构体定义"""
    name: str
    fields: list  # list of (name: str, type: Type)

@dataclass
class ParamDecl:
    """函数参数"""
    type: Optional[Type]
    name: str

@dataclass
class ProcessDef:
    """过程定义"""
    name: str
    body: Stmt  # CompoundStmt

@dataclass
class FunctionDef:
    """函数定义"""
    return_type: Optional[Type]
    name: str
    params: list  # list of ParamDecl
    body: Stmt  # CompoundStmt

@dataclass
class PseudoCModel:
    """8mSpec_0821.c 模型"""
    global_vars: list  # list of GlobalVarDecl
    structs: list  # list of StructDef
    processes: list  # list of ProcessDef
    functions: list  # list of FunctionDef

@dataclass
class TranslationUnit(Stmt):
    """顶层节点"""
    reg_map: Optional[RegMapDef] = None
    pseudo_c_model: Optional[PseudoCModel] = None
```

---

## 6. 语义分析器设计

### 6.1 符号表结构

```python
@dataclass
class Symbol:
    name: str
    kind: SymbolKind  # TABLE, REGISTER, FIELD, VARIABLE, PROCESS, FUNCTION, STRUCT
    type: Optional[Type]
    decl: Any  # 对应的 AST 声明节点

class SymbolTable:
    """符号表"""
    def __init__(self, parent=None):
        self.symbols: dict[str, Symbol] = {}
        self.parent: Optional[SymbolTable] = parent

    def define(self, symbol: Symbol):
        """定义符号"""
        self.symbols[symbol.name] = symbol

    def lookup(self, name: str) -> Optional[Symbol]:
        """查找符号（包括父作用域）"""
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def lookup_local(self, name: str) -> Optional[Symbol]:
        """仅查找当前作用域"""
        return self.symbols.get(name)
```

### 6.2 符号表构建

语义分析的第一个阶段是构建符号表，需要按以下顺序处理：

```
Phase 1: 从 RegMapDef 构建全局符号
  ├── MemTable 符号: {'DsMac', 'DsVlan', 'DsPort', ...}
  ├── Register 符号: {'L2AgingCtl', 'LoopDetectCtl', ...}
  └── 每个符号下注册字段（FieldDecl）作为子符号

Phase 2: 从 PseudoCModel 构建附加符号
  ├── 全局变量: {'PacketByte', 'piSrcPort', 'piPktLength', ...}
  ├── 结构体: {'ParserResult'}
  ├── 过程: {'forward', 'updateStormCtrl', 'normalAging', ...}
  └── 函数: {'parser', 'switchX', 'egress'}
```

### 6.3 类型检查器

```python
class TypeChecker:
    """类型检查器"""

    def __init__(self, symbol_table: SymbolTable):
        self.symbol_table = symbol_table

    def check(self, node):
        """类型检查入口"""
        if isinstance(node, TranslationUnit):
            self.check_translation_unit(node)
        elif isinstance(node, ProcessDef):
            self.check_process(node)
        elif isinstance(node, FunctionDef):
            self.check_function(node)
        elif isinstance(node, AssignStmt):
            self.check_assignment(node)
        # ... 递归处理

    def check_assignment(self, stmt: AssignStmt):
        """检查赋值语句的位宽兼容性"""
        lhs_type = self.infer_type(stmt.lhs)
        rhs_type = self.infer_type(stmt.rhs)

        if lhs_type and rhs_type:
            lhs_width = self.get_bit_width(lhs_type)
            rhs_width = self.get_bit_width(rhs_type)

            if lhs_width < rhs_width:
                # 左值位宽小于右值 → 截断警告
                warning(f"Possible truncation: {lhs_width}bit <- {rhs_width}bit")
            # lhs_width >= rhs_width 正常（硬件中自动高位补0）

    def infer_type(self, expr: Expr) -> Optional[Type]:
        """推导表达式的类型"""
        if isinstance(expr, IntLiteral):
            return BitVectorType(self.required_bits(expr.value))
        elif isinstance(expr, IdentifierExpr):
            symbol = self.symbol_table.lookup(expr.name)
            return symbol.type if symbol else None
        elif isinstance(expr, FieldAccessExpr):
            # DsMac.prior → 查找 DsMac 的 prior 字段类型
            base_type = self.infer_type(expr.obj)
            if base_type and isinstance(base_type, StructType):
                # 查找字段位宽
                for field_name, field_type in base_type.fields:
                    if field_name == expr.field:
                        return field_type
        elif isinstance(expr, BitSliceExpr):
            # expr[3:0] → 宽度为 (hi - lo + 1)
            base_type = self.infer_type(expr.obj)
            if base_type:
                # 计算切片宽度 (需要 hi, lo 为常量)
                return BitVectorType(4)  # 示例简化
        elif isinstance(expr, ConcatExpr):
            # {a, b, c} → 宽度为各部分宽度之和
            total_width = 0
            for part in expr.parts:
                part_type = self.infer_type(part)
                if part_type:
                    total_width += self.get_bit_width(part_type)
            return BitVectorType(total_width)
        # ...
```

### 6.4 位宽计算工具

```python
def get_bit_width(type_or_expr) -> Optional[int]:
    """获取表达式或类型的位宽"""
    if isinstance(type_or_expr, BitVectorType):
        return type_or_expr.width
    elif isinstance(type_or_expr, BoolType):
        return 1
    elif isinstance(type_or_expr, IdentifierExpr):
        # 查找符号的位宽
        symbol = symbol_table.lookup(type_or_expr.name)
        return get_bit_width(symbol.type) if symbol else None
    elif isinstance(type_or_expr, BitSliceExpr):
        # 需要常量折叠计算 hi - lo + 1
        hi = constant_fold(type_or_expr.hi)
        lo = constant_fold(type_or_expr.lo)
        if hi is not None and lo is not None:
            return hi - lo + 1
    elif isinstance(type_or_expr, ConcatExpr):
        total = 0
        for part in type_or_expr.parts:
            w = get_bit_width(part)
            if w is None:
                return None
            total += w
        return total
    # ...
    return None
```

### 6.5 触发依赖性分析

用于识别 ReadTrigger/WriteTrigger 标记的字段，生成寄存器访问代码：

```python
class TriggerAnalyzer:
    """分析寄存器字段的触发行为"""

    def __init__(self, reg_map: RegMapDef):
        self.reg_map = reg_map

        # 建立触发映射
        self.read_triggers: dict[str, list[FieldDecl]] = {}
        self.write_triggers: dict[str, list[FieldDecl]] = {}

        for table in reg_map.mem_tables:
            for field in table.fields:
                if field.read_trigger:
                    self.read_triggers.setdefault(table.name, []).append(field)
                if field.write_trigger:
                    self.write_triggers.setdefault(table.name, []).append(field)

        for reg in reg_map.registers:
            for field in reg.fields:
                if field.read_indicate:
                    # 读指示 → 读时硬件自动更新
                    pass
                if field.write_indicate:
                    # 写指示 → 写时触发硬件动作
                    pass

    def is_read_triggered(self, table_name: str, field_name: str) -> bool:
        """指定字段是否有读触发"""
        if table_name in self.read_triggers:
            return any(f.name == field_name for f in self.read_triggers[table_name])
        return False

    def is_write_triggered(self, table_name: str, field_name: str) -> bool:
        """指定字段是否有写触发"""
        if table_name in self.write_triggers:
            return any(f.name == field_name for f in self.write_triggers[table_name])
        return False
```

### 6.6 Process 依赖图构建

用于分析多个 process 之间的并发和数据依赖关系：

```python
class ProcessDependencyGraph:
    """过程依赖图"""

    def __init__(self):
        self.nodes: dict[str, ProcessNode] = {}
        self.edges: list[tuple[str, str, str]] = []  # (from, to, dependency_type)

    def add_process(self, name: str, reads: set, writes: set):
        """添加过程节点"""
        self.nodes[name] = ProcessNode(name, reads, writes)

    def analyze_dependencies(self):
        """分析所有过程之间的依赖"""
        names = list(self.nodes.keys())
        for i, name_a in enumerate(names):
            for name_b in names[i+1:]:
                node_a = self.nodes[name_a]
                node_b = self.nodes[name_b]

                # 读写依赖
                common_read_write = node_a.writes & node_b.reads
                if common_read_write:
                    self.edges.append((name_a, name_b, "write_to_read"))

                common_write_write = node_a.writes & node_b.writes
                if common_write_write:
                    self.edges.append((name_a, name_b, "write_to_write"))

    def gen_rtl_hint(self) -> str:
        """生成 RTL 设计提示"""
        hints = []
        for name, node in self.nodes.items():
            hint = f"  {name}: reads={node.reads}, writes={node.writes}"
            hints.append(hint)
        return "\n".join(hints)


@dataclass
class ProcessNode:
    name: str
    reads: set  # 读取的符号集合
    writes: set  # 写入的符号集合
```

### 6.7 语义分析完整流程

```python
class SemanticAnalyzer:
    """语义分析器"""

    def __init__(self):
        self.global_table = SymbolTable()
        self.type_checker = None
        self.trigger_analyzer = None
        self.dep_graph = ProcessDependencyGraph()

    def analyze(self, ast: TranslationUnit):
        """执行完整的语义分析"""

        # 第1步：构建符号表
        self._build_symbol_table(ast)

        # 第2步：类型检查
        self.type_checker = TypeChecker(self.global_table)
        self.type_checker.check(ast)

        # 第3步：触发分析
        if ast.reg_map:
            self.trigger_analyzer = TriggerAnalyzer(ast.reg_map)

        # 第4步：数据流分析
        if ast.pseudo_c_model:
            self._dataflow_analysis(ast.pseudo_c_model)

        # 第5步：常量折叠与优化
        self._constant_folding(ast)

        return ast

    def _build_symbol_table(self, ast: TranslationUnit):
        """构建符号表"""
        # 先从 RegMap 构建
        if ast.reg_map:
            for table in ast.reg_map.mem_tables:
                fields = []
                for field in table.fields:
                    field_type = BitVectorType(field.hi_bit - field.lo_bit + 1)
                    fields.append((field.name, field_type))
                table_type = StructType(table.name, fields)
                self.global_table.define(Symbol(
                    table.name, SymbolKind.TABLE, table_type, table
                ))

            for reg in ast.reg_map.registers:
                fields = []
                for field in reg.fields:
                    field_type = BitVectorType(field.hi_bit - field.lo_bit + 1)
                    fields.append((field.name, field_type))
                reg_type = StructType(reg.name, fields)
                self.global_table.define(Symbol(
                    reg.name, SymbolKind.REGISTER, reg_type, reg
                ))

        # 再从 PseudoC 构建
        if ast.pseudo_c_model:
            for var in ast.pseudo_c_model.global_vars:
                self.global_table.define(Symbol(
                    var.name, SymbolKind.VARIABLE, var.type, var
                ))
            # ... 结构体、过程、函数
```

---

## 7. C 代码生成器

### 7.1 目标

Generate C code that can be compiled by standard C compilers (GCC/Clang/MSVC) for:

1. **行为仿真模型（Behavior Model）** — 在 PC 上模拟芯片行为，用于验证
2. **寄存器驱动（Register Driver）** — 提供对寄存器和内存表的读写 API
3. **测试平台（Testbench）** — 生成输入激励并验证输出

### 7.2 基本映射规则

#### 7.2.1 类型映射

| 伪 C 类型 | C 类型 | 说明 |
|-----------|--------|------|
| `bool` | `uint8_t` | 使用 8 位表示 1 位布尔 |
| `uint3` | `uint8_t` | 使用最接近的标准类型 |
| `uint4` | `uint8_t` | |
| `uint8` | `uint8_t` | 精确匹配 |
| `uint12` | `uint16_t` | |
| `uint16` | `uint16_t` | |
| `uint32` | `uint32_t` | |
| `uint48` | `uint64_t` | |
| `uintN` | 最小能容纳 N 位的标准类型 | 通过宏选择 |

#### 7.2.2 位域操作映射

```c
// 伪C: x[hi:lo]
// C代码:
#define BITFIELD_GET(x, hi, lo) (((x) >> (lo)) & ((1ULL << ((hi)-(lo)+1)) - 1))
#define BITFIELD_SET(x, hi, lo, val) \
    ((x) = ((x) & ~(((1ULL << ((hi)-(lo)+1)) - 1) << (lo))) | \
           (((val) & ((1ULL << ((hi)-(lo)+1)) - 1)) << (lo)))

// 使用示例:
// uint3 prior = DsMac.prior[1:0];  ← 伪C
uint8_t prior = BITFIELD_GET(ds_mac, 13, 12);  // ← 生成C

// DsMac.prior[1:0] = piVlanPrior[1:0];  ← 伪C
BITFIELD_SET(ds_mac, 13, 12, pi_vlan_prior);  // ← 生成C
```

#### 7.2.3 拼接操作映射

```c
// 伪C: { a, b, c }
// C代码:
#define CONCAT_3(a, a_w, b, b_w, c, c_w) \
    (((uint64_t)(a) << ((b_w)+(c_w))) | \
     ((uint64_t)(b) << (c_w)) | \
     ((uint64_t)(c)))

// {PacketByte12, PacketByte13} → uint16
uint16_t gi_tpid = ((uint16_t)PacketByte[12] << 8) | PacketByte[13];
```

#### 7.2.4 Table 访问映射

```c
// 伪C: DsMac = DsMac Table[giHashIdx];
// ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓ LUT 实现（仿真用）

// 读取: 从内存数组中读取
#include <stdint.h>

// 内存表类型定义
typedef struct {
    uint16_t destMap;      // bit[9:0]
    uint8_t  destDiscard;  // bit[10]
    uint8_t  isMcast;      // bit[11]
    uint8_t  prior;        // bit[13:12]
} DsMac_entry_t;

#define DS_MAC_DEPTH 2048
DsMac_entry_t DsMac_mem[DS_MAC_DEPTH];

// 读操作函数
DsMac_entry_t DsMac_table_read(uint16_t index) {
    if (index < DS_MAC_DEPTH) {
        return DsMac_mem[index];
    }
    // 越界处理
    DsMac_entry_t zero = {0};
    return zero;
}

// 写操作函数
void DsMac_table_write(uint16_t index, DsMac_entry_t value) {
    if (index < DS_MAC_DEPTH) {
        DsMac_mem[index] = value;
    }
}
```

#### 7.2.5 过程映射

```c
// 伪C:
// process updateStormCtrl() {
//     giStormIdx[4:0] = 0;
//     while(1) {
//         if( StormCfgCtl.enable ) {
//             DsStormCtrl = DsStormCtrl Table[ giStormIdx ];
//             ...
//         }
//         giStormIdx++;
//         Delay( StormCfgCtl.delayInterval[31:0] );
//     }
// }

// ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓

// C代码:
void updateStormCtrl_tick(void) {
    static uint8_t giStormIdx = 0;  // [4:0]
    static uint32_t delayCounter = 0;

    if (delayCounter > 0) {
        delayCounter--;
        return;  // 还在延迟中
    }

    if (StormCfgCtl.enable) {
        DsStormCtrl_entry_t DsStormCtrl = DsStormCtrl_table_read(giStormIdx);
        if (DsStormCtrl.enable) {
            DsStormCtrl.counter += DsStormCtrl.step;
            if (DsStormCtrl.counter > DsStormCtrl.cntThrd) {
                DsStormCtrl.counter = DsStormCtrl.cntThrd;
            }
            DsStormCtrl_table_write(giStormIdx, DsStormCtrl);
        }
    }

    giStormIdx++;
    delayCounter = StormCfgCtl.delayInterval;  // 设置延迟计数器
}
```

### 7.3 寄存器驱动代码生成

```c
// ==================== 8m_reg_drv.h ====================

#ifndef __8M_REG_DRV_H__
#define __8M_REG_DRV_H__

#include <stdint.h>

// ==================== 地址定义 ====================
// 内存表地址
#define DS_MAC_BASE     0x0080
#define DS_MAC_DEPTH    2048
#define DS_MAC_WORD_SIZE 2  // 1 word = 2 bytes

#define DS_VLAN_BASE    0x0240
#define DS_VLAN_DEPTH   16
#define DS_VLAN_WORD_SIZE 4  // 2 words = 4 bytes

// ... 其他表

// 寄存器地址
#define L2_AGING_CTL_ADDR   0x2800
#define L2_LEARN_CTL_ADDR   0x2810
#define LOOP_DETECT_CTL_ADDR 0x2820

// ==================== 内存表结构体 ====================
typedef struct {
    uint16_t destMap;        // bit[9:0],  offset=0
    uint8_t  destDiscard;    // bit[10],   offset=0
    uint8_t  isMcast;        // bit[11],   offset=0
    uint8_t  prior;          // bit[13:12],offset=0
} DsMac_entry_t;

// ==================== 寄存器结构体 ====================
typedef struct {
    uint8_t  fastAgingEn;    // bit[0],    offset=0
    uint8_t  agingEn;        // bit[1],    offset=0
    uint8_t  fastAgingAll;   // bit[2],    offset=0
    uint8_t  fastAgingByPort;// bit[3],    offset=0
    uint8_t  portId;         // bit[7:4],  offset=0
    uint32_t cycleThrd;      // bit[31:0], offset=1
} L2AgingCtl_t;

// ==================== 寄存器读写 API ====================
// 底层访问
uint32_t reg_read(uint16_t addr);
void reg_write(uint16_t addr, uint32_t val);

// L2AgingCtl 专用访问
L2AgingCtl_t L2AgingCtl_read(void);
void L2AgingCtl_write(L2AgingCtl_t val);

// 域级访问
uint8_t L2AgingCtl_get_agingEn(void);
void L2AgingCtl_set_agingEn(uint8_t val);

// DsMac 内存表访问
DsMac_entry_t DsMac_read(uint16_t index);
void DsMac_write(uint16_t index, DsMac_entry_t val);

#endif // __8M_REG_DRV_H__


// ==================== 8m_reg_drv.c ====================

#include "8m_reg_drv.h"

// 寄存器原始数据打包/解包
L2AgingCtl_t L2AgingCtl_read(void) {
    uint32_t raw[2];
    raw[0] = reg_read(L2_AGING_CTL_ADDR + 0);
    raw[1] = reg_read(L2_AGING_CTL_ADDR + 4);

    L2AgingCtl_t val;
    val.fastAgingEn     = (raw[0] >> 0) & 0x1;
    val.agingEn         = (raw[0] >> 1) & 0x1;
    val.fastAgingAll    = (raw[0] >> 2) & 0x1;
    val.fastAgingByPort = (raw[0] >> 3) & 0x1;
    val.portId          = (raw[0] >> 4) & 0xF;
    val.cycleThrd       = raw[1];
    return val;
}

void L2AgingCtl_write(L2AgingCtl_t val) {
    uint32_t raw0 = 0;
    raw0 |= (val.fastAgingEn     & 0x1) << 0;
    raw0 |= (val.agingEn         & 0x1) << 1;
    raw0 |= (val.fastAgingAll    & 0x1) << 2;
    raw0 |= (val.fastAgingByPort & 0x1) << 3;
    raw0 |= (val.portId          & 0xF) << 4;

    reg_write(L2_AGING_CTL_ADDR + 0, raw0);
    reg_write(L2_AGING_CTL_ADDR + 4, val.cycleThrd);
}

uint8_t L2AgingCtl_get_agingEn(void) {
    uint32_t raw = reg_read(L2_AGING_CTL_ADDR);
    return (raw >> 1) & 0x1;
}
```

---

## 8. RTL/Verilog 生成器

### 8.1 设计目标

生成可综合的 Verilog/SystemVerilog 代码，用于 FPGA 或 ASIC 实现。

### 8.2 输出文件组

| 文件 | 内容 | 说明 |
|------|------|------|
| `8m_switch_top.v` | 顶层模块 | 例化所有子模块 |
| `8m_parser.v` | 包解析器 | Ethernet/IP 包头解析 |
| `8m_forward.v` | 转发引擎 | L2 交换、MAC 学习、查表 |
| `8m_aging.v` | 老化模块 | 正常/快速老化 |
| `8m_storm_ctrl.v` | 风暴控制 | 广播/组播/未知单播风暴控制 |
| `8m_priority.v` | 优先级分配 | DSCP/VLAN/Port 优先级加权 |
| `8m_egress.v` | 出口处理 | VLAN 标签修改、MAC 替换 |
| `8m_reg_decode.v` | 寄存器解码 | 地址译码、寄存器读写 |
| `8m_ram_wrap_*.v` | RAM Wrapper | 每个内存表的包装器 |

### 8.3 类型映射

| 伪 C 类型 | Verilog 类型 |
|-----------|-------------|
| `uint3` | `wire [2:0]` / `reg [2:0]` |
| `uint8` | `wire [7:0]` / `reg [7:0]` |
| `uint12` | `wire [11:0]` / `reg [11:0]` |
| `uint48` | `wire [47:0]` / `reg [47:0]` |
| `bool` | `wire` / `reg` |
| `uint8 PacketByte[]` | `wire [7:0] PacketByte [0:PKT_LEN-1]` |

### 8.4 核心转换规则

#### 8.4.1 process → always 块

```
// === 伪C ===
process updateStormCtrl() {
    giStormIdx[4:0] = 0;
    while(1) {
        if( StormCfgCtl.enable ) {
            DsStormCtrl = DsStormCtrl Table[ giStormIdx ];
            if( DsStormCtrl.enable ) {
                DsStormCtrl.counter += DsStormCtrl.step[31:0];
                if( DsStormCtrl.counter[31:0] > DsStormCtrl.cntThrd[31:0] ) {
                    DsStormCtrl.counter = DsStormCtrl.cntThrd;
                }
            }
        }
        giStormIdx++;
        Delay( StormCfgCtl.delayInterval[31:0] );
    }
}

// === 生成 Verilog ===
module updateStormCtrl (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        StormCfgCtl_enable,
    input  wire [4:0]  giStormIdx,
    // ...其他端口
);

// FSM 状态定义
localparam IDLE    = 3'd0;
localparam READ   = 3'd1;
localparam UPDATE = 3'd2;
localparam DELAY  = 3'd3;

reg [2:0] state, next_state;
reg [4:0] storm_idx;
reg [31:0] delay_cnt;

// 状态寄存器
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        state <= IDLE;
        storm_idx <= 0;
        delay_cnt <= 0;
    end else begin
        state <= next_state;
        if (state == READ) storm_idx <= storm_idx + 1;
        if (state == UPDATE) delay_cnt <= StormCfgCtl_delayInterval;
        if (state == DELAY && delay_cnt > 0) delay_cnt <= delay_cnt - 1;
    end
end

// 次态逻辑
always @(*) begin
    next_state = state;
    case (state)
        IDLE: begin
            if (StormCfgCtl_enable)
                next_state = READ;
            else
                next_state = DELAY;  // 跳过，直接延迟
        end
        READ: begin
            if (DsStormCtrl_enable)
                next_state = UPDATE;
            else
                next_state = DELAY;  // 无需更新，但索引已++
        end
        UPDATE: next_state = DELAY;
        DELAY: begin
            if (delay_cnt == 0)
                next_state = IDLE;
        end
    endcase
end

// RAM 读操作
wire [31:0] DsStormCtrl_read_data;
DsStormCtrl_ram u_DsStormCtrl_ram (
    .clk(clk),
    .addr(storm_idx),
    .dout(DsStormCtrl_read_data)
);

// 数据通路
wire DsStormCtrl_enable;
wire DsStormCtrl_usePkt;
wire [31:0] DsStormCtrl_cntThrd;
wire [31:0] DsStormCtrl_step;

assign DsStormCtrl_enable  = DsStormCtrl_read_data[0];
assign DsStormCtrl_usePkt  = DsStormCtrl_read_data[1];
assign DsStormCtrl_cntThrd = DsStormCtrl_read_data[63:32];  // word1
assign DsStormCtrl_step    = DsStormCtrl_read_data[127:96];  // word3

// 计数器更新
reg [31:0] counter;
always @(posedge clk) begin
    if (state == UPDATE) begin
        if (counter < DsStormCtrl_cntThrd - DsStormCtrl_step)
            counter <= counter + DsStormCtrl_step;
        else
            counter <= DsStormCtrl_cntThrd;
    end
end

// RAM 写操作
reg DsStormCtrl_wr_en;
reg [4:0] DsStormCtrl_wr_addr;
reg [31:0] DsStormCtrl_wr_data;

always @(posedge clk) begin
    if (state == UPDATE) begin
        DsStormCtrl_wr_en <= 1;
        DsStormCtrl_wr_addr <= storm_idx - 1;
        DsStormCtrl_wr_data <= counter;
    end else begin
        DsStormCtrl_wr_en <= 0;
    end
end

endmodule
```

#### 8.4.2 while(1) → 流水线模式

对于 `forward` 过程中的 `while(1) { parser(); switchX(); egress(); }`：

```
推理为3级流水线：
  流水线级1: parser() — 解析包头部
  流水线级2: switchX() — L2交换/L2学习
  流水线级3: egress() — 出口处理

```

```verilog
module forward_pipeline (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  PacketByte [0:63],  // 前64B
    // ...
);

// ========== 流水线寄存器 ==========
// Stage 1: Parser
reg [47:0]  pipe1_macDa;
reg [47:0]  pipe1_macSa;
reg [2:0]   pipe1_vlanPrior;
reg [11:0]  pipe1_vlanId;
reg         pipe1_isLoopDetection;
// ...

// Stage 2: Switch
reg [11:0]  pipe2_vid;
reg [9:0]   pipe2_fwdBmp;
reg [11:0]  pipe2_fid;
reg [1:0]   pipe2_prior;
// ...

// Stage 3: Egress
reg [7:0]   pipe3_outPacket [0:63];
reg [2:0]   pipe3_destPort;
// ...

// ========== 流水线控制 ==========
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        // 清零所有流水线寄存器
        pipe1_macDa <= 0;
        // ...
    end else begin
        // Stage 1
        {pipe1_macDa, pipe1_macSa, ...} <= parser(PacketByte);

        // Stage 2
        {pipe2_vid, pipe2_fwdBmp, ...} <= switchX(pipe1_macDa, pipe1_macSa, ...);

        // Stage 3
        pipe3_outPacket <= egress(pipe2_vid, pipe2_fwdBmp, ...);
    end
end

endmodule
```

#### 8.4.3 Table → RAM Wrapper

```verilog
// ==================== 8m_ram_wrap_DsMac.v ====================
// 自动从 tinyReg.txt 生成
// DsMac: 2048 entries x 1 word (14bits used, stored as 16bits)

module DsMac_ram_wrap (
    input  wire        clk,
    input  wire        rst_n,

    // 读端口
    input  wire [10:0] rd_addr,   // 11-bit address (2048 depth)
    output wire [15:0] rd_data,

    // 写端口
    input  wire        wr_en,
    input  wire [10:0] wr_addr,
    input  wire [15:0] wr_data
);

    // 位域分解为端口（根据 MemRegFields）
    // destMap:     rd_data[9:0]     (offset=0, hi=9, lo=0)
    // destDiscard: rd_data[10]      (offset=0, hi=10, lo=10)
    // isMcast:     rd_data[11]      (offset=0, hi=11, lo=11)
    // prior:       rd_data[13:12]   (offset=0, hi=13, lo=12)

    // 可综合单口RAM
    reg [15:0] mem [0:2047];

    always @(posedge clk) begin
        if (wr_en)
            mem[wr_addr] <= wr_data;
        rd_data <= mem[rd_addr];
    end

endmodule


// ==================== 8m_ram_wrap_L2AgingCtl.v ====================
// L2AgingCtl: 2 words register, not a memory table
// 但 RegMap 中定义为 Register，生成寄存器逻辑而非 RAM

module L2AgingCtl_reg (
    input  wire        clk,
    input  wire        rst_n,

    // 寄存器总线接口
    input  wire        reg_wr_en,
    input  wire [0:0]  reg_wr_sel,  // word select (2 words)
    input  wire [31:0] reg_wr_data,
    output wire [31:0] reg_rd_data,

    // 域级访问接口 (直接给内部逻辑使用)
    output wire        field_fastAgingEn,
    output wire        field_agingEn,
    output wire        field_fastAgingAll,
    output wire        field_fastAgingByPort,
    output wire [3:0]  field_portId,
    output wire [31:0] field_cycleThrd,

    // 域级写接口（内部逻辑修改寄存器）
    input  wire        field_fastAgingEn_wr,
    input  wire        field_fastAgingEn_set  // 写值
);

    reg [31:0] word0, word1;
    wire [31:0] reg_rd_data;

    // 位域分解
    assign field_fastAgingEn     = word0[0];
    assign field_agingEn         = word0[1];
    assign field_fastAgingAll    = word0[2];
    assign field_fastAgingByPort = word0[3];
    assign field_portId          = word0[7:4];
    assign field_cycleThrd       = word1;

    // 读多路选择
    assign reg_rd_data = (reg_wr_sel == 0) ? word0 : word1;

    // 寄存器写（外部总线）
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            word0 <= 32'h0000_0006;  // agingEn=1, fastAgingAll=1
            word1 <= 32'h0000_0000;
        end else begin
            if (reg_wr_en) begin
                if (reg_wr_sel == 0) word0 <= reg_wr_data;
                else word1 <= reg_wr_data;
            end

            // 内部逻辑写某些域（如 L2LearnCtl.sysLearnNum--）
            if (field_fastAgingEn_wr)
                word0[0] <= field_fastAgingEn_set;
        end
    end

endmodule
```

#### 8.4.4 位域操作转换

```verilog
// 伪C: prMacDa[47:0] = {PacketByte0, ..., PacketByte5};

// 生成Verilog:
wire [47:0] prMacDa;
assign prMacDa = {PacketByte[0], PacketByte[1], PacketByte[2],
                  PacketByte[3], PacketByte[4], PacketByte[5]};

// 伪C: prVlanPrior[2:0] = PacketByte[ giPldOffset ][7:5];

// 生成Verilog:
wire [2:0] prVlanPrior;
assign prVlanPrior = PacketByte[giPldOffset][7:5];

// 伪C: DsMacValid.valid[ giAgingPtr[1:0] ] = 0;

// 生成Verilog:
// valid[3:0] 4位
wire [1:0] giAgingPtr_low = giAgingPtr[1:0];
always @(*) begin
    case (giAgingPtr_low)
        2'd0: DsMacValid_valid[0] = 0;
        2'd1: DsMacValid_valid[1] = 0;
        2'd2: DsMacValid_valid[2] = 0;
        2'd3: DsMacValid_valid[3] = 0;
    endcase
end

// 或简化为（如果工具支持部分写）:
always @(posedge clk) begin
    if (clear_en)
        DsMacValid_valid <= DsMacValid_valid & ~(1 << giAgingPtr_low);
end
```

#### 8.4.5 更新/写入操作转换

```verilog
// 伪C: update DsMacKey using newDsMacKeyEntry at { giLrnHash }.{ giLrnSubIdx };

// 生成Verilog:
wire [10:0] wr_addr = {giLrnHash, giLrnSubIdx[1:0]};  // 复合地址
wire [63:0] wr_data = {prMacSa, giFid};  // newDsMacKeyEntry

always @(posedge clk) begin
    if (lrn_update_en)
        DsMacKey_mem[wr_addr] <= wr_data;
end
```

#### 8.4.6 包修改操作转换

```verilog
// 伪C:
// Replace PacketBypte[6] to PacketBypte[11] using LoopDetectCtl.loopMac[47:0];

// 生成Verilog:
always @(posedge clk) begin
    if (replace_en) begin
        out_packet[6]  <= loopMac[47:40];
        out_packet[7]  <= loopMac[39:32];
        out_packet[8]  <= loopMac[31:24];
        out_packet[9]  <= loopMac[23:16];
        out_packet[10] <= loopMac[15:8];
        out_packet[11] <= loopMac[7:0];
    end
end


// 伪C:
// Insert newVlanTag after PacketByte[11];

// 生成Verilog:
// 插入操作涉及数据移位
always @(*) begin
    if (insert_en) begin
        // PacketByte[0:11] 保持不变
        // PacketByte[12:15] = newVlanTag
        // PacketByte[16:end] = 原来的 PacketByte[12:end-4]
        out_packet[0:11] = in_packet[0:11];
        out_packet[12:15] = newVlanTag;
        out_packet[16:63] = in_packet[12:59];
    end else begin
        out_packet = in_packet;
    end
end


// 伪C:
// remove PacketByte[12] ... PacketByte[15];

// 生成Verilog:
always @(*) begin
    if (remove_en) begin
        // PacketByte[0:11] 不变
        // PacketByte[12:end-4] = PacketByte[16:end]
        out_packet[0:11] = in_packet[0:11];
        out_packet[12:59] = in_packet[16:63];
    end else begin
        out_packet = in_packet;
    end
end
```

### 8.5 寄存器地址解码

```verilog
// ==================== 8m_reg_decode.v ====================

module reg_decode (
    input  wire [17:2] addr,   // 16位地址的高16位

    // 内存表片选
    output reg         sel_DsMac,
    output reg [10:0]  DsMac_addr,  // 2048深度

    output reg         sel_DsVlan,
    output reg [3:0]   DsVlan_addr,  // 16深度

    // 寄存器片选
    output reg         sel_L2AgingCtl,
    output reg [0:0]   L2AgingCtl_word_sel,  // 2 words = 1 bit
);

always @(*) begin
    // 默认值
    sel_DsMac = 0;
    sel_DsVlan = 0;
    sel_L2AgingCtl = 0;

    // 使用 casez 处理带通配位的地址解码
    // 优先级: 先 decode 更精确的地址

    // DsMac: 16'b00_100?_????_????_??
    // 地址位: {addr[17:12], addr[11:6], addr[5:2]} 匹配模式
    casez ({addr[17:12], addr[11:6], addr[5:2]})
        14'b00_100?_????_????: begin
            sel_DsMac = 1;
            DsMac_addr = addr[12:2];  // 11位地址
        end

        // DsVlan: 16'b10_0100_0000_0???_??
        14'b10_0100_0000_0???: begin
            sel_DsVlan = 1;
            DsVlan_addr = addr[5:2];  // 4位地址
        end

        // L2AgingCtl: 16'b10_1000_0000_0000_0?
        14'b10_1000_0000_0000: begin
            if (addr[2] == 1'b0) begin  // 0? 最后一位
                sel_L2AgingCtl = 1;
                L2AgingCtl_word_sel = addr[3];  // 2 words
            end
        end
    endcase
end

endmodule
```

---

## 9. 编译管道与工具链

### 9.1 编译器入口

```python
# ==================== main.py ====================

import argparse
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description='8M Switch AST Compiler - Generate C/RTL from spec files'
    )
    parser.add_argument('spec_file', type=str, help='PseudoC spec file (.c)')
    parser.add_argument('reg_file', type=str, help='Register map file (.txt)')
    parser.add_argument('--target', choices=['c', 'rtl', 'all'],
                        default='all', help='Code generation target')
    parser.add_argument('--output-dir', '-o', type=str, default='./output',
                        help='Output directory')
    parser.add_argument('--gen-driver', action='store_true',
                        help='Generate register driver code')
    parser.add_argument('--gen-tb', action='store_true',
                        help='Generate testbench')
    parser.add_argument('--gen-ram', action='store_true',
                        help='Generate RAM wrapper RTL')
    parser.add_argument('--optimize', choices=['area', 'speed', 'none'],
                        default='none', help='RTL optimization target')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    # 初始化编译管道
    compiler = CompilerPipeline(args)

    # 执行编译
    result = compiler.run()

    if result.success:
        print(f"Compilation successful. Output: {args.output_dir}")
    else:
        print(f"Compilation failed: {result.error}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
```

### 9.2 编译管道实现

```python
# ==================== pipeline.py ====================

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CompilerResult:
    success: bool
    error: Optional[str] = None
    output_files: list[str] = field(default_factory=list)


class CompilerPipeline:
    """编译管道"""

    def __init__(self, args):
        self.args = args
        self.spec_path = Path(args.spec_file)
        self.reg_path = Path(args.reg_file)
        self.output_dir = Path(args.output_dir)
        self.verbose = args.verbose

        # 编译阶段状态
        self.source_text: dict[str, str] = {}
        self.tokens: dict[str, list] = {}
        self.ast: Optional[TranslationUnit] = None
        self.ir = None

    def run(self) -> CompilerResult:
        """执行完整的编译流程"""

        result = CompilerResult()

        try:
            # 第1阶段：文件读取与预处理
            self._log("Phase 1: Preprocessing...")
            self._preprocess()

            # 第2阶段：词法分析
            self._log("Phase 2: Lexical Analysis...")
            self._lex()

            # 第3阶段：语法分析
            self._log("Phase 3: Syntax Analysis...")
            self._parse()

            # 第4阶段：语义分析
            self._log("Phase 4: Semantic Analysis...")
            self._semantic_analyze()

            # 第5阶段：IR 构建
            self._log("Phase 5: IR Construction...")
            self._build_ir()

            # 第6阶段：代码生成
            target = self.args.target
            if target in ('c', 'all'):
                self._log("Phase 6a: C Code Generation...")
                self._gen_c()

            if target in ('rtl', 'all'):
                self._log("Phase 6b: RTL Code Generation...")
                self._gen_rtl()

            result.success = True
            result.output_files = self._list_output_files()

        except CompilerError as e:
            result.success = False
            result.error = str(e)
        except Exception as e:
            result.success = False
            result.error = f"Unexpected error: {e}"

        return result

    def _log(self, msg: str):
        """输出日志"""
        if self.verbose:
            print(f"  {msg}")

    def _preprocess(self):
        """预处理：读取文件、移除注释、展开宏"""
        spec_text = self.reg_path.read_text(encoding='utf-8')
        reg_text = self.spec_path.read_text(encoding='utf-8')
        self.source_text['spec'] = spec_text
        self.source_text['reg'] = reg_text

    def _lex(self):
        """词法分析"""
        from lexer.regmap_lexer import RegMapLexer
        from lexer.pseudoc_lexer import PseudoCLexer

        reg_lexer = RegMapLexer(self.source_text['reg'])
        spec_lexer = PseudoCLexer(self.source_text['spec'])

        self.tokens['reg'] = reg_lexer.tokenize()
        self.tokens['spec'] = spec_lexer.tokenize()

    def _parse(self):
        """语法分析"""
        from parser.regmap_parser import RegMapParser
        from parser.pseudoc_parser import PseudoCParser

        reg_parser = RegMapParser(self.tokens['reg'])
        spec_parser = PseudoCParser(self.tokens['spec'])

        reg_ast = reg_parser.parse()
        spec_ast = spec_parser.parse()

        self.ast = TranslationUnit(reg_map=reg_ast, pseudo_c_model=spec_ast)

    def _semantic_analyze(self):
        """语义分析"""
        from semantic.semantic_analyzer import SemanticAnalyzer
        analyzer = SemanticAnalyzer()
        analyzer.analyze(self.ast)

    def _build_ir(self):
        """构建统一中间表示"""
        from ir.ir_builder import IRBuilder
        builder = IRBuilder()
        self.ir = builder.build(self.ast)

    def _gen_c(self):
        """生成 C 代码"""
        from codegen.c_codegen import CCodeGenerator
        from codegen.c_reg_driver_gen import RegDriverGenerator

        model_gen = CCodeGenerator(self.ir, self.output_dir)
        model_gen.generate()

        if self.args.gen_driver:
            drv_gen = RegDriverGenerator(self.ir, self.output_dir)
            drv_gen.generate()

        if self.args.gen_tb:
            from codegen.c_tb_gen import TestbenchGenerator
            tb_gen = TestbenchGenerator(self.ir, self.output_dir)
            tb_gen.generate()

    def _gen_rtl(self):
        """生成 RTL/Verilog 代码"""
        from codegen.rtl_codegen import RTLCodeGenerator
        from codegen.rtl_ram_gen import RAMWrapperGenerator

        rtl_gen = RTLCodeGenerator(self.ir, self.output_dir,
                                    optimize=self.args.optimize)
        rtl_gen.generate()

        if self.args.gen_ram:
            ram_gen = RAMWrapperGenerator(self.ir, self.output_dir)
            ram_gen.generate()

    def _list_output_files(self) -> list[str]:
        """列出所有输出文件"""
        return [str(f) for f in self.output_dir.rglob('*') if f.is_file()]
```

### 9.3 命令行使用示例

```bash
# 生成所有输出
8m_compiler 8mSpec_0821.c tinyReg.txt --target all -o ./build

# 仅生成 C 行为模型
8m_compiler 8mSpec_0821.c tinyReg.txt --target c -o ./build/c_model

# 仅生成 RTL 代码
8m_compiler 8mSpec_0821.c tinyReg.txt --target rtl -o ./build/rtl

# 生成 RTL + 寄存器驱动
8m_compiler 8mSpec_0821.c tinyReg.txt --target rtl --gen-driver -o ./build

# 生成所有 + 测试平台 + RAM 包装器
8m_compiler 8mSpec_0821.c tinyReg.txt --target all --gen-tb --gen-ram -o ./build

# 详细模式 + 面积优化
8m_compiler 8mSpec_0821.c tinyReg.txt --target rtl --optimize area -v
```

### 9.4 Makefile 集成

```makefile
# ==================== Makefile ====================

COMPILER = python3 -m 8m_compiler
SPEC_FILE = 8mSpec_0821.c
REG_FILE  = tinyReg.txt
OUTPUT_DIR = ./build

.PHONY: all c_model rtl driver tb clean

all: c_model rtl driver tb

c_model:
	$(COMPILER) $(SPEC_FILE) $(REG_FILE) --target c -o $(OUTPUT_DIR)/c_model

rtl:
	$(COMPILER) $(SPEC_FILE) $(REG_FILE) --target rtl --gen-ram -o $(OUTPUT_DIR)/rtl

driver:
	$(COMPILER) $(SPEC_FILE) $(REG_FILE) --target c --gen-driver -o $(OUTPUT_DIR)/driver

tb:
	$(COMPILER) $(SPEC_FILE) $(REG_FILE) --target c --gen-tb -o $(OUTPUT_DIR)/tb

# 编译 C 模型并运行测试
test: c_model
	cd $(OUTPUT_DIR)/c_model && gcc -o 8m_sim 8m_c_model.c 8m_tb.c -lm
	cd $(OUTPUT_DIR)/c_model && ./8m_sim

# 检查 RTL 语法
syntax: rtl
	cd $(OUTPUT_DIR)/rtl && for f in *.v; do iverilog -o /dev/null -s $$f $$f 2>&1; done

clean:
	rm -rf $(OUTPUT_DIR)
```

---

## 10. 实现优先级与迭代路线

### Phase 1 — MVP：RegMap 解析器 + C 头文件生成

**目标**：将 `tinyReg.txt` 解析为数据结构，生成寄存器定义头文件

```
任务清单:
  □ 实现 RegMap Lexer（表格格式词法分析）
  □ 实现 RegMap Parser（解析表头 + 数据行）
  □ 构建 MemTableDecl / RegisterDecl / FieldDecl 对象
  □ 实现 C 头文件生成模板（#define 地址、结构体定义）

验证:
  - 解析 tinyReg.txt 并打印 AST
  - 生成的头文件能通过 gcc/clang 编译
  - 头文件中地址值、位宽信息正确

预计工作量: ~500 行 Python
```

### Phase 2 — PseudoC 解析器

**目标**：解析 8mSpec_0821.c，构建完整的 AST

```
任务清单:
  □ 实现 PseudoC Lexer（完整的关键字/操作符/字面量识别）
  □ 实现 PseudoC Parser（递归下降解析器）
  □ 支持核心语法子集（声明/表达式/语句/控制流）
  □ 支持硬件特殊语法（Table访问/位域/包操作/process）
  □ 输出 AST dump（JSON/YAML 格式方便调试）

验证:
  - 能解析整个 8mSpec_0821.c 文件
  - AST dump 包含所有关键信息
  - 特殊语法（复合字段、范围case、花括号索引）正确解析

预计工作量: ~1500 行 Python
```

### Phase 3 — C 代码生成器

**目标**：将 AST 转换为可编译的 C 行为模型和仿真代码

```
任务清单:
  □ 类型映射（uintN → uintXX_t）+ 位域操作宏
  □ 表达式翻译（拼接、切片、复合字段）
  □ 语句翻译（if/while/for/switch/case）
  □ Table 访问翻译（read/write 函数调用）
  □ process → tick 函数（状态机展开）
  □ 包操作翻译（Replace/Insert/Remove → memcpy）
  □ 寄存器驱动生成（read/write API + 地址解码）
  □ 测试平台生成（激励注入 + 结果检查）

验证:
  - C 代码能编译无警告（gcc -Wall -Wextra）
  - C 模型运行结果与规范描述一致
  - 寄存器驱动 API 覆盖所有 Field

预计工作量: ~2000 行 Python
```

### Phase 4 — RTL 代码生成器

**目标**：将 AST 转换为可综合的 Verilog/SystemVerilog

```
任务清单:
  □ 类型映射（uintN → wire/reg [N-1:0]）
  □ process → always 块 + FSM
  □ while(1) → always @(posedge clk) 流水线
  □ if/else 链 → always_comb 优先级编码器
  □ switch/case → casez/casex 硬件选择器
  □ Table → RAM wrapper 实例化
  □ 寄存器bank → reg + 地址解码器
  □ 位域操作 → wire slice + 多路选择器
  □ 包操作 → 移位/选择逻辑

验证:
  - Verilog 代码能通过 lint 检查（Verilator/Mentor lint）
  - 综合报告无严重警告
  - RTL 仿真结果与 C 模型行为一致

预计工作量: ~3000 行 Python
```

### Phase 5 — 优化与扩展

**目标**：提升代码质量，扩展功能

```
任务清单:
  □ 流水线阶段自动推断
  □ 面积/时序优化（资源共享、流水线平衡）
  □ 多时钟域支持
  □ 形式验证支持（生成 SystemVerilog Assertions）
  □ 代码覆盖率分析
  □ 电源优化门控时钟生成
  □ Web UI 图形化查看 AST 和生成的代码

预计工作量: ~2000 行 Python
```

### 迭代甘特图

```
Phase 1: MVP         ████████░░░░░░░░░░░░   (4 周)
Phase 2: Parser      ░░░░████████░░░░░░░░   (4 周，与 Phase 1 有重叠)
Phase 3: C CodeGen   ░░░░░░░░████████░░░░   (4 周)
Phase 4: RTL Gen     ░░░░░░░░░░░░████████   (4 周)
Phase 5: Optimize    ░░░░░░░░░░░░░░░░░░░░   (持续，与 Phase 3/4 重叠)

总计: ~12-16 周（3-4 个月），1 人全职开发
```

---

## 11. 关键难点与应对策略

### 11.1 难点汇总表

| # | 难点 | 具体表现 | 应对策略 |
|---|------|---------|---------|
| 1 | **表式访问与赋值一体** | `DsMac = DsMac Table[giHashIdx]` 左侧赋值、右侧读表 | 解析为两个操作：TABLE_READ + REG_ASSIGN，在 IR 中展开 |
| 2 | **隐式位宽跟踪** | `giAgingIdx++` 在 11 位上自增，需要知道 `giAgingIdx[10:0]` | 变量声明时记录位宽，表达式传播时自动推导 |
| 3 | **复合域 `.{ }` 语法** | `DsMacKey.{ fid, macAddr }` 不是标准 C | Lexer 中将 `.{` 标记为特殊 Token；Parser 构建 CompositeFieldExpr |
| 4 | **花括号索引 `{}`** | `aging{ giAgingIdx[1:0] }` 花括号内是索引表达式 | 在 postfix_expression 中识别 `{` 作为 FieldIndexExpr |
| 5 | **`while(1)` 语义歧义** | C 语义 = 无限循环；硬件语义 = 持续运行/每包触发 | C 后端展开为 tick 函数；RTL 后端推断为 always 块或 FSM |
| 6 | **包处理流水线数据依赖** | parser → switchX → egress 之间有数据依赖 | 数据流分析 + 自动插入流水线寄存器匹配延迟 |
| 7 | **源文件中的拼写错误** | `DsMacAing`（应为 `DsMacAging`）、`egrssFilter` | 语义分析阶段提供模糊匹配建议和警告 |
| 8 | **范围 Case `~` 语法** | `0x11~1f:` 非标准 C Case | AST 中展开为 RangeExpr 或多个 CaseStmt |
| 9 | **Table 复合地址** | `update at { giLrnHash }.{ giLrnSubIdx }` 多维地址 | 地址表达式支持 `.{}` 语法；RTL 中拼接为完整地址 |
| 10 | **触发行为代码生成** | ReadTrigger/WriteTrigger 影响 RTL 的读写使能 | TriggerAnalyzer 生成读写使能信号和时序逻辑 |

### 11.2 详细应对策略

#### 难点 1: 表式访问与赋值一体

```python
# 处理方法: 在 Parser 中将读表和赋值分离

def parse_table_read_or_assign(self):
    """解析可能为 Table 读的赋值语句"""
    identifier = self.peek()

    # 预读: ident = ident Table[ expr ]
    save_pos = self.pos
    try:
        ident1 = self.expect(IDENTIFIER)
        self.expect('=')
        ident2 = self.expect(IDENTIFIER)

        if self.peek() == TokenType.TABLE:
            # 确认是 Table 读
            self.advance()
            self.expect('[')
            index = self.parse_expression()
            self.expect(']')
            self.expect(';')

            # 生成两个 IR 操作: TABLE_READ + ASSIGN
            return CompoundStmt([
                TableReadStmt(ident2, index),
                AssignStmt(IdentifierExpr(ident1), IdentifierExpr(f"__{ident2}_read_temp"))
            ])
    except ParseError:
        self.pos = save_pos  # 回退到预读前

    # 不是 Table 读，按普通赋值解析
    return self.parse_normal_assign()
```

#### 难点 5: while(1) 语义处理

```
分析策略:

  C 后端:
    while(1) → 拆解为 "每包触发" 或 "每时钟周期" 的 tick 函数
    内部所有状态变量（giStormIdx, giCycleCnt）声明为 static
    添加一个 tick 调用作为 "步进"

  RTL 后端:
    while(1) 在 process 顶层 → always @(posedge clk)
    while(1) 嵌套在 if 内 → FSM 状态机

    判断标准:
    - process 入口的 while(1) + 无 Delay → 流水线 always
    - process 入口的 while(1) + 有 Delay → 周期性 FSM
    - 内部嵌套 while → 内层 FSM
```

#### 难点 7: 拼写错误处理

```python
class FuzzySymbolResolver:
    """模糊匹配符号解析器，处理拼写错误"""

    def __init__(self, symbol_table: SymbolTable):
        self.symbol_table = symbol_table

    def resolve(self, name: str) -> Optional[Symbol]:
        """解析符号，支持模糊匹配"""
        # 精确匹配优先
        result = self.symbol_table.lookup(name)
        if result:
            return result

        # 模糊匹配
        candidates = self._find_similar(name,
                                        list(self.symbol_table.symbols.keys()),
                                        threshold=0.7)
        if candidates:
            warning(f"Symbol '{name}' not found. Did you mean '{candidates[0]}'?")
            return self.symbol_table.lookup(candidates[0])

        error(f"Undefined symbol: {name}")
        return None

    def _find_similar(self, target: str, candidates: list[str],
                      threshold: float = 0.7) -> list[str]:
        """使用编辑距离寻找相似符号"""
        results = []
        for candidate in candidates:
            similarity = self._levenshtein_ratio(target.lower(), candidate.lower())
            if similarity >= threshold:
                results.append((similarity, candidate))

        results.sort(reverse=True)
        return [c for s, c in results]

    def _levenshtein_ratio(self, s1: str, s2: str) -> float:
        """计算 Levenshtein 编辑距离比例"""
        # 标准动态规划实现...
        pass
```

---

## 12. 代码文件结构建议

### 完整的项目文件树

```
8m_compiler/
│
├── __init__.py
├── main.py                            # 命令行入口
├── pipeline.py                        # 编译管道编排
│
├── preprocessor.py                    # 注释移除、宏展开
│
├── lexer/
│   ├── __init__.py
│   ├── base_lexer.py                  # 词法分析器基类
│   ├── regmap_lexer.py                # tinyReg.txt 词法分析器
│   └── pseudoc_lexer.py               # 8mSpec_0821.c 词法分析器
│
├── parser/
│   ├── __init__.py
│   ├── ast_nodes.py                   # 所有 AST 节点定义
│   ├── regmap_parser.py               # tinyReg.txt 语法分析器
│   └── pseudoc_parser.py              # 伪 C 语法分析器
│
├── semantic/
│   ├── __init__.py
│   ├── symbol_table.py                # 符号表
│   ├── type_checker.py                # 类型检查器
│   ├── trigger_analyzer.py            # 触发/依赖分析
│   └── fuzzy_resolver.py              # 模糊匹配符号解析
│
├── ir/
│   ├── __init__.py
│   ├── ir_builder.py                  # AST → IR 转换
│   └── ir_optimizer.py                # IR 优化
│
├── codegen/
│   ├── __init__.py
│   ├── c_codegen.py                   # C 行为模型生成
│   ├── c_reg_driver_gen.py            # C 寄存器驱动生成
│   ├── c_tb_gen.py                    # C 测试平台生成
│   ├── rtl_codegen.py                 # Verilog RTL 生成
│   └── rtl_ram_gen.py                 # RAM Wrapper 生成
│
├── templates/
│   ├── reg_header.j2                  # 寄存器头文件模板
│   ├── reg_driver.j2                  # 驱动代码模板
│   ├── rtl_module.j2                  # RTL 模块模板
│   └── ram_wrapper.j2                 # RAM 包装器模板
│
└── utils/
    ├── __init__.py
    ├── bit_utils.py                   # 位宽计算 / 位操作工具
    └── error_handler.py               # 编译器错误 / 警告 / 诊断
```

### 关键实现建议

| 关注点 | 建议 | 理由 |
|--------|------|------|
| **编程语言** | Python 3.8+ | 开发效率高，语法分析库丰富，跨平台 |
| **解析器实现** | 手写递归下降 | 对 DSL 的错误信息友好，易于调试特殊语法 |
| **替代方案** | PLY (Python Lex-Yacc) | 适合标准 C 文法，但对特殊语法支持差 |
| **模板引擎** | Jinja2 | 代码生成更灵活，模板与逻辑分离 |
| **版本控制** | Git + Semantic Versioning | 跟踪语法变更，确保向后兼容 |
| **测试框架** | pytest | 单元测试 Lexer/Parser/CodeGen 各模块 |
| **文档生成** | Sphinx + autodoc | 自动生成 API 文档 |

---

## 附录

### A. 参考资源

- **编译原理**：《Compilers: Principles, Techniques, and Tools》 (Dragon Book)
- **硬件描述**：IEEE 1364-2005 (Verilog), IEEE 1800-2017 (SystemVerilog)
- **PLY 文档**：https://www.dabeaz.com/ply/
- **Jinja2 文档**：https://jinja.palletsprojects.com/

### B. 术语表

| 术语 | 全称 | 说明 |
|------|------|------|
| AST | Abstract Syntax Tree | 抽象语法树，结构化表示源码语法的树状数据结构 |
| IR | Intermediate Representation | 中间表示，介于源码和目标码之间的统一表示 |
| DSL | Domain-Specific Language | 领域特定语言，针对特定问题的专用语言 |
| LALR(1) | Look-Ahead LR(1) | 一种自底向上的 LR 语法分析算法 |
| RTL | Register Transfer Level | 寄存器传输级，描述寄存器间数据流和操作 |
| FSM | Finite State Machine | 有限状态机，常用于硬件控制逻辑 |
| LUT | Look-Up Table | 查表，硬件中实现组合逻辑的基本单元 |
| CRC | Cyclic Redundancy Check | 循环冗余校验 |
| MAC | Media Access Control | 媒体访问控制（MAC 地址） |
| SVA | SystemVerilog Assertions | SystemVerilog 断言，用于形式验证 |

### C. 原始规范文件摘要

#### 8mSpec_0821.c 内容摘要

| 过程/函数 | 类型 | 功能描述 |
|-----------|------|---------|
| `forward()` | process | 顶层包处理过程：解析 → 交换 → 出口 |
| `updateStormCtrl()` | process | 风暴控制更新，周期轮询所有索引 |
| `normalAging()` | process | 正常老化，基于计数器和阈值 |
| `fastAging()` | process | 快速老化，扫描全部 MAC 表 |
| `sendLoopDetect()` | process | 周期发送环路检测报文 |
| `parser()` | function | 以太网/IP 包头解析 |
| `switchX()` | function | L2 交换（VLAN/学习/转发/优先级） |
| `egress()` | function | 出口处理（标签修改/包编辑） |

#### tinyReg.txt 定义的内表和寄存器

| 类型 | 名称 | 深度 | 位宽 | 用途 |
|------|------|------|------|------|
| MemReg | Ds1qPriorMap | 8 | 1 word | 802.1Q 优先级映射 |
| MemReg | DsDscpPriorMap | 64 | 1 word | DSCP 优先级映射 |
| MemReg | DsMac | 2048 | 1 word | MAC 地址表 |
| MemReg | DsMacAging | 512 | 1 word | MAC 老化计数器 |
| MemReg | DsMacKey | 512 | 8 words | MAC 表 Key（地址+VID） |
| MemReg | DsMacStatic | 512 | 1 word | MAC 静态标志 |
| MemReg | DsMacValid | 512 | 1 word | MAC 有效标志 |
| MemReg | DsPort | 8 | 4 words | 端口配置 |
| MemReg | DsStormCtl | 32 | 4 words | 风暴控制配置 |
| MemReg | DsVlan | 16 | 2 words | VLAN 配置 |
| Register | L2AgingCtl | 2 words | — | 老化控制 |
| Register | L2LearnCtl | 1 word | — | 学习控制 |
| Register | LoopDetectCtl | 3 words | — | 环路检测控制 |
| Register | MirrorCtl | 1 word | — | 镜像控制 |
| Register | PriorAssignCtl | 17 words | — | 优先级分配 |
| Register | StormCfgCtl | 2 words | — | 风暴配置控制 |
| Register | VlanIdCamCtl | 8 words | — | VLAN ID CAM 控制 |
