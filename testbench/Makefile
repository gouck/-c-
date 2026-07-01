# Makefile — 8m 测试框架

# === 路径配置 ===
# 默认使用最新的 c_project
DUT_DIR ?= $(shell ls -d output/*/c_project 2>/dev/null | tail -1)
ifeq ($(DUT_DIR),)
DUT_DIR = ../output/008/c_project
endif

DUT_SRC_DIR = $(DUT_DIR)/src
DUT_INC_DIR = $(DUT_DIR)/include
TB_C_API    = c_api

# === 编译选项 ===
CC       = gcc
CFLAGS   = -std=c99 -w -fcommon -fPIC
LDFLAGS  = -shared
INCLUDES = -I$(DUT_INC_DIR) -I$(TB_C_API)

# 生成的 C 源文件（排除 reg_drv_*.c，因为 switch_api.c 包含了寄存器定义）
# 注意：8m_common.c 中有 weak enqueue_packet，switch_api.c 提供了强符号
DUT_SRCS  = $(wildcard $(DUT_SRC_DIR)/8m_*.c)
DUT_SRCS  := $(filter-out $(DUT_SRC_DIR)/8m_common.c, $(DUT_SRCS))
# 8m_common.c 去掉 weak enqueue_packet/send_packet，也在链接中
DUT_SRCS  += $(DUT_SRC_DIR)/8m_common.c

# === 目标 ===
.PHONY: all lib test test-aft clean help

all: lib test

# 编译 C 动态库
lib: libswitch_dut.so

libswitch_dut.so: $(TB_C_API)/switch_api.c $(DUT_SRCS)
	$(CC) $(LDFLAGS) -o $@ \
		$(TB_C_API)/switch_api.c \
		$(DUT_SRCS) \
		$(CFLAGS) $(INCLUDES)
	@echo "  [OK] libswitch_dut.so built"

# 运行 AFT 测试
test-aft: lib
	python tests/test_aft.py

# 运行所有测试
test: lib
	python tests/test_aft.py

# 清理
clean:
	rm -f libswitch_dut.so libswitch_dut.dll
	rm -f *.o

help:
	@echo "用法:"
	@echo "  make lib        - 编译 libswitch_dut.so"
	@echo "  make test       - 运行所有测试"
	@echo "  make test-aft   - 运行 AFT 全覆盖测试"
	@echo "  make clean      - 清理"
	@echo ""
	@echo "变量:"
	@echo "  DUT_DIR=<path>  - 指定 c_project 路径"
	@echo "  当前: $(DUT_DIR)"
