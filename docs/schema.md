# 剧本 YAML Schema 设计文档

本文档定义 Novel2Script Agent Studio 最终导出的剧本 YAML Schema，并说明该 Schema 的设计原因。

这个 Schema 的目标不是把小说简单装进 `scene / action / dialogue` 这样的格式里，而是服务“AI 改编副编剧”工作流：系统需要把小说中的叙述、心理、氛围、背景和伏笔，转换成可表演、可拍摄、可继续修改的剧本初稿，同时保留来源、改编理由和后续打磨建议。

## 设计目标

Schema 主要服务五个目标：

1. **可表演**
   小说常常依赖心理描写、旁白和氛围铺陈，剧本需要把这些内容转成动作、对白、场景冲突和情绪变化。因此每场戏不仅保存正文，还保存 `purpose`、`conflict`、`emotional_shift`、`performance_notes` 等字段。

2. **可追踪**
   作者需要知道每场戏来自哪些章节、参考了哪些原文内容，以及哪些内容是 AI 改写或新增。因此 Schema 保留 `source_chapters`、`source_excerpt`、`source_function` 和动作/对白级别的 `origin`。

3. **可控制**
   作者不是把小说交给 AI 黑箱生成，而是在指挥一个副编剧。所以最终 YAML 需要记录作者选择的剧本类型、改编尺度、风格偏向、保留内容、禁止改动内容和备注，这些都保存在 `adaptation_profile` 中。

4. **可校验**
   YAML 不只是展示文本，还要能被程序检查。角色、地点、场景、对白说话人都使用稳定 ID，后端可以校验引用是否存在，前端也可以基于 JSON Schema 给出编辑提示。

5. **可返修**
   作者后续可能只想改某一场、某一章，或重新做章节之间的连贯性合成。因此每场戏都保存改编理由、制作风险和修改建议，方便局部返修，而不是每次推倒重来。

## Schema 真源

Schema 的唯一代码真源是：

```text
backend/app/domain/schemas.py
```

其中 `ScriptJson` 是最终剧本 JSON/YAML 的根模型。后端会从 Pydantic v2 模型生成 JSON Schema，并通过接口提供给前端：

```text
GET /api/schema/script
```

最终导出流程是：

```text
LLM 输出结构化 JSON
 -> Pydantic 模型校验
 -> JSON Schema / 语义校验
 -> ruamel.yaml 程序化导出 YAML
```

也就是说，**LLM 不直接输出 YAML**。这样设计是为了避免 YAML 缩进、字段缺失、枚举值错误和引用错乱等问题。

## 顶层结构

最终 YAML 根对象结构如下：

```yaml
metadata:
adaptation_profile:
adaptation_strategy:
characters:
locations:
props:
scenes:
adaptation_notes:
```

| 字段 | 类型 | 作用 | 设计原因 |
|---|---|---|---|
| `metadata` | object | 剧本基础信息 | 让产物有标题、语言、类型和一句话故事，方便展示与归档 |
| `adaptation_profile` | object | 作者控制项 | 保留作者当时的创作指令，避免最终稿脱离作者意图 |
| `adaptation_strategy` | string[] | 整体改编策略 | 解释 AI 为什么按这个方向改，而不是只给结果 |
| `characters` | object[] | 角色表 | 统一角色 ID，方便校验对白说话人和场景出场人物 |
| `locations` | object[] | 地点表 | 统一地点 ID，避免同一地点前后命名不一致 |
| `props` | object[] | 重要道具表 | 记录信件、剧本、灯等推动剧情的物件 |
| `scenes` | object[] | 剧本场景列表 | 最终剧本主体，每场戏都包含来源、冲突、动作、对白和返修信息 |
| `adaptation_notes` | string[] | 全局改编备注 | 保存压缩、合并、删减、风格处理等整体说明 |

## 枚举值

### `format_type`

表示目标剧本形式：

```text
film | short_drama | stage_play | radio_drama | animation | game_script
```

设计原因：不同媒介的表达重点不同。短剧强调钩子和节奏，舞台剧强调场面调度，广播剧依赖声音，游戏脚本可能需要交互节点。把格式写入 Schema，可以让后续生成和返修有明确方向。

### `adaptation_scale`

表示改编尺度：

```text
faithful | balanced | bold
```

设计原因：作者需要控制 AI 是忠实改编、平衡改写，还是大胆重构。这个字段能防止 AI 自动扩大改编范围。

### `style_focus`

表示风格重点：

```text
psychological | action | dialogue | suspense | relationship | custom
```

