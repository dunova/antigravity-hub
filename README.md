# Antigravity Hub

<p align="center">
  <img src="docs/assets/antigravity-hub-logo.svg" alt="Antigravity Hub v3.0.0 Logo" width="128" height="128" />
</p>

<p align="center">
  <strong>专为 Google Antigravity 打造的 Omarchy 原生 C++17 / Qt6 QML 极简高密账号看板、多模型配额看门狗与无感断点接力中枢</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Release-v3.0.0-0F172A?style=flat-square&logo=github" alt="Release" />
  <img src="https://img.shields.io/badge/C++-17-00599C?style=flat-square&logo=c%2B%2B" alt="C++" />
  <img src="https://img.shields.io/badge/Framework-Qt%206.12%20QML-41CD52?style=flat-square&logo=qt" alt="Qt" />
  <img src="https://img.shields.io/badge/Platform-Omarchy%20%7C%20Wayland%20%7C%20Linux-black?style=flat-square" alt="Platform" />
  <img src="https://img.shields.io/badge/Design-Omarchy%20Flat%20%7C%20Zero--Gradient-1c1c1e?style=flat-square" alt="Style" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="License" />
</p>

<p align="center">
  <img src="docs/assets/preview.png" alt="Antigravity Hub v3.0.0 Omarchy Native Desktop UI Preview" width="100%" />
</p>

<p align="center">
  <em>图：Antigravity Hub v3.0.0 生产级实际 UI 界面（基于 Omarchy 设计规范，零渐变纯平顶栏、正统 Antigravity 单色剪影 Logo、闭合 1px 细线外框、屏幕绝对固定的偶奇斑马纹行、Gemini 4 / 3.8 / Claude 三模型配额毫米级对齐排版与一键脱敏打码保护）</em>
</p>

---

## ⚡ v3.0.0 核心架构演进与重大革新

**Antigravity Hub v3.0.0** 标志着控制中心从早期 Web 界面全面跃迁为 **Omarchy 官方原生 C++17 / Qt6 QML 桌面应用程序**：

1. **正统 Google Antigravity 剪影 Logo 重塑**：
   - 彻底废除旧版几何三角假标与蓝色着色；
   - 基于官方流线型不对称悬浮拱门（Sweeping Aerodynamic Arch）精确矢量化，呈现在高对比度 Omarchy 单色剪影下（浅色极黑 `#0F172A`、深色纯白 `#FFFFFF`），与 `Omarchy Control` 风格完美对齐。
2. **纯正 Omarchy 扁平设计铁律**：
   - **全面清零渐变**：顶栏、状态栏、表头与斑马纹背景实现 `gradient` 语法 0 出现率，消除一切发灰发脏的视觉噪点；
   - **全面直角纯平**：`radius: 0` 严格贯彻，1px 语义线框完整闭合；
   - **屏幕绝对固定斑马纹**：彻底分离数据排序与视觉行号，奇偶行背景在任意动态拖拽或表头排序时永远保持绝对交替，杜绝双灰行重叠；
   - **固体防穿透浮动通知（Solid Toast）**：通知条采用实色表面背景搭配左侧 3px 语义状态条，彻底杜绝底层表格文字穿透干扰。
3. **Mac 级半行检测拖拽排序与一键置顶**：
   - 自由上下拖拽账号手柄（`⠿`），支持从最底部一键拖拽至最顶端或任意中间行；
   - 上半行向上插入、下半行向下插入精准检测，配合 3px 蓝绿色插入指示线；
   - 重排结果即时生效并原子级落盘持久化至 `accounts_order`。
4. **全键盘无鼠标工作流与模态防穿透**：
   - `j`/`k` 或方向键平滑导航、`Enter` 毫秒级原生热切号；
   - `isModalOpen` 模态守卫全面覆盖「添加账户」、「系统设置」、「批量删除确认」及「帮助速查」，弹窗开启时底层快捷键物理阻断，`Esc` 分级平滑回退。
