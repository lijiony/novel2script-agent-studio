import Link from "next/link";

const heroSteps = ["先读懂小说", "作者确认", "逐章改编", "合成 YAML 初稿"];

const journeySteps = [
  {
    title: "带着前三章",
    text: "粘贴或上传 3 章以上正文，先让系统按章节拆开故事。",
    tag: "输入",
  },
  {
    title: "AI 章节理解",
    text: "每章生成摘要、人物、线索、冲突和改编机会，先证明它读懂了。",
    tag: "理解",
  },
  {
    title: "作者确认 / 重读",
    text: "确认读对了再继续，不对就讨论、修改理解，或让 AI 重新理解这一章。",
    tag: "确认",
  },
  {
    title: "生成改编计划",
    text: "整理主线、人物关系、伏笔和改编风险，先给出副编剧方案。",
    tag: "计划",
  },
  {
    title: "选择改编方向",
    text: "剧本类型、改编尺度、风格偏向、保留内容和禁止改动都由作者决定。",
    tag: "控制",
  },
  {
    title: "逐章剧本卡",
    text: "先生成每章剧本卡，作者逐章看场景、对白、冲突和结尾钩子。",
    tag: "剧本卡",
  },
  {
    title: "连贯性合成",
    text: "处理章节过渡、人物动机、线索回收和节奏推进，再合成完整初稿。",
    tag: "合成",
  },
  {
    title: "导出 YAML",
    text: "得到结构化剧本、改编报告和连贯性报告，方便继续打磨。",
    tag: "产物",
  },
  {
    title: "最终返修",
    text: "不满意可以只修连贯性，也可以定位到某章剧本卡重新改。",
    tag: "返修",
  },
];

const trustCards = [
  {
    title: "AI 先说明它读到了什么",
    text: "章节理解卡把事件、人物、地点、线索和情绪变化摊开，作者先验收理解质量。",
  },
  {
    title: "作者决定改编方向",
    text: "短剧、影视、舞台剧、广播剧等方向可以选择，忠实或大胆也不交给 AI 自己猜。",
  },
  {
    title: "不满意可以局部返修",
    text: "最终稿不满意时，不必推倒重来，可以回到连贯性合成或某一章剧本卡。",
  },
];

const artifactItems = [
  "章节理解卡",
  "Story Bible",
  "改编计划",
  "逐章剧本卡",
  "YAML 剧本",
  "改编报告",
  "连贯性报告",
];

const schemaReasons = [
  "方便作者定位到某场戏、某句对白、某条线索继续修改。",
  "方便检查人物、场景、伏笔和情绪推进有没有前后打架。",
  "方便后续导出、校验、下载，或交给别的创作工具继续加工。",
];

const workspaceColumns = [
  {
    title: "左边找任务",
    text: "新建改编、切换任务、查看当前状态和产物入口。",
  },
  {
    title: "中间推进创作",
    text: "输入小说、确认章节理解、选择改编方向、审核剧本卡。",
  },
  {
    title: "右边看上下文",
    text: "只在需要时打开章节讨论、YAML、报告和下载列表。",
  },
];