设计原因：小说转剧本的难点不同。心理外化、动作推进、对白压缩、悬疑节奏和关系张力对应不同的改写策略。

### `origin`

动作和对白的来源标记：

```text
source_extracted | ai_adapted | ai_added
```

含义：

- `source_extracted`：直接来自原文或接近原文。
- `ai_adapted`：根据原文含义改写成可表演动作或对白。
- `ai_added`：AI 为增强戏剧性、连贯性或可表演性新增。

设计原因：作者最关心“哪些是原文，哪些是 AI 改的，哪些是 AI 新增的”。这个字段让 AI 的创作边界可见。

## `metadata`

```yaml
metadata:
  title: 雨巷里的来信
  source_chapter_count: 3
  language: zh-CN
  genre: mystery drama
  logline: 林夏循着父亲留下的线索走进旧剧院。
```

| 字段 | 说明 |
|---|---|
| `title` | 剧本标题 |
| `source_chapter_count` | 来源章节数，至少为 3 |
| `language` | 剧本语言，默认 `zh-CN` |
| `genre` | 类型标签，例如 `drama`、`mystery drama` |
| `logline` | 一句话故事 premise |

设计原因：这些字段让 YAML 能作为独立剧本初稿存在，不依赖前端页面或运行上下文。

## `adaptation_profile`

```yaml
adaptation_profile:
  format_type: short_drama
  adaptation_scale: balanced
  style_focus: psychological
  generation_scope: [1, 2, 3]
  preserve_items:
    - 保留林夏、周砚和父亲失踪线索
  forbidden_changes:
    - 不要改变主角继续调查父亲失踪的核心动机
  author_notes: 心理活动尽量转成动作、停顿和克制对白。
```

| 字段 | 说明 |
|---|---|
| `format_type` | 作者选择的剧本形式 |
| `adaptation_scale` | 作者选择的改编尺度 |
| `style_focus` | 作者选择的风格重点 |
| `generation_scope` | 作者选择生成的来源章节序号 |
| `preserve_items` | 必须保留的内容 |
| `forbidden_changes` | 禁止改动的内容 |
| `author_notes` | 自由创作备注 |

设计原因：最终 YAML 必须保存作者意图。否则同一段小说生成出的剧本无法解释“为什么是短剧版”“为什么强化心理外化”“为什么只生成前三章”。

## `adaptation_strategy`

```yaml
adaptation_strategy:
  - 将内心疑虑改成停顿、翻找和试探对白。
  - 每章至少保留一个可追踪场景，方便作者继续局部修改。
```

设计原因：它保存 AI 的整体改编判断。作者看到的不只是最终文本，还能知道 AI 采用了什么创作策略，方便判断方向是否正确。

## 角色、地点和道具索引

### `characters`

```yaml
characters:
  - id: char_linxia
    name: 林夏
    role: protagonist
    description: 谨慎、执着的档案馆工作人员。
    first_appearance_chapter: 1
```

角色 ID 必须符合：

```text
char_[a-zA-Z0-9_]+
```

设计原因：对白中的 `speaker_id` 和场景中的 `characters` 都引用角色 ID。统一角色表可以避免“林夏 / 小夏 / 女主”在结构上被误认为不同角色。

### `locations`

```yaml
locations:
  - id: loc_archive
    name: 城南档案馆
    description: 雨巷旁的旧档案馆。
```

地点 ID 必须符合：

```text
loc_[a-zA-Z0-9_]+
```

设计原因：场景通过 `location_id` 引用地点，方便检查地点是否存在，也方便后续按地点拆分剧本或制作拍摄清单。

### `props`

```yaml
props:
  - id: prop_letter
    name: 无编号信件
    description: 引导林夏前往旧剧院的关键线索。
```

道具 ID 必须符合：

```text
prop_[a-zA-Z0-9_]+
```

设计原因：小说改编常依赖信件、旧剧本、灯、钥匙等物件推动剧情。把重要道具结构化，有利于追踪伏笔和制作需求。

## `scenes`

`scenes` 是最终 YAML 的核心。每个 scene 表示一场可表演的戏。