5. **严苛的六层全栈测试矩阵**：
   - 28 项 QtTest 单元测试 + 9 项 E2E 真实键鼠拖拽测试，覆盖静态规范、主题 WCAG 对比度、数据模型角色非遮蔽、多尺寸平铺及实机 Wayland 像素级核验，100% 绿灯交付。

---

## 🖥️ 响应式平铺与多主题适配

Antigravity Hub 专为 Hyprland 动态平铺窗口管理器打造，支持自适应栅格布局：

| 布局模式 | 几何尺寸 | 响应式特性 |
| :--- | :--- | :--- |
| **半屏平铺 (Tiled)** | `941 × 1030` | 8 大列紧凑排布，配额进度条与数字倒计时垂直严密对齐 |
| **全屏展示 (Fullscreen)** | `1896 × 1030` | 账号名称与配额槽自适应拉伸，高密视觉依然干爽整洁 |
| **最小受控窗口** | `920 × 540` | 水平滚动条按需启动，表头与数据列绝对锁定无缝对齐 |

<p align="center">
  <img src="docs/assets/preview-tiled.png" alt="Antigravity Hub v3.0.0 Light & Dark Dual Theme Preview" width="100%" />
</p>

<p align="center">
  <em>图：浅色主题（Omarchy Lupine）与强制深色主题双态同屏实机对比（支持半屏平铺自适应、零渐变高对比单色剪影 Logo 与 WCAG ≥ 4.5:1 选区自适应）</em>
</p>

---

## ⌨️ 全局快捷键速查表

在应用任意位置均可使用键盘高效驱动：

| 快捷键 | 功能描述 | 交互行为 |
| :--- | :--- | :--- |
| `j` / `↓` | 下移选择 | 选择列表中的下一个账号 |
| `k` / `↑` | 上移选择 | 选择列表中的上一个账号 |
| `PgUp` / `PgDn` | 快速翻页 | 每次按 15 个账号步长快速翻页 |
| `Enter` | 原生热切号 | 毫秒级原子重载，IDE 编辑器与终端零中断 |
| `/` | 聚焦搜索 | 光标聚焦至搜索栏，支持实时模糊筛选 |
| `m` | 隐私脱敏打码 | 一键在明文与 `c***8` 脱敏打码模式间切换（截图保护） |
| `r` | 并发刷新 | 后台异步探针拉取最新配额数据 |
| `s` | 偏好设置 | 呼出控制台配置对话框 |
| `g` | 切换至 TopG | 自动计算并一键切入当前 Gemini 配额最高的健康账号 |
| `w` | 全池错峰预热 | 触发全池长连接预热与滑动窗口建立 |
| `?` / `F1` | 帮助弹窗 | 切换全局快捷键速查中心 |
| `Esc` | 分级取消 | 优先关闭弹窗 → 清空搜索输入并释放焦点 |
| `q` | 退出程序 | 安全清理并退出 Antigravity Hub |

---

## 🛠️ 构建、测试与运行

### 1. 系统依赖
确保 Omarchy / Arch Linux 系统已就绪标准 C++ 与 Qt6 基础包：
```bash
omarchy-pkg-add base-devel qt6-base qt6-declarative qt6-svg hicolor-icon-theme
```

### 2. 编译与测试
```bash
# 进入项目工作区
cd ~/Projects/antigravity-hub

# 快速编译并构建二进制产物 (产物位于 build/antigravity-hub)
./bin/build

# 离线执行全套 28 项 Qt Test 自动化测试套件
./bin/test
```

### 3. 安装与运行
```bash
# 复制二进制至用户执行路径
cp build/antigravity-hub ~/.local/bin/antigravity-hub

# 启动原生桌面应用
antigravity-hub
```

---

## 📄 开源许可证

本项目采用 [MIT License](LICENSE) 授权许可。
