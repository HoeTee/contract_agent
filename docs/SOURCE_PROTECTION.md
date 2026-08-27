# 源码保护方案（AES 加密 + VMP 虚拟化）

## 保护目标

项目源码不能以可解译形态进入最终镜像：即使使用者通过 `docker cp` 或 `docker save` 拿到镜像内容，也无法直接还原 Python 源码。

当前保护由两层组成：

1. **AES 加密层**：源码编译成 pyc 后整体用 AES-256-GCM 加密为 `/app/code.bin`，磁盘上不出现任何 `.py` / `.pyc`。
2. **VMP 编译层（实验验证）**：把负责解密 code.bin 的 loader 共享库用 VMProtect 加壳，密钥重建与 AES 解密代码被虚拟化，静态分析无法读出密钥。

## 总体结构

```text
host（明文小启动器）
  └─ dlopen /app/libloader.vmp.so（VMP 加壳的 loader）
       ├─ 重建 AES 密钥（被虚拟化）
       ├─ AES-256-GCM 解密 /app/code.bin
       ├─ Python 3.12 初始化 + importer 从内存加载模块
       └─ 运行 uvicorn 启动应用
```

镜像中受保护的关键文件只有三个：`/app/host`、`/app/libloader.vmp.so`、`/app/code.bin`。其余资源（frontend、prompts、模板）按设计保持可读。

## 两层保护说明

### AES 加密层（保护数据）

- 输入：项目 Python 源码（由 `protect/modules.txt` 指定范围）。
- 处理：`protect/pack.py` 将源码编译为 pyc、打包为 zip，再使用 32 字节密钥做 AES-256-GCM 加密。
- 输出：`code.bin`（密文）、`key_data.h`（密钥分片，编译进 loader，不进入镜像）。
- 密钥来源：构建期 BuildKit secret（`source_key`），构建结束后即失效；也支持 `build.ps1 -KeyFile` 指定固定密钥。

### VMP 编译层（保护代码与密钥）

- 对象：`libloader.so`（内含密钥重建 `reconstruct_key` 与 AES 解密 `aes_decrypt_payload`）。
- 处理：源码中用 `VMProtectBegin` / `VMProtectEnd` 标记上述两个函数，`vmprotect_con` 加壳后变为 `libloader.vmp.so`。
- 效果：加壳前可直接读出的明文密钥、importer 引导源码、内部符号在加壳后全部消失；运行时行为不变。

## 构建流程

### 1. AES 加密生成 code.bin

```bash
python3 protect/pack.py \
  --root /src \
  --modules-file protect/modules.txt \
  --key-file source.key \
  --output code.bin \
  --key-header key_data.h
```

前提：`source.key` 为 32 字节随机密钥；已安装 `cryptography`。

### 2. VMP 加壳生成 libloader.vmp.so

先编译 loader 共享库：

```bash
clang++ -shared -fPIC -O2 -fvisibility=hidden -fno-ident \
  -I protect/loader/src -I <key_data.h目录> -I <VMP SDK头目录> -I <python3.12头目录> \
  loader_entry.cpp crypto.cpp importer.cpp \
  -L<console工具目录> -lVMProtectSDK64 -lpython3.12 -lcrypto \
  -o libloader.so
```

再加壳：

```bash
cd <console工具目录>
LD_LIBRARY_PATH=. ./vmprotect_con libloader.so
```

加壳器 `vmprotect_con` 由 `vmp-linux-so-protect` skill 的 `build_vmp_console.sh` 在 Linux（glibc ≥ 2.38）环境下从自带源码构建，产物含注册配置 `VMProtectLicense.ini`。

### 3. 构建镜像

```powershell
docker build -f protect\vmp\tmp_test\Dockerfile.vmp-runtime -t contract_agent:vmp-test .
```

运行时阶段基于 `python:3.12-slim`，与现有正式 Dockerfile 的最终阶段一致，仅将入口从 `/app/loader` 换为 `/app/host`。

## 运行时流程

```text
容器启动（CMD: /app/host）
  → dlopen /app/libloader.vmp.so
  → VMP 运行时在内存中解包加壳容器
  → 执行虚拟化代码：重建 AES 密钥 → 解密 code.bin
  → 内存中获得 Python 源码 zip
  → importer 加载模块 → uvicorn 监听 8000
```

VMP 解包与 AES 解密均发生在内存中，磁盘上的 `libloader.vmp.so` 与 `code.bin` 始终保持加壳/密文形态。

## 证据验证

```powershell
# 镜像内不应存在任何 .py / .pyc
docker run --rm --entrypoint sh contract_agent:vmp-test -c "find /app -name '*.py' | wc -l"
docker run --rm --entrypoint sh contract_agent:vmp-test -c "find /app -name '*.pyc' | wc -l"

# code.bin 应为 LEXORA1 密文头
docker run --rm --entrypoint sh contract_agent:vmp-test -c "xxd -l 8 /app/code.bin"

# 加壳 .so 中不应存在明文关键字符串
docker run --rm --entrypoint sh contract_agent:vmp-test -c "strings /app/libloader.vmp.so | grep -cE 'reconstruct_key|aes_decrypt|LEXORA1|zipfile'"
```

## 安全边界

- 静态分析：`docker cp` 后离线解译源码需先逆向 VMP 虚拟机再解 AES，代价以周/月计。
- 动态分析：能运行并观察进程的攻击者（docker exec、ptrace、LD_PRELOAD）仍可从进程内存提取解密后的归档。这是所有运行时保护的共性边界，部署层应配合非 root 运行、`/app` 只读挂载、禁止 `docker exec`、审计日志。
- 法律边界：泄露版 VMP 属未授权软件，仅限技术研究与内部保护，分发与商用存在法律风险。

## 现状与相关文件

- 正式构建链（`Dockerfile`、`protect/build.ps1`）：当前为 AES-only 形态（`/app/loader` + `code.bin`），尚未集成 VMP 阶段。
- VMP 版本：实验验证镜像 `contract_agent:vmp-test`；加壳产物与临时 Dockerfile 位于 `protect/vmp/tmp_test/`，未纳入正式构建链。
- 流程固化：`vmp-linux-so-protect` skill（含泄露版 VMP 源码、注册配置、构建与加壳脚本）。
- 相关源码：`protect/loader/`（loader_entry.cpp、crypto.cpp、importer.cpp、host.c）、`protect/pack.py`。