```yaml
scenes:
  - id: sc_001
    title: 雨夜档案馆的发现
    source_chapters: [1]
    source_excerpt: 林夏在城南档案馆值夜班，发现一封没有编号的信。
    source_function: 开篇设悬，引出旧剧院和父亲失踪线索。
    location_id: loc_archive
    time_of_day: night
    characters: [char_linxia]
    purpose: 建立主角和核心悬念。
    scene_purpose: 把原文的氛围和心理疑问转成可见发现。
    conflict: 林夏想确认信件来源，但信件把她拉回父亲失踪事件。
    emotional_shift: 从疲惫麻木到警觉和主动追查。
    adaptation_reason: 信件发现需要成为第一场的行动触发点。
    performance_notes: 雨声、纸张摩擦和停顿可以外化林夏的不安。
    risk_note: 避免只用旁白解释信件含义。
    production_risk: 档案馆氛围不能太静，需要用声音和动作维持张力。
    format_type: short_drama
    actions:
      - text: 林夏把信举到灯下，指尖停在“那盏灯”三个字上。
        beat: discovery
        origin: ai_adapted
    dialogues:
      - speaker_id: char_linxia
        line: 这不是馆里的编号。
        emotion: confused
        origin: ai_adapted
    ai_added_content:
      - 增加短暂停顿，用动作外化疑虑。
    revision_suggestions:
      - 如果开场仍然偏静，可以增加一个外部打扰。
    adaptation_notes:
      - 将原文氛围压缩为雨声、灯光和信件特写。
```

### 场景字段说明

| 字段 | 说明 | 设计原因 |
|---|---|---|
| `id` | 场景 ID，如 `sc_001` | 稳定定位一场戏，方便局部返修 |
| `title` | 场景标题 | 方便作者快速浏览 |
| `source_chapters` | 来源章节序号 | 保证场景可追溯到原文 |
| `source_excerpt` | 来源原文片段 | 让作者检查 AI 是否脱离原著 |
| `source_function` | 原文段落在小说中的功能 | 区分“事件本身”和“它在原文里起什么作用” |
| `location_id` | 地点 ID | 校验地点引用，方便制作拆分 |
| `time_of_day` | 时间标签 | 支持基础拍摄/舞台调度信息 |
| `characters` | 出场角色 ID | 校验角色引用 |
| `purpose` | 剧作目的 | 说明这场戏在剧本结构中干什么 |
| `scene_purpose` | 改编后的场景功能 | 说明小说内容如何被转成戏剧场面 |
| `conflict` | 场景冲突 | 防止剧本只复述情节，没有戏剧推动 |
| `emotional_shift` | 情绪变化 | 帮助把心理描写转成可表演节奏 |
| `adaptation_reason` | 改编原因 | 解释 AI 为什么这样改 |
| `performance_notes` | 表演/镜头/声音提示 | 帮助作者继续把文本打磨成可拍、可演内容 |
| `risk_note` | 创作风险 | 提醒哪里可能节奏慢、解释感强或动机不清 |
| `production_risk` | 制作风险 | 提醒场景在拍摄、舞台或声音实现上的难点 |
| `format_type` | 本场戏采用的剧本形式 | 支持不同场景有不同媒介处理 |
| `actions` | 动作提示 | 保存可表演动作 |
| `dialogues` | 对白 | 保存角色台词 |
| `ai_added_content` | AI 新增内容 | 明确标记非原文内容 |
| `revision_suggestions` | 修改建议 | 给作者下一步打磨方向 |
| `adaptation_notes` | 场景级改编备注 | 保存局部解释和处理说明 |

## `actions`

```yaml
actions:
  - text: 林夏把信举到灯下，指尖停在“那盏灯”三个字上。
    beat: discovery
    origin: ai_adapted
```

| 字段 | 说明 |
|---|---|
| `text` | 动作内容 |
| `beat` | 动作节拍或功能，例如 `discovery`、`pause`、`conflict` |
| `origin` | 内容来源 |

设计原因：动作是小说转剧本的关键。很多小说里的心理变化不能直接照搬，需要通过可见动作、停顿、走位、道具互动来表现。

## `dialogues`

```yaml
dialogues:
  - speaker_id: char_linxia
    line: 这不是馆里的编号。
    emotion: confused
    origin: ai_adapted
```

| 字段 | 说明 |
|---|---|
| `speaker_id` | 说话角色 ID |
| `line` | 台词 |
| `emotion` | 可选情绪提示 |
| `origin` | 内容来源 |

设计原因：对白必须引用角色表中的人物，避免出现不存在的说话人。`emotion` 可以帮助演员或作者理解这句台词的表演方向。

## 校验规则

后端会对 YAML 做三层校验：

1. **YAML 解析校验**
   检查 YAML 是否能被解析，根节点是否为对象。

2. **JSON Schema / Pydantic 结构校验**
   检查必填字段、字段类型、枚举值、ID 格式、数组长度等是否符合模型定义。

