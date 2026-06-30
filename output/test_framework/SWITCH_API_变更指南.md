# switch_api.c 变更指南

## 这个文件什么时候需要改

`switch_api.c` 是编译器生成代码和 tb_new.c 之间的适配层。  
它**不是永不变的**，而是在编译器输出变化时需要同步更新。

---

## 变更触发条件速查

| 你在项目中做了什么 | switch_api.c 需要改吗 | 改动位置 |
|-------------------|:---:|---------|
| 修改了 `8mSpec_0821.c` 中 process 内部逻辑 | ❌ 不需要 | — |
| 修改了 `tinyReg.txt` 的表项字段 | ❌ 不需要 | — |
| 修改了 `tinyReg.txt` 的寄存器默认值 | ✅ 需要 | `_init_all_tables()` |
| **新增了** `tinyReg.txt` 中的表 | ✅ 需要 | `_init_all_tables()` + include |
| **新增了** parser 输出变量 | ✅ 需要 | extern 声明块 + 读接口 |
| **重命名了** `process forward()` | ✅ 需要 | `forward_tick()` 改为 `新名字_tick()` |
| **新增了** 寄存器 | ✅ 需要 | 寄存器实例定义 + `_init_all_tables()` |
| 修改了端口数量（8→10） | ✅ 需要 | 所有 `[8]` 循环改为 `[10]` |

---

## 场景一：新增了 parser 输出变量

### 你在 DSL 中加了

```
// 8mSpec_0821.c  parser() 函数中新增
prIpProto[7:0] = PacketByte[giPldOffset+9][7:0];   // IP 协议号
```

### switch_api.c 需要改的地方

```diff
  extern uint32_t piSrcPort, piPktLength;
  extern uint32_t prVlanId, piVlanId, piPrior;
+ extern uint32_t prIpProto;                    // ← 新增 extern

  // ... 在通用接口实现区域新增读接口 ...
+ uint32_t switch_ip_protocol(void) {            // ← 新增 API
+     return prIpProto;
+ }
```

### switch_api.h 需要同步加

```diff
+ uint32_t switch_ip_protocol(void);
```

---

## 场景二：新增了 tinyReg.txt 中的表

### 你在 tinyReg.txt 中加了

```
DsIgmpGroup	DsIgmpGroup	64	...
```

### switch_api.c 需要改的地方

```diff
  #include "reg_drv_tinyReg.h"
  #include "reg_drv_tinyReg2.h"
+ #include "reg_drv_tinyReg3.h"                  // ← 新增 include

  // 在 _init_all_tables() 中新增
+ memset(DsIgmpGroup_mem, 0, sizeof(DsIgmpGroup_mem));
```

---

## 场景三：重命名了主 process

### DSL 中

```
// 之前
process forward() { while(1) { parser(); switchX(); egress(); } }

// 之后
process main_pipeline() { while(1) { parser(); switchX(); egress(); } }
```

### switch_api.c 需要改的地方

```diff
- void forward_tick(void);
+ void main_pipeline_tick(void);                 // ← extern 声明改名

  void switch_process_packet(...) {
      ...
-     forward_tick();
+     main_pipeline_tick();                      // ← 调用改名
  }
```

---

## 场景四：端口数从 8 改为 10

### switch_api.c 需要改的地方（涉及 8 处）

```diff
- static uint64_t g_rx_cnt[8];
- static uint64_t g_tx_cnt[8];
- static uint64_t g_drop_cnt[8];
+ static uint64_t g_rx_cnt[10];
+ static uint64_t g_tx_cnt[10];
+ static uint64_t g_drop_cnt[10];

- static int g_stp_state[8];
+ static int g_stp_state[10];

- static int g_port_max_mac[8];
+ static int g_port_max_mac[10];

  // _init_all_tables() 中
- for (i = 0; i < 8; i++) { ... }
+ for (i = 0; i < 10; i++) { ... }

- if (src_port >= 0 && src_port < 8)
+ if (src_port >= 0 && src_port < 10)
  (出现 4 次)
```

---

## 编译命令（通用模板）

每次改了 switch_api.c 后，用这个命令重新编译测试：

```powershell
# 找到最新工程编号
$N = (Get-ChildItem output -Directory | Where-Object { $_.Name -match '^\d+$' -and (Test-Path (Join-Path $_.FullName "c_project")) } | Sort-Object { [int]$_.Name } | Select-Object -Last 1).Name

# 编译
cd output/$N/c_project
gcc ../../test_framework/tb_new.c ../../test_framework/switch_api.c src/8m_common.c src/8m_main.c src/8m_parser.c src/8m_switchX.c src/8m_egress.c -o tb_new.exe -std=c99 -w -fcommon -Iinclude -I../../test_framework

# 运行
.\tb_new.exe
```