export default function LandingPage() {
  return (
    <main className="landing-page">
      <section className="landing-hero" id="top">
        <nav className="landing-nav" aria-label="产品导航">
          <Link className="landing-brand" href="#top">
            Novel2Script
          </Link>
          <div className="landing-nav-links">
            <Link href="#journey">改编旅程</Link>
            <Link href="#artifact">可打磨产物</Link>
            <Link href="#schema">Schema</Link>
            <Link className="landing-nav-cta" href="/workbench">
              进入工作台
            </Link>
          </div>
        </nav>

        <div className="hero-stage">
          <div className="hero-copy">
            <span className="hero-kicker">AI 改编副编剧工作台</span>
            <h1>把长篇小说改成可继续打磨的剧本初稿</h1>
            <p>
              粘贴 3 章以上小说，AI 会先理解剧情、人物和线索，再让作者确认方向，
              逐章生成剧本卡，最终合成可审计、可修改的 YAML 剧本初稿。
            </p>
            <div className="hero-actions">
              <Link className="primary-link" href="/workbench">
                开始改编
              </Link>
              <Link className="secondary-link" href="#journey">
                查看改编旅程
              </Link>
            </div>
            <div className="hero-facts" aria-label="核心能力">
              {heroSteps.map((step) => (
                <span key={step}>{step}</span>
              ))}
            </div>
          </div>

          <div className="hero-workbench-card" aria-label="工作台预览">
            <div className="preview-sidebar">
              <strong>当前改编</strong>
              <span>章节确认</span>
              <span>作者方向</span>
              <span>YAML 打磨</span>
            </div>
            <div className="preview-main">
              <span>AI 正在说明它读到了什么</span>
              <strong>第 1 章理解卡</strong>
              <p>关键事件、人物关系、线索和改编机会会先摊开给作者确认。</p>
              <div>
                <em>通过</em>
                <em>讨论修改</em>
                <em>重新理解</em>
              </div>
            </div>
            <div className="preview-panel">
              <span>上下文</span>
              <strong>YAML / 报告</strong>
              <p>只在需要时打开，不打断主创作流。</p>
            </div>
          </div>
        </div>

        <div className="hero-flow-preview" aria-label="流程预览">
          {heroSteps.map((step, index) => (
            <div key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section journey-section" id="journey">
        <div className="section-head">
          <span className="section-kicker">改编旅程</span>
          <h2>不是一键黑箱生成，而是一路确认、一路改。</h2>
          <p>
            作者每一步都知道 AI 在做什么，也能在关键节点停下来确认、讨论、重写或返修。
          </p>
        </div>
        <div className="journey-track" aria-label="小说改编旅程">
          {journeySteps.map((step, index) => (
            <article key={step.title} className={index % 2 === 0 ? "is-high" : "is-low"}>
              <span className="journey-node">{String(index + 1).padStart(2, "0")}</span>
              <small>{step.tag}</small>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section trust-section">
        <div className="section-head">
          <span className="section-kicker">不是黑箱生成</span>
          <h2>AI 是副编剧，作者仍然掌握故事方向。</h2>
        </div>
        <div className="trust-grid">
          {trustCards.map((card) => (
            <article key={card.title}>
              <h3>{card.title}</h3>
              <p>{card.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section artifact-section" id="artifact">
        <div className="artifact-copy">
          <span className="section-kicker">可审计、可塑形</span>
          <h2>交付的不只是一段文本，而是一套能继续打磨的改编档案。</h2>
          <p>
            从章节理解到最终 YAML，每个中间产物都能帮助作者看见“它为什么这样改”，
            也能帮助后续继续修人物、改场景、调节奏。
          </p>
          <div className="artifact-tags" aria-label="改编产物">
            {artifactItems.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        </div>

        <div className="schema-card" id="schema">
          <span className="section-kicker">为什么用结构化 Schema</span>
          <h3>它让剧本初稿更容易被检查、修改和继续加工。</h3>
          <ul>
            {schemaReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <pre className="yaml-preview" aria-label="YAML Schema 片段">
{`script:
  scenes:
    - id: sc_001
      source_chapters: [1]
      location: 城南档案馆
      characters: [林夏]
      conflict: 无编号的信打破夜班秩序
      beats:
        - type: action
          text: 林夏停下整理资料的手。
          origin: source_adapted
      continuity:
        carries: [无编号的信]`}
          </pre>
        </div>
      </section>

      <section className="landing-section workspace-section">
        <div className="section-head">
          <span className="section-kicker">工作台怎么用</span>
          <h2>任务、流程和产物分开，作者不会在一堆卡片里迷路。</h2>
        </div>
        <div className="workspace-map">
          {workspaceColumns.map((column) => (
            <article key={column.title}>
              <h3>{column.title}</h3>
              <p>{column.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section example-section" id="example">
        <div className="section-head">
          <span className="section-kicker">生成示例</span>
          <h2>从小说段落，到可编辑剧本初稿。</h2>
        </div>
        <div className="example-grid">
          <article>
            <span>小说片段</span>
            <p>
              林夏在城南档案馆值夜班。傍晚的雨落在窄巷里，像有人把旧照片一张张翻过。
              她整理一箱无人认领的资料时，看见一封没有编号的信。
            </p>
          </article>
          <article>
            <span>剧本处理</span>
            <p>
              AI 将环境叙述拆成可表演动作，把“旧照片般的雨巷”转成场景氛围，
              同时保留“无编号的信”作为悬疑钩子。
            </p>
          </article>
        </div>
      </section>

      <section className="landing-cta">
        <span>带着你的前三章，开始生成第一版剧本</span>
        <h2>先让 AI 读懂故事，再由你决定怎么改。</h2>
        <Link className="primary-link" href="/workbench">
          进入创作工作台
        </Link>
      </section>
    </main>
  );
}