3. **语义校验**
   检查跨字段关系：

   - `scene.id` 是否唯一。
   - `scene.location_id` 是否存在于 `locations`。
   - `scene.characters` 是否都存在于 `characters`。
   - `dialogue.speaker_id` 是否存在于 `characters`。
   - 每场戏是否至少有动作或对白；目前这是 warning。
   - `scenes.source_chapters` 是否覆盖至少 3 个来源章节；这是 error。

设计原因：LLM 生成文本时容易出现“字段看似完整，但引用关系错了”的问题。语义校验可以把这些问题暴露给作者和前端编辑器。

## 为什么不只保留 `scene / action / dialogue`

普通剧本结构大致只需要场景、动作、对白。但小说改编工具还必须回答：

- 这场戏来自哪几章？
- 原文内容在小说中起什么功能？
- AI 为什么把它改成这场戏？
- 哪些内容是 AI 新增？
- 这场戏有没有冲突？
- 心理描写如何外化？
- 作者下一步该怎么改？
- 拍摄或表演上有什么风险？

所以本 Schema 增加了来源追踪、改编解释、作者控制、风险提示和修改建议。这些字段会让 YAML 更长，但换来的是可解释、可校验、可返修。

## 完整示例

```yaml
metadata:
  title: 雨巷里的来信
  source_chapter_count: 3
  language: zh-CN
  genre: mystery drama
  logline: 林夏循着父亲留下的线索走进旧剧院。
adaptation_profile:
  format_type: short_drama
  adaptation_scale: balanced
  style_focus: psychological
  generation_scope: [1, 2, 3]
  preserve_items:
    - 保留林夏、周砚和父亲失踪线索
  forbidden_changes:
    - 不要改变主角继续调查父亲失踪的核心动机
  author_notes: 心理活动尽量转成动作、停顿和克制对白。
adaptation_strategy:
  - 保留原文线索链，将心理和氛围改成可见动作。
  - 每章至少生成一场戏，方便作者追踪来源。
characters:
  - id: char_linxia
    name: 林夏
    role: protagonist
    description: 谨慎但执着的档案馆工作人员。
    first_appearance_chapter: 1
locations:
  - id: loc_archive
    name: 城南档案馆
    description: 雨巷旁的旧档案馆。
props:
  - id: prop_letter
    name: 无编号信件
    description: 引导林夏前往旧剧院的关键线索。
scenes:
  - id: sc_001
    title: 雨夜档案馆的发现
    source_chapters: [1]
    source_excerpt: 林夏在城南档案馆值夜班，发现一封没有编号的信。
    source_function: 开篇设悬，引出旧剧院和父亲失踪线索。
    location_id: loc_archive
    time_of_day: night
    characters: [char_linxia]
    purpose: 建立主角和核心悬念。
    scene_purpose: 把原文的氛围和心理疑问转成可见发现。
    conflict: 林夏想确认信件来源，但信件把她拉回父亲失踪事件。
    emotional_shift: 从疲惫麻木到警觉和主动追查。
    adaptation_reason: 信件发现需要成为第一场的行动触发点。
    performance_notes: 雨声、纸张摩擦和停顿可以外化林夏的不安。
    risk_note: 避免只用旁白解释信件含义。
    production_risk: 档案馆氛围不能太静，需要用声音和动作维持张力。
    format_type: short_drama
    actions:
      - text: 林夏把信举到灯下，指尖停在“那盏灯”三个字上。
        beat: discovery
        origin: ai_adapted
    dialogues:
      - speaker_id: char_linxia
        line: 这不是馆里的编号。
        emotion: confused
        origin: ai_adapted
    ai_added_content:
      - 增加短暂停顿，用动作外化疑虑。
    revision_suggestions:
      - 如果开场仍然偏静，可以增加一个外部打扰。
    adaptation_notes:
      - 将原文氛围压缩为雨声、灯光和信件特写。
adaptation_notes:
  - 本稿优先保留前三章线索链，后续可继续扩展章节范围。
```

## 后续扩展方向

当前 Schema 已经支持剧本初稿、来源追踪和返修。未来可以扩展：

- `evidence`：独立保存证据链，让场景引用证据 ID，而不是只保存 `source_excerpt`。
- `versions`：保存多轮返修版本，支持对比。
- `beats`：细化成更小的节拍结构。
- `production_breakdown`：生成演员、地点、道具和拍摄需求清单。
- `localized_formats`：针对短剧、舞台剧、广播剧、游戏脚本扩展专属字段。

这些扩展没有放进当前 MVP，是为了保持导出结构可读、可验证，并适合作者在前端继续编辑。
