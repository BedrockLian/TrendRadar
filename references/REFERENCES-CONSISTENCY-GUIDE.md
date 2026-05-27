# References 一致性维护指南

> 本文档指导 Agent 如何消除 Skill references/ 与根 references/ 之间的内容冲突，
> 并建立长期防护机制防止再次漂移。

---

## 一、问题说明

### 1.1 两套 references 的关系

TrendRadar 存在两套 references 目录：

```
trendradar/
├── references/                     ← 根目录（项目级真相源）
│   ├── traps.md
│   ├── pipeline.md
│   └── ...（29 个文件）
│
└── skills/
    ├── news-secretary/
    │   └── references/             ← Skill 目录（Agent 实际读取的位置）
    │       ├── traps.md            ← 同名副本
    │       └── ...（13 个文件）
    ├── self-healing/
    │   └── references/             ← 又一个 Skill 目录
    │       ├── traps.md            ← 又一份额副本
    │       └── ...（11 个文件）
    └── ...
```

**Hermes Agent 加载 Skill 时，只读 Skill 目录下的 `references/`**。根目录的 `references/` 是项目维护者阅读和编辑的位置，但 Agent 看不到它。

### 1.2 冲突是怎么产生的

```
维护者修改了 references/traps.md（根目录）
        ↓
忘记同步到 skills/news-secretary/references/traps.md
        ↓
两份文件内容逐渐漂移
        ↓
Agent 读到过时的 Skill 版本，做出错误决策
```

这是一个**纯人工同步问题**，当前没有任何自动化机制防止它发生。

### 1.3 当前冲突清单

截至 2026-05-26，以下文件存在内容不一致：

| 文件 | 根目录 | news-secretary | self-healing | system-config | 状态 |
|------|--------|---------------|-------------|--------------|------|
| `traps.md` | 9149B | **8549B** ❌ | 9149B ✅ | 9149B ✅ | news-secretary 缺 ~600B |
| `pipeline.md` | 3547B | **2645B** ❌ | — | 3547B ✅ | news-secretary 缺 ~900B |
| `translation-pipeline-sync.md` | 4513B | **2616B** ❌ | — | — | news-secretary 缺 ~1900B |
| `render-format.md` | 2333B | 2333B ✅ | — | — | 已同步 |
| `sources-management.md` | — | 4336B | 4336B | — | 两份相同（无根目录版） |
| `cron-operations.md` | 3305B | 3305B ✅ | — | — | 已同步 |

**影响最大的冲突**：

1. **`traps.md`** — news-secretary 版本缺少 Trap 39（"改变游戏规则"成语误判）和 Trap 40（药监/政治条目误入科技板块）。Agent 排查分类问题时找不到这两个案例。

2. **`pipeline.md`** — news-secretary 版本缺少"自动特性"节（SILENT 闭环、熔断退避、多样性惩罚等）和"脚本清单"节。Agent 对管线能力的理解不完整。

3. **`translation-pipeline-sync.md`** — news-secretary 版本缺少"陷阱 2"的详细描述（只有两层回退时翻译写入通用版但渲染读日期版）和修复代码。Agent 排查翻译丢失问题时缺少关键线索。

---

## 二、修复步骤

### Step 1: 同步 3 个冲突文件（2 分钟）

将根目录版本覆盖到 Skill 目录：

```bash
cd ~/TrendRadar/trendradar

# 1. traps.md — news-secretary 版本缺 Trap 39-40
cp references/traps.md skills/news-secretary/references/traps.md

# 2. pipeline.md — news-secretary 版本缺自动特性+脚本清单
cp references/pipeline.md skills/news-secretary/references/pipeline.md

# 3. translation-pipeline-sync.md — news-secretary 版本缺陷阱 2 详述
cp references/translation-pipeline-sync.md skills/news-secretary/references/translation-pipeline-sync.md
```

### Step 2: 验证同步结果（1 分钟）

```bash
# 对比 MD5，所有同名文件应完全一致
for f in traps.md pipeline.md translation-pipeline-sync.md render-format.md; do
    echo "=== $f ==="
    find references/ skills/*/references/ -name "$f" -exec md5sum {} \;
done
```

**期望输出**：每个文件的所有副本 MD5 值完全相同。

### Step 3: 补全缺失的根目录文件（2 分钟）

`sources-management.md` 只存在于 Skill 目录，根目录没有。将其复制到根目录作为真相源：

```bash
# sources-management.md 在 news-secretary 和 self-healing 中各有一份（内容相同）
# 复制到根目录作为真相源
cp skills/news-secretary/references/sources-management.md references/sources-management.md

# 删除 Skill 目录中的副本
rm skills/news-secretary/references/sources-management.md
rm skills/self-healing/references/sources-management.md
```

然后更新两个 Skill 的 SKILL.md 中的引用路径。

**news-secretary SKILL.md**：

```markdown
# 旧
| `references/sources-management.md` | RSS 源发现与添加 |

# 新（指向根目录的相对路径）
| `../../references/sources-management.md` | RSS 源发现与添加 |
```

**self-healing SKILL.md**：同样修改。

> **注意**：如果 Hermes Agent 不支持 `../../` 相对路径解析，则保留 Skill 目录中的副本，但必须确保与根目录版本一致。验证方法：在 Agent 中执行 `cat references/sources-management.md`，确认能读到内容。

### Step 4: 验证无 dead references（2 分钟）

检查所有 SKILL.md 中引用的 references 文件是否实际存在：

```bash
cd ~/TrendRadar/trendradar

for skill_dir in skills/*/; do
    skill_name=$(basename "$skill_dir")
    # 提取 SKILL.md 中所有 `references/xxx.md` 引用
    grep -oP '`references/[^`]+`' "$skill_dir/SKILL.md" 2>/dev/null | while read -r ref; do
        # 去掉反引号和 references/ 前缀
        filename=$(echo "$ref" | tr -d '`' | sed 's|^references/||')
        # 检查 Skill 目录或根目录是否存在该文件
        if [ ! -f "$skill_dir/references/$filename" ] && [ ! -f "references/$filename" ]; then
            echo "❌ DEAD: $skill_name -> $ref"
        fi
    done
done

echo "检查完成。无输出 = 无 dead references。"
```

---

## 三、长期防护机制

### 方案 A: CI 一致性检查（推荐）

在 `.github/workflows/ci.yml` 中添加一个检查步骤，每次 PR 自动检测副本是否同步：

```yaml
  check-references:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check references consistency
        run: |
          python3 -c "
          import hashlib, sys
          from pathlib import Path

          root = Path('trendradar/references')
          mismatches = []

          for skill_refs in Path('trendradar/skills').glob('*/references'):
              for f in skill_refs.glob('*.md'):
                  root_f = root / f.name
                  if root_f.exists():
                      h1 = hashlib.md5(root_f.read_bytes()).hexdigest()
                      h2 = hashlib.md5(f.read_bytes()).hexdigest()
                      if h1 != h2:
                          mismatches.append(f'{root_f} ({h1[:8]}) != {f} ({h2[:8]})')

          if mismatches:
              print('ERROR: Skill references/ 与根 references/ 内容不一致:')
              for m in mismatches:
                  print(f'  {m}')
              print()
              print('修复方法: cp trendradar/references/<file> trendradar/skills/<skill>/references/<file>')
              sys.exit(1)
          else:
              print('OK: 所有同名 references 文件内容一致')
          "
```

**效果**：每次 PR 如果修改了根目录的 references 但没同步 Skill 目录，CI 会报错并给出修复命令。

### 方案 B: 符号链接（Linux 生产环境）

将 Skill references/ 中的同名文件替换为指向根目录的符号链接：

```bash
cd ~/TrendRadar/trendradar

# 对所有 Skill 目录中的同名文件创建符号链接
for skill_refs in skills/*/references; do
    for f in "$skill_refs"/*.md; do
        filename=$(basename "$f")
        root_file="../../../references/$filename"
        if [ -f "references/$filename" ]; then
            # 删除副本，创建符号链接
            rm "$f"
            ln -s "$root_file" "$f"
            echo "✅ $f -> $root_file"
        fi
    done
done
```

**优点**：一处修改，处处生效。零同步成本。
**缺点**：
- Windows 开发环境不支持（但生产环境是 Linux，不影响运行）
- `git` 会跟踪符号链接本身（不是目标文件），需要在 `.gitattributes` 中配置
- 需要验证 Hermes Agent 是否能正确解析符号链接

**验证**：
```bash
# 确认符号链接正确
ls -la skills/news-secretary/references/traps.md
# 期望: traps.md -> ../../../references/traps.md

# 确认内容可读
head -3 skills/news-secretary/references/traps.md
```

### 方案 C: 删除 Skill 副本 + SKILL.md 改用根目录路径

如果 Hermes Agent 支持从 Skill 目录向上查找文件：

```markdown
# SKILL.md 中改为引用根目录
| `../../references/traps.md` | 已知陷阱全集 |
```

**验证**：在 Agent 中执行 `cat ../../references/traps.md`，确认能读到内容。如果不能，此方案不可用。

---

## 四、日常维护规则

### 4.1 编辑 references 时的铁律

```
修改根目录 references/xxx.md 后
    ↓
检查是否有 Skill 目录的同名副本
    ↓
    ├─ 有副本 → 同步: cp references/xxx.md skills/*/references/xxx.md
    └─ 无副本 → 完成
```

**快速检查命令**：

```bash
# 查找所有同名文件
filename="traps.md"  # 替换为实际文件名
find references/ skills/*/references/ -name "$filename"
```

### 4.2 新增 references 文件时

1. 新文件**只放在根目录** `references/`
2. 在需要引用它的 Skill 的 SKILL.md 中添加引用
3. 如果 Agent 无法通过相对路径访问根目录，再在 Skill references/ 中创建副本

### 4.3 修改 Skill SKILL.md 时

检查 SKILL.md 中引用的所有 references 文件是否存在：

```bash
grep -oP '`references/[^`]+`' skills/<skill-name>/SKILL.md
# 逐个确认文件存在
```

### 4.4 定期审计（建议每月一次）

```bash
cd ~/TrendRadar/trendradar

echo "=== 1. 同名文件一致性 ==="
for f in $(find references/ -name '*.md' -exec basename {} \; | sort -u); do
    copies=$(find references/ skills/*/references/ -name "$f" 2>/dev/null)
    count=$(echo "$copies" | wc -l)
    if [ "$count" -gt 1 ]; then
        hashes=$(echo "$copies" | xargs md5sum | awk '{print $1}' | sort -u | wc -l)
        if [ "$hashes" -gt 1 ]; then
            echo "❌ $f: $count 份副本，$hashes 种内容"
        else
            echo "✅ $f: $count 份副本，内容一致"
        fi
    fi
done

echo ""
echo "=== 2. Dead references ==="
for skill_dir in skills/*/; do
    skill_name=$(basename "$skill_dir")
    grep -oP '`references/[^`]+`' "$skill_dir/SKILL.md" 2>/dev/null | while read -r ref; do
        filename=$(echo "$ref" | tr -d '`' | sed 's|^references/||')
        if [ ! -f "$skill_dir/references/$filename" ] && [ ! -f "references/$filename" ]; then
            echo "❌ DEAD: $skill_name -> $ref"
        fi
    done
done

echo ""
echo "=== 3. 文件总数 ==="
echo "根目录: $(find references/ -name '*.md' | wc -l) 个"
echo "Skill 目录: $(find skills/*/references/ -name '*.md' | wc -l) 个"
echo "总计: $(find references/ skills/*/references/ -name '*.md' | wc -l) 个"
```

---

## 五、决策流程图

当 Agent 需要读取或修改 references 时，按此流程决策：

```
需要读取某个 reference 文件
    │
    ├─ 知道文件名 → 先查 Skill 本地 references/
    │   ├─ 存在 → 读取（但注意可能与根目录不同步）
    │   └─ 不存在 → 查根目录 references/
    │       ├─ 存在 → 读取
    │       └─ 不存在 → 报告文件缺失
    │
    └─ 不知道文件名 → 查 references/INDEX.md 按功能定位

需要修改某个 reference 文件
    │
    ├─ 修改根目录 references/xxx.md（真相源）
    │
    └─ 检查 Skill 目录是否有同名副本
        ├─ 有 → cp references/xxx.md skills/*/references/xxx.md
        └─ 无 → 完成
```

---

## 六、验证清单

完成所有修复后，逐项确认：

```bash
cd ~/TrendRadar/trendradar

# ✅ 1. 三个冲突文件已同步
diff references/traps.md skills/news-secretary/references/traps.md
diff references/pipeline.md skills/news-secretary/references/pipeline.md
diff references/translation-pipeline-sync.md skills/news-secretary/references/translation-pipeline-sync.md
# 期望: 全部无输出（内容完全一致）

# ✅ 2. 无 dead references
for skill_dir in skills/*/; do
    grep -oP '`references/[^`]+`' "$skill_dir/SKILL.md" 2>/dev/null | while read -r ref; do
        filename=$(echo "$ref" | tr -d '`' | sed 's|^references/||')
        [ ! -f "$skill_dir/references/$filename" ] && [ ! -f "references/$filename" ] && echo "DEAD: $(basename $skill_dir) -> $ref"
    done
done
# 期望: 无输出

# ✅ 3. 所有同名文件 MD5 一致
for f in $(find references/ -name '*.md' -exec basename {} \; | sort -u); do
    copies=$(find references/ skills/*/references/ -name "$f" 2>/dev/null)
    count=$(echo "$copies" | wc -l)
    if [ "$count" -gt 1 ]; then
        hashes=$(echo "$copies" | xargs md5sum | awk '{print $1}' | sort -u | wc -l)
        [ "$hashes" -gt 1 ] && echo "❌ $f: 内容不一致"
    fi
done
# 期望: 无输出

# ✅ 4. CI 检查脚本可用（如果已添加）
python3 -c "
import hashlib, sys
from pathlib import Path
root = Path('references')
mismatches = []
for skill_refs in Path('skills').glob('*/references'):
    for f in skill_refs.glob('*.md'):
        root_f = root / f.name
        if root_f.exists():
            h1 = hashlib.md5(root_f.read_bytes()).hexdigest()
            h2 = hashlib.md5(f.read_bytes()).hexdigest()
            if h1 != h2:
                mismatches.append(f'{root_f} != {f}')
if mismatches:
    print('FAIL:', mismatches)
    sys.exit(1)
print('PASS: 所有同名 references 一致')
"
```
