# -*- coding: utf-8 -*-
"""生成界面 01–09 的 HTML 原型（S5）。运行后在 _src/ 下产出 界面NN.html，
再用 Edge 无头截图到 exp2/UI界面/界面NN.png（2880×1800，device-scale-factor=2）。

约定：
- 每张页面右下角 stamp 标出「模块 · REQ · 界面号」，报告里的映射表直接引它；
- 状态色与设计基线 01 §2 的六状态一一对应（待确认琥珀、已确认蓝、已入住绿、
  已退房灰、已取消紫、未入住红）；
- 库存三值一律写「可售 / 已占用 / 余量」，与 03 §5 口径一致。
"""
import pathlib

OUT = pathlib.Path(__file__).parent

NAV = [
    ("顾客端", [("01", "登录 / 注册", "界面01"), ("02", "搜索酒店", "界面02"),
             ("07", "我的订单", "界面07")]),
    ("酒店端", [("10", "酒店工作台", "界面10"), ("11", "库存日历", "界面11"),
             ("12", "价格与停售", "界面12"), ("13", "入住与退房", "界面13"),
             ("16", "统计报表", "界面16")]),
    ("平台管理", [("14", "入驻审核", "界面14"), ("15", "节假日字典", "界面15"),
              ("17", "审计日志", "界面17"),
              ("19", "用户与角色", "界面19 可选"), ("20", "运维与对账", "界面20 可选")]),
]


def shell(active: str, crumb: str, title: str, sub: str, body: str, stamp: str,
          bare: bool = False) -> str:
    nav_html = []
    for group, items in NAV:
        nav_html.append(f'<div class="nav-group"><div class="nav-title">{group}</div>')
        for num, name, page in items:
            cls = "nav-item on" if num == active else "nav-item"
            nav_html.append(
                f'<div class="{cls}"><span class="dot"></span>{name}'
                f'<span class="tag">{page}</span></div>')
        nav_html.append("</div>")

    head = "" if bare else f"""
      <div class="page-head">
        <div>
          <h1>{title}</h1>
          <p>{sub}</p>
        </div>
      </div>"""
    content_cls = "content bare" if bare else "content"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title} · 云栖酒店预订</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark">云</div>
      <div>
        <div class="brand-name">云栖酒店预订</div>
        <div class="brand-sub">软工实验二 · 设计原型</div>
      </div>
    </div>
    {''.join(nav_html)}
    <div class="sidebar-foot">
      顾客 · 酒店工作人员 · 平台管理员<br>
      三端同一套账号体系（M1 统一鉴权）<br>
      <span style="color:#6C82A1">界面19/20 为可选项；M10 不做独立界面，运维与对账走配置项与告警通道</span>
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <div class="crumb">{crumb}</div>
      <div class="spacer"></div>
      <div class="search-mini">⌕ 搜索订单号 / 酒店名</div>
      <div class="user"><span class="avatar">陈</span>陈一帆 · 顾客</div>
    </header>

    <section class="{content_cls}">{head}
      {body}
    </section>

    <footer class="stamp">
      <span>云栖酒店预订系统 · UI 原型 v1.0（2026-11-12）</span>
      <span class="r">{stamp}</span>
    </footer>
  </main>
</div>
</body>
</html>
"""


# ---------------- 界面01 登录 / 注册（M1） ----------------
def page01() -> str:
    body = """
<div class="login">
  <div class="login-left">
    <div class="row">
      <div class="brand-mark" style="width:40px;height:40px;font-size:17px;">云</div>
      <div>
        <div style="font-size:15px;font-weight:650;">云栖酒店预订</div>
        <div style="font-size:11.5px;color:#9DB6D8;">多城市 · 多门店 · 一套账号</div>
      </div>
    </div>
    <h1>把「查得到、订得下、<br>改得了」做扎实</h1>
    <p>实时余量按「房型 × 日期」维护，下单在同一个事务里占房——
       不会出现「页面显示有房、点下单却没房」。</p>
    <div class="login-points">
      <div class="login-point"><span class="n">1</span><div><b>六种订单状态，转换只有 8 条边</b><br>
        每一步都能说清是谁触发的、失败返回什么。</div></div>
      <div class="login-point"><span class="n">2</span><div><b>价格按日固化</b><br>
        下单那一刻的每晚单价写进订单快照，之后改价不影响已下的单。</div></div>
      <div class="login-point"><span class="n">3</span><div><b>越权返回 403，不是静默失败</b><br>
        顾客看不到别家的库存与订单，酒店只动自己的房型。</div></div>
    </div>
  </div>

  <div class="login-right">
    <h2>欢迎回来</h2>
    <div class="lead">用手机号登录；没有账号时同一表单直接注册。</div>

    <div class="seg">
      <div class="s on">登录</div>
      <div class="s">注册</div>
    </div>

    <div class="field mt8">
      <div class="label">手机号</div>
      <div class="input"><span>+86</span><span style="color:#D0D5DD;">|</span><span>138 0013 8000</span></div>
    </div>

    <div class="field mt16">
      <div class="label">密码</div>
      <div class="input"><span style="letter-spacing:2px;">••••••••</span>
        <span style="margin-left:auto;font-size:12.5px;color:#2F6FED;">显示</span></div>
      <div class="hint">密码加盐哈希存储；连续 5 次失败锁定 10 分钟。</div>
    </div>

    <div class="field mt16">
      <div class="label">图形验证码</div>
      <div class="row">
        <div class="input" style="flex:1;"><span class="ph">请输入右侧 4 位字符</span></div>
        <div class="thumb" style="width:104px;height:40px;display:grid;place-items:center;
             font-size:17px;letter-spacing:4px;color:#1B4FBF;font-weight:700;">7K3Q</div>
      </div>
      <div class="hint" style="color:#B42318;">验证码已过期，请点击图形刷新（E-01 输入类错误：就地提示，不清空已填内容）</div>
    </div>

    <div class="row mt16" style="justify-content:space-between;">
      <div class="row" style="font-size:12.5px;color:#344054;">
        <span class="box on"></span> 记住这台设备
      </div>
      <div style="font-size:12.5px;color:#2F6FED;">忘记密码？</div>
    </div>

    <div class="btn primary mt20" style="height:44px;justify-content:center;font-size:14px;">登录</div>

    <div class="alert a-info mt16">
      <span class="ic">i</span>
      <div>权限按角色判定：顾客只能看自己的订单；酒店工作人员只在本店范围内操作；
        平台管理员可查审计日志但不能改业务数据。越权请求返回 <b>403</b> 并提示「无权访问该资源」，
        不是静默失败。</div>
    </div>
  </div>
</div>
"""
    return shell("01", "顾客端 / 登录", "登录 / 注册", "同一表单，登录与注册切换；三种角色共用一套账号体系",
                 body, "M1 账号与权限 · REQ-026、REQ-020 · 界面01", bare=True)


# ---------------- 界面02 搜索首页（M4） ----------------
def page02() -> str:
    cards = ""
    data = [
        ("云栖·外滩江景酒店", "上海 · 外滩", "4.8 分 · 2186 条评价", "高级江景大床房", 880, "仅剩 2 间"),
        ("云栖·西湖山居", "杭州 · 西湖", "4.7 分 · 1543 条评价", "山景双床房", 620, "余 6 间"),
        ("云栖·鼓浪屿海景", "厦门 · 鼓浪屿", "4.6 分 · 987 条评价", "亲子家庭房", 540, "余 9 间"),
    ]
    for nm, loc, rate, room, price, left in data:
        cards += f"""
      <div class="card hotel-card">
        <div class="pic thumb"></div>
        <div class="bd">
          <div class="nm">{nm}</div>
          <div class="meta"><span>{loc}</span><span>{rate}</span></div>
          <div class="row wrap">
            <span class="pill">{room}</span>
            <span class="pill blue">{left}</span>
          </div>
          <div class="foot">
            <div><span class="price">¥{price}</span><small> / 晚起</small></div>
            <div class="btn sm">查看房型</div>
          </div>
        </div>
      </div>"""

    body = f"""
<div class="hero">
  <h2>今天想住哪儿？</h2>
  <p>按城市、日期、人数、价格筛选；余量按「房型 × 日期」实时计算，展示与下单同一口径。</p>
  <div class="searchbar">
    <div class="sb-cell"><div class="k">目的地 / 酒店名</div><div class="v">上海</div></div>
    <div class="sb-cell"><div class="k">入住</div><div class="v">11-15 周六</div></div>
    <div class="sb-cell"><div class="k">退房</div><div class="v">11-17 周一</div></div>
    <div class="sb-cell"><div class="k">房间 / 人数</div><div class="v">1 间 · 2 人</div></div>
    <div class="btn primary" style="height:46px;padding:0 22px;">搜索</div>
  </div>
  <div class="chips">
    <span class="chip">热门：上海 · 外滩</span>
    <span class="chip">杭州 · 西湖</span>
    <span class="chip">厦门 · 鼓浪屿</span>
    <span class="chip">成都 · 春熙路</span>
    <span class="chip">广州 · 珠江新城</span>
  </div>
</div>

<div class="row mt20" style="justify-content:space-between;">
  <div style="font-size:15px;font-weight:650;">为你推荐（上海 · 11-15 至 11-17）</div>
  <div class="muted">共 42 家 · 按推荐排序</div>
</div>
<div class="hotel-grid">{cards}
</div>

<div class="alert a-warn mt16">
  <span class="ic">!</span>
  <div>日期校验：退房日期必须晚于入住日期，且不能早于今天；选错时输入框下方就地提示
    「退房日期需晚于入住日期」，不弹窗、不清空已选。跨年、跨月都按自然日计算。</div>
</div>
"""
    return shell("02", "顾客端 / 搜索", "搜索酒店", "城市 + 日期 + 人数 + 价格的组合查询入口",
                 body, "M4 搜索与展示 · REQ-001 · 界面02")


# ---------------- 界面03 搜索结果列表（M4） ----------------
def page03() -> str:
    def result(nm, loc, rate, price, rooms, tag=""):
        lines = ""
        for rn, bed, cnt, pr, left, hot in rooms:
            left_cls = "b-pending" if hot else "b-checkin"
            lines += f"""
        <div class="roomline">
          <span class="nm2">{rn}</span>
          <span>{bed}</span>
          <span>可住 {cnt} 人</span>
          <div class="rt">
            <span class="badge {left_cls}"><span class="d"></span>{left}</span>
            <span class="price" style="font-size:15px;">¥{pr}</span>
            <span class="btn sm primary">预订</span>
          </div>
        </div>"""
        return f"""
      <div class="result">
        <div class="pic thumb"></div>
        <div class="bd">
          <div class="row" style="justify-content:space-between;">
            <div>
              <div class="nm">{nm}</div>
              <div class="meta mt8" style="font-size:12px;color:#667085;display:flex;gap:12px;">
                <span>{loc}</span><span>{rate}</span><span>免费取消（入住前 48h）</span>
              </div>
            </div>
            <div style="text-align:right;">
              <div class="price">¥{price}<small> / 晚起</small></div>
              <div class="hint">{tag}</div>
            </div>
          </div>
          {lines}
        </div>
      </div>"""

    body = f"""
<div class="list-wrap">
  <div class="card filters">
    <h3>筛选</h3>
    <div class="fgroup">
      <div class="label">价格（每晚）</div>
      <div class="row mt8" style="gap:6px;">
        <div class="input" style="height:32px;flex:1;font-size:12.5px;">¥300</div>
        <span class="muted">—</span>
        <div class="input" style="height:32px;flex:1;font-size:12.5px;">¥1200</div>
      </div>
    </div>
    <div class="fgroup">
      <div class="label">星级</div>
      <div class="fopt"><span class="box on"></span> 五星 / 豪华</div>
      <div class="fopt"><span class="box on"></span> 四星 / 高档</div>
      <div class="fopt"><span class="box"></span> 三星 / 舒适</div>
    </div>
    <div class="fgroup">
      <div class="label">房型</div>
      <div class="fopt"><span class="box on"></span> 大床房</div>
      <div class="fopt"><span class="box on"></span> 双床房</div>
      <div class="fopt"><span class="box"></span> 家庭房</div>
    </div>
    <div class="fgroup">
      <div class="label">设施</div>
      <div class="fopt"><span class="box on"></span> 免费停车</div>
      <div class="fopt"><span class="box"></span> 含早餐</div>
      <div class="fopt"><span class="box"></span> 可加床</div>
    </div>
  </div>

  <div>
    <div class="card" style="padding:12px 16px;">
      <div class="row" style="justify-content:space-between;">
        <div class="muted">上海 · 11-15 至 11-17 · 1 间 · 2 人，共 <b style="color:#101828;">42</b> 家符合条件</div>
        <div class="row" style="gap:6px;font-size:12.5px;">
          <span class="pill blue">推荐排序</span><span class="pill">价格从低到高</span><span class="pill">评分优先</span>
        </div>
      </div>
    </div>

    <div class="card mt12">
      {result("云栖·外滩江景酒店", "上海 · 外滩 · 距地铁 2 号口 380m", "4.8 分 · 2186 条评价", 880,
              [("高级江景大床房", "1.8m 大床", 2, 880, "仅剩 2 间", True),
               ("豪华双床房", "1.2m 双床", 2, 960, "余 5 间", False)], "含双早 · 可免费取消")}
      {result("云栖·静安商务酒店", "上海 · 静安寺 · 近南京西路", "4.6 分 · 1320 条评价", 720,
              [("商务大床房", "1.8m 大床", 2, 720, "余 8 间", False),
               ("行政套房", "2.0m 大床 + 沙发床", 3, 1180, "余 3 间", False)], "含单早")}
      {result("云栖·虹桥枢纽酒店", "上海 · 虹桥 · 距 T2 航站楼 1.2km", "4.5 分 · 806 条评价", 560,
              [("标准双床房", "1.2m 双床", 2, 560, "余 12 间", False)], "24h 接送机")}
    </div>

    <div class="alert a-warn mt12">
      <span class="ic">!</span>
      <div><b>没房了（空态）</b>：11-15 至 11-17 已无房。换一天或换一家，两个按钮直接改日期，
        刚选的价格区间和星级都留着，不用重选。
        <b>加载失败（错误态）</b>才是红条「加载失败，点击重试」，已填的条件一样原样保留——两者不要混为一谈。
        单日余量不够不算空态：酒店照常出现在列表里，只在房型行写「该日余量不足」并禁用「预订」。</div>
    </div>
  </div>
</div>
"""
    return shell("03", "顾客端 / 搜索 / 结果", "搜索结果", "筛选 + 排序结果；每行房型显示余量与每晚价",
                 body, "M4 搜索与展示 · REQ-001 / REQ-004 · 界面03")


# ---------------- 界面04 酒店详情（M2/M4） ----------------
def page04() -> str:
    rows = ""
    for rn, bed, cnt, price, avail, occ, left, state in [
        ("高级江景大床房", "1.8m 大床", 2, 880, 12, 10, 2, "仅剩 2 间"),
        ("豪华双床房", "1.2m 双床", 2, 960, 15, 10, 5, "余 5 间"),
        ("行政套房", "2.0m 大床", 3, 1580, 4, 4, 0, "已订满"),
    ]:
        btn = ('<span class="btn sm primary">预订</span>' if left > 0
               else '<span class="btn sm" disabled>已订满</span>')
        left_cls = "b-noshow" if left == 0 else ("b-pending" if left <= 2 else "b-checkin")
        rows += f"""
      <tr>
        <td class="strong">{rn}</td><td>{bed}</td><td>可住 {cnt} 人</td>
        <td class="num">¥{price}</td>
        <td class="num">可售 {avail} / 已占用 {occ} / <b style="color:#101828">余量 {left}</b></td>
        <td><span class="badge {left_cls}"><span class="d"></span>{state}</span></td>
        <td style="text-align:right;">{btn}</td>
      </tr>"""

    body = f"""
<div class="row mt8" style="align-items:flex-start;gap:18px;">
  <div style="flex:1;">
    <div class="row" style="justify-content:space-between;">
      <div>
        <div style="font-size:21px;font-weight:700;">云栖·外滩江景酒店</div>
        <div class="meta mt8" style="font-size:12.5px;color:#667085;display:flex;gap:12px;">
          <span>上海 · 黄浦区中山东一路 18 号</span><span>4.8 分 · 2186 条评价</span>
          <span>五星 / 豪华</span><span>2019 年开业 · 2023 年翻新</span>
        </div>
      </div>
      <div class="row" style="gap:8px;">
        <span class="btn sm">收藏</span><span class="btn sm">分享</span>
      </div>
    </div>

    <div class="gallery mt16">
      <div class="g1 thumb"></div><div class="thumb"></div><div class="thumb"></div>
    </div>
  </div>
</div>

<div class="detail-grid mt16">
  <div class="card">
    <div class="card-head"><h2>房型与今日余量</h2>
      <span class="sub">2026-11-15 入住 · 11-17 退房（2 晚）</span>
      <span class="spacer" style="flex:1;"></span>
      <span class="hint">余量 = 可售 − 已占用（03 §5 口径）</span>
    </div>
    <table class="grid">
      <thead><tr><th>房型</th><th>床型</th><th>可住</th><th>每晚</th>
        <th>库存（可售 / 已占用 / 余量）</th><th>状态</th><th></th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <div style="padding:12px 16px;border-top:1px solid #F2F4F7;">
      <div class="alert a-info">
        <span class="ic">i</span>
        <div>两晚价格可能不同：11-15（周六）¥880、11-16（周日）¥820，下单时按「每晚单价 × 间数」逐晚写进订单快照，
          总价 = Σ（单价 × 间数），之后改价不影响已下的单。</div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-head"><h2>政策与提示</h2></div>
    <div class="card-body policy">
      <ul style="margin:0;padding-left:18px;">
        <li><b>取消政策</b>：入住前 48 小时（11-13 14:00 前）免费取消；之后取消收取首晚房费。</li>
        <li><b>不可取消区间</b>：11-14 至 11-16 为展会期间，该时段部分房型不可取消（房型行会标「不可取消」）。</li>
        <li><b>到店时间</b>：14:00 后入住，12:00 前退房；凌晨到店请备注。</li>
        <li><b>确认时限</b>：提交后 30 分钟内酒店需确认，超时系统自动取消并释放房间。</li>
      </ul>
      <div class="alert a-warn mt12">
        <span class="ic">!</span>
        <div>房型「行政套房」当前<b>停售</b>（临时封房），页面写「暂停销售」而不是「已订满」。</div>
      </div>
      <div class="alert a-danger mt10">
        <span class="ic">×</span>
        <div>下单瞬间最后一间被订走 → 返回「手慢了，最后一间已被订走」并回显余量 0，不进入待确认。</div>
      </div>
    </div>
  </div>
</div>
"""
    return shell("02", "顾客端 / 搜索 / 酒店详情", "酒店详情",
                 "房型、逐日价格、库存三值与取消政策；库存三值直接对应 03 §5 口径",
                 body, "M2 酒店与房型 / M4 搜索与展示 · REQ-001 / REQ-004 · 界面04")


# ---------------- 界面05 预订确认（M5） ----------------
def page05() -> str:
    body = """
<div class="confirm-grid">
  <div>
    <div class="card">
      <div class="card-head"><h2>入住信息</h2><span class="sub">带 * 为必填</span></div>
      <div class="card-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
          <div class="field"><div class="label">入住人姓名 *</div><div class="input">陈一帆</div></div>
          <div class="field"><div class="label">手机号 *</div><div class="input">138 0013 8000</div>
            <div class="hint">用于接收入住凭证与取消通知</div></div>
          <div class="field"><div class="label">预计到店时间</div><div class="input">18:00 - 20:00 ▾</div></div>
          <div class="field"><div class="label">房间数 *</div><div class="input">1 间 ▾</div>
            <div class="hint">最多可订 3 间（同一房型单次预订上限）</div></div>
        </div>
        <div class="field mt16"><div class="label">特殊要求（选填）</div>
          <div class="input" style="height:64px;align-items:flex-start;padding-top:10px;color:#98A2B3;">
            如需高楼层、无烟房、婴儿床，请在此说明（酒店尽量安排，不保证）</div></div>
        <div class="field mt16"><div class="label">发票</div>
          <div class="row" style="gap:8px;">
            <span class="pill blue">不需要</span><span class="pill">电子普通发票</span><span class="pill">专用发票</span>
          </div>
        </div>
        <div class="alert a-warn mt16"><span class="ic">!</span>
          <div><b>重复提交保护</b>：本页生成一个隐藏幂等键 —— 连点两次或网络重试，第二次直接返回首单，
            不会出两张。同一时段（同顾客 + 同酒店 + 同房型 + 日期重叠）已有有效单时拒绝，
            提示「你在这个时段已有一张有效订单」。</div>
        </div>
      </div>
    </div>

    <div class="card mt16">
      <div class="card-head"><h2>逐晚价格明细</h2><span class="sub">下单即固化，后续改价不影响本单</span></div>
      <table class="grid">
        <thead><tr><th>日期</th><th>房型</th><th>间数</th><th>每晚单价</th><th>小计</th></tr></thead>
        <tbody>
          <tr><td class="strong">11-15 周六</td><td>高级江景大床房</td><td class="num">1</td>
            <td class="num">¥880</td><td class="num strong">¥880</td></tr>
          <tr><td class="strong">11-16 周日</td><td>高级江景大床房</td><td class="num">1</td>
            <td class="num">¥820</td><td class="num strong">¥820</td></tr>
        </tbody>
      </table>
      <div class="card-body" style="padding-top:12px;">
        <div class="hint">逐晚单价写入 <code>booking_night</code>（订单号 + 日期 联合唯一），
          总价 = Σ（单价 × 间数）= 1700 元。</div>
      </div>
    </div>
  </div>

  <div class="card summary">
    <div class="card-head"><h2>订单摘要</h2></div>
    <div class="card-body">
      <div class="row" style="gap:12px;">
        <div class="thumb" style="width:88px;height:66px;flex:0 0 88px;"></div>
        <div>
          <div style="font-size:13.5px;font-weight:650;">云栖·外滩江景酒店</div>
          <div class="hint mt8">高级江景大床房 · 1 间</div>
          <div class="hint">11-15 至 11-17 · 2 晚</div>
        </div>
      </div>

      <div class="mt16">
        <div class="row" style="justify-content:space-between;font-size:13px;color:#344054;">
          <span>房费（2 晚 × 1 间）</span><span>¥1700</span>
        </div>
        <div class="row mt8" style="justify-content:space-between;font-size:13px;color:#344054;">
          <span>服务费</span><span>¥0</span>
        </div>
        <div class="row mt8" style="justify-content:space-between;font-size:13px;color:#344054;">
          <span>优惠</span><span style="color:#067647;">- ¥50</span>
        </div>
        <div class="row mt12" style="justify-content:space-between;border-top:1px solid #E4E7EC;padding-top:12px;">
          <span style="font-weight:650;">应付总额</span>
          <span class="price" style="font-size:20px;">¥1650</span>
        </div>
      </div>

      <div class="countdown">
        提交后酒店需在 <b>30 分钟</b> 内确认；超时未确认，系统自动取消并释放房间（T3）。
        取消政策：入住前 48 小时免费取消。
      </div>

      <div class="btn primary" style="height:44px;justify-content:center;font-size:14.5px;">提交预订</div>
      <div class="hint mt8" style="text-align:center;">提交即表示同意《预订条款》与《取消政策》</div>

      <div class="alert a-info mt16"><span class="ic">i</span>
        <div>全站库存口径只有一套：<b>可售</b>（酒店挂牌） − <b>已占用</b>（有效订单） = <b>余量</b>；
          下单只加「已占用」，不动「可售」。</div>
      </div>
    </div>
  </div>
</div>
"""
    return shell("07", "顾客端 / 预订 / 确认", "预订确认",
                 "填写入住信息、核对逐晚价格后提交；提交即触发「校验 + 占用 + 建单 + 幂等键」同一事务",
                 body, "M5 预订与订单 · REQ-005 / REQ-006 · 界面05")


# ---------------- 界面06 提交结果（M5） ----------------
def page06() -> str:
    body = """
<div class="card done">
  <div class="tick">✓</div>
  <h2>预订已提交，等待酒店确认</h2>
  <div class="ono mt8">订单号 <b>HT20261112000318</b></div>
  <div class="row mt12" style="justify-content:center;gap:10px;">
    <span class="badge b-pending"><span class="d"></span>待确认</span>
    <span class="muted">云栖·外滩江景酒店 · 高级江景大床房 · 11-15 至 11-17</span>
  </div>

  <div class="timer">酒店确认剩余时间 <b>29:41</b></div>
  <div class="hint">超时未确认将自动取消并释放房间，你会收到一条站内与短信通知。</div>

  <div class="row mt20" style="justify-content:center;gap:10px;">
    <span class="btn primary">查看订单详情</span>
    <span class="btn">继续浏览</span>
    <span class="btn ghost">联系酒店</span>
  </div>

  <div class="mt20" style="text-align:left;">
    <div class="alert a-info"><span class="ic">i</span>
      <div><b>关于重复提交</b>：如果刚才网络卡顿你点了两次，这里显示的仍是<b>同一张订单</b>——
        幂等键在同一个事务里与订单一起写入，第二次请求命中键值后直接返回原单号，不会多扣房间。</div>
    </div>
    <div class="alert a-warn mt12"><span class="ic">!</span>
      <div><b>提交失败长什么样</b>：库存被别人抢走时，本页不会出现，
        而是回到确认页顶部显示红色提示「手慢了，最后一间已被订走（当前余量 0）」，并保留你填的入住信息。</div>
    </div>
  </div>
</div>

<div class="card mt16">
  <div class="card-head"><h2>你可能还关心</h2></div>
  <div class="card-body">
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;">
      <div class="card" style="box-shadow:none;"><div class="card-body">
        <div class="label">什么时候能确认？</div>
        <div class="hint mt8">酒店在 30 分钟内确认；确认后状态变为「已确认」，你会在订单列表看到蓝色状态标。</div>
      </div></div>
      <div class="card" style="box-shadow:none;"><div class="card-body">
        <div class="label">现在能改期吗？</div>
        <div class="hint mt8">可以。已确认订单可改期一次：先占新日期再放旧日期，新日期余量不足则整单不变。</div>
      </div></div>
      <div class="card" style="box-shadow:none;"><div class="card-body">
        <div class="label">能取消吗？</div>
        <div class="hint mt8">入住前 48 小时免费取消；展会等不可取消区间按房型政策执行，取消前会显示退款金额。</div>
      </div></div>
    </div>
  </div>
</div>
"""
    return shell("07", "顾客端 / 预订 / 结果", "提交结果",
                 "成功进入「待确认」并给出确认倒计时；重复提交返回同一订单号",
                 body, "M5 预订与订单 · REQ-005 / REQ-014 · 界面06")


# ---------------- 界面07 订单列表（M5） ----------------
def page07() -> str:
    rows = [
        ("HT20261112000318", "云栖·外滩江景酒店", "高级江景大床房", "11-15 → 11-17", 1, "¥1650", "待确认", "b-pending",
         "取消订单"),
        ("HT20261108000192", "云栖·西湖山居", "山景双床房", "11-20 → 11-22", 2, "¥2480", "已确认", "b-confirmed",
         "改期 / 取消"),
        ("HT20261026000087", "云栖·鼓浪屿海景", "亲子家庭房", "10-30 → 11-02", 1, "¥1620", "已入住", "b-checkin",
         "查看凭证"),
        ("HT20261019000041", "云栖·静安商务酒店", "商务大床房", "10-22 → 10-23", 1, "¥720", "已退房", "b-checkout",
         "再次预订"),
        ("HT20261003000012", "云栖·虹桥枢纽酒店", "标准双床房", "10-05 → 10-06", 1, "¥560", "已取消", "b-cancel",
         "查看退款"),
    ]
    trs = ""
    for no, hotel, room, span, cnt, amt, st, cls, ops in rows:
        trs += f"""
      <tr>
        <td class="strong">{no}</td>
        <td>{hotel}<div class="hint">{room}</div></td>
        <td>{span}<div class="hint">{cnt} 间</div></td>
        <td class="num strong">{amt}</td>
        <td><span class="badge {cls}"><span class="d"></span>{st}</span></td>
        <td style="text-align:right;">
          <span class="btn sm">详情</span>
          <span class="btn sm">{ops}</span>
        </td>
      </tr>"""

    body = f"""
<div class="card">
  <div class="tabs" style="padding:0 6px;">
    <div class="tab on">全部 <span class="muted">(5)</span></div>
    <div class="tab">待确认 <span class="muted">(1)</span></div>
    <div class="tab">已确认 <span class="muted">(1)</span></div>
    <div class="tab">已入住 <span class="muted">(1)</span></div>
    <div class="tab">历史订单 <span class="muted">(2)</span></div>
    <div style="flex:1;"></div>
    <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;">
      <div class="search-mini" style="width:200px;height:32px;">⌕ 订单号 / 酒店名</div>
      <span class="btn sm">导出</span>
    </div>
  </div>
  <table class="grid">
    <thead><tr><th>订单号</th><th>酒店 / 房型</th><th>入住 → 退房</th><th>金额</th><th>状态</th><th></th></tr></thead>
    <tbody>{trs}</tbody>
  </table>
</div>

<div style="display:grid;grid-template-columns:1.3fr 1fr;gap:16px;" class="mt16">
  <div class="card">
    <div class="card-head"><h2>状态说明</h2><span class="sub">六状态，只有 8 条转换边</span></div>
    <div class="card-body">
      <div class="row wrap" style="gap:8px;">
        <span class="badge b-pending"><span class="d"></span>待确认</span>
        <span class="badge b-confirmed"><span class="d"></span>已确认</span>
        <span class="badge b-checkin"><span class="d"></span>已入住</span>
        <span class="badge b-checkout"><span class="d"></span>已退房</span>
        <span class="badge b-cancel"><span class="d"></span>已取消</span>
        <span class="badge b-noshow"><span class="d"></span>未入住</span>
      </div>
      <div class="hint mt12">前三种状态占用库存；已取消与未入住会释放库存。
        已入住不能取消、已退房不能重开——这类请求返回 409，状态与库存都不变，只记一条审计。</div>
    </div>
  </div>
  <div class="card">
    <div class="card-head"><h2>空态</h2></div>
    <div class="card-body">
      <div class="empty"><div class="big">🗂</div>
        还没有订单<br>
        <span class="hint">去「搜索酒店」看看，或者检查一下筛选的日期范围</span>
      </div>
    </div>
  </div>
</div>
"""
    return shell("07", "顾客端 / 我的订单", "我的订单",
                 "按状态分组查看；每行给出该状态可做的动作，不可做的动作直接不显示",
                 body, "M5 预订与订单 · REQ-015 · 界面07")


# ---------------- 界面08 订单详情 + 取消 / 改期（M5/M7） ----------------
def page08() -> str:
    body = """
<div style="display:grid;grid-template-columns:1fr 336px;gap:18px;align-items:start;">
  <div>
    <div class="card">
      <div class="card-head">
        <h2>订单 HT20261108000192</h2>
        <span class="badge b-confirmed"><span class="d"></span>已确认</span>
        <span class="spacer" style="flex:1;"></span>
        <span class="hint">创建于 2026-11-08 14:22 · 最后更新 11-08 14:31</span>
      </div>
      <div class="card-body">
        <div class="timeline">
          <div class="tl-step done"><div class="pt"></div><div class="lb">待确认</div></div>
          <div class="tl-step done"><div class="pt"></div><div class="lb">已确认</div></div>
          <div class="tl-step now"><div class="pt"></div><div class="lb">待入住</div></div>
          <div class="tl-step"><div class="pt"></div><div class="lb">已入住</div></div>
          <div class="tl-step"><div class="pt"></div><div class="lb">已退房</div></div>
        </div>
        <div class="hint mt12" style="text-align:center;">20:00 后到店请联系酒店；<b>23:59 前</b>酒店可标记「未入住」，此后系统于<b>次日 00:05 自动置为「已入住」</b>（宁可多算一晚，也不误判未到店）</div>
      </div>
    </div>

    <div class="card mt16">
      <div class="card-head"><h2>订单明细</h2></div>
      <div class="card-body" style="display:grid;grid-template-columns:1fr 1fr;gap:18px;">
        <dl class="kv">
          <dt>酒店</dt><dd>云栖·西湖山居（杭州 · 西湖区）</dd>
          <dt>房型</dt><dd>山景双床房 · 2 间</dd>
          <dt>入住</dt><dd>2026-11-20（周五）14:00 后</dd>
          <dt>退房</dt><dd>2026-11-22（周日）12:00 前</dd>
        </dl>
        <dl class="kv">
          <dt>入住人</dt><dd>陈一帆 · 138 0013 8000</dd>
          <dt>状态</dt><dd>已确认（酒店于 11-08 14:31 确认）</dd>
          <dt>取消政策</dt><dd>入住前 48 小时免费取消</dd>
          <dt>总价</dt><dd style="color:#B42318;font-weight:700;">¥2480</dd>
        </dl>
      </div>
      <table class="grid">
        <thead><tr><th>日期</th><th>单价</th><th>间数</th><th>小计</th></tr></thead>
        <tbody>
          <tr><td class="strong">11-20 周五</td><td class="num">¥620</td><td class="num">2</td><td class="num strong">¥1240</td></tr>
          <tr><td class="strong">11-21 周六</td><td class="num">¥620</td><td class="num">2</td><td class="num strong">¥1240</td></tr>
        </tbody>
      </table>
    </div>

    <div class="card mt16">
      <div class="card-head"><h2>可执行操作</h2><span class="sub">按钮是否可点，由状态决定</span></div>
      <div class="card-body">
        <div class="actions">
          <span class="btn danger">取消订单</span>
          <span class="btn">改期</span>
          <span class="btn ghost">联系酒店</span>
          <span class="btn" disabled>标记未入住</span>
        </div>
        <div class="alert a-warn mt12"><span class="ic">!</span>
          <div><b>为什么「标记未入住」是灰的</b>：那是酒店工作人员的权限（REQ-011 未入住标记），顾客看不到也点不动；
            越权调用接口会返回 403 并提示「无权执行该操作」。</div>
        </div>
        <div class="alert a-danger mt12"><span class="ic">×</span>
          <div><b>已入住之后不能再取消</b>：订单一旦「已入住」，取消按钮置灰并提示
            「房费已消费，如遇特殊情况请联系酒店协商，或由平台管理员强制取消（T7，会写入审计）」。</div>
        </div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-head"><h2>改期怎么算</h2></div>
    <div class="card-body">
      <div class="hint" style="line-height:1.9;">
        1. 先校验新日期区间余量（任一日不足即整单失败）；<br>
        2. 先占新日期（已占用 +2），成功后再放旧日期（已占用 −2）；<br>
        3. 两步在同一事务内，中途失败不会出现「新占一半」的中间态；<br>
        4. 若新日期单价不同，按新日期的每晚单价重新生成快照，总价随之变化。
      </div>
      <div class="alert a-info mt12"><span class="ic">i</span>
        <div>改期只允许一次，避免反复改期把库存刷乱（REQ-009）。</div>
      </div>
      <div class="btn mt16" style="justify-content:center;">选择新日期</div>
    </div>
  </div>
</div>
"""
    return shell("07", "顾客端 / 我的订单 / 详情", "订单详情",
                 "状态时间线 + 明细 + 可执行操作；不可执行的动作置灰并说明原因",
                 body, "M5 预订与订单 / M7 取消与改期 · REQ-009 / REQ-010 / REQ-015 · 界面08")


# ---------------- 界面09 取消确认（M7） ----------------
def page09() -> str:
    inner = """
<div class="dialog">
  <div class="dh">
    <h3>确认取消这张订单？</h3>
    <span class="badge b-confirmed"><span class="d"></span>已确认</span>
  </div>
  <div class="db">
    <div class="row" style="gap:12px;">
      <div class="thumb" style="width:84px;height:62px;flex:0 0 84px;"></div>
      <div>
        <div style="font-size:13.5px;font-weight:650;">云栖·西湖山居 · 山景双床房 2 间</div>
        <div class="hint mt8">11-20 → 11-22 · 订单 HT20261108000192</div>
      </div>
    </div>

    <div class="mt16" style="padding:12px 14px;border:1px solid #E4E7EC;border-radius:11px;background:#FCFDFF;">
      <div class="money"><span>已支付</span><span>¥2480</span></div>
      <div class="money"><span>取消手续费（距入住 8 天，免费取消期内）</span><span style="color:#067647;">¥0</span></div>
      <div class="money total"><span>预计退款</span><span style="color:#B42318;">¥2480</span></div>
      <div class="hint mt8">原路退回，1–3 个工作日到账。</div>
    </div>

    <div class="alert a-warn mt16"><span class="ic">!</span>
      <div><b>取消后房间立即释放</b>：这张订单占用的 2 间会在这笔操作提交后回到余量里，
        其他人马上就能订到；若你只是想换日期，建议先「改期」再决定要不要取消。</div>
    </div>

    <div class="alert a-danger mt12"><span class="ic">×</span>
      <div><b>不可取消区间</b>：11-14 至 11-16（展会期间）的订单不支持取消，页面会直接隐藏取消按钮并提示
        「该订单处于不可取消区间，如需取消请联系酒店」，而不是点了才报错。</div>
    </div>

    <div class="field mt16">
      <div class="label">取消原因（选填，用于改进服务）</div>
      <div class="input"><span class="ph">行程有变 / 找到更合适的 / 价格原因 / 其他</span></div>
    </div>
  </div>
  <div class="df">
    <span class="btn">暂不取消</span>
    <span class="btn danger">确认取消并退款</span>
  </div>
</div>
"""
    body = f'<div class="overlay" style="margin:-26px;min-height:838px;">{inner}</div>'
    return shell("07", "顾客端 / 我的订单 / 取消", "取消确认",
                 "取消前必须让用户看清退款金额与不可取消区间；确认后同事务释放库存",
                 body, "M7 取消与改期 · REQ-010 · 界面09")


# ---------------- 界面10 酒店工作台（M6） ----------------
def page10() -> str:
    rows = [
        ("HT20261112000318", "陈一帆", "高级江景大床房 × 1", "11-15 → 11-17", "¥1650", "04:12", "b-pending"),
        ("HT20261112000401", "李思远", "山景双床房 × 2", "11-18 → 11-20", "¥2480", "21:40", "b-pending"),
        ("HT20261112000455", "王雨桐", "亲子家庭房 × 1", "11-16 → 11-17", "¥820", "28:05", "b-pending"),
    ]
    trs = "".join(
        f"""
      <tr>
        <td class="strong">{no}<div class="hint">{guest}</div></td>
        <td>{room}</td>
        <td>{span}</td>
        <td class="num strong">{amt}</td>
        <td><span class="timer">剩 {left}</span></td>
        <td style="text-align:right;">
          <span class="btn sm primary">确认</span>
          <span class="btn sm">拒单</span>
        </td>
      </tr>""" for no, guest, room, span, amt, left, _ in rows)

    body = f"""
<div class="stats">
  <div class="stat"><div class="k">待确认</div><div class="v">3</div><div class="d">最早一单剩 4 分 12 秒</div></div>
  <div class="stat"><div class="k">今日入住</div><div class="v">12</div><div class="d">已办理 5 · 未到 7</div></div>
  <div class="stat"><div class="k">今日退房</div><div class="v">9</div><div class="d">已办理 6 · 待办 3</div></div>
  <div class="stat"><div class="k">本店今日余量</div><div class="v">17</div><div class="d">可售 42 − 已占用 25</div></div>
</div>

<div class="card mt16">
  <div class="card-head"><h2>待确认队列</h2><span class="sub">按剩余确认时间升序；超时由系统置为已取消（T3）并释放房间</span></div>
  <table class="grid">
    <thead><tr><th>订单号 / 顾客</th><th>房型 × 间数</th><th>入住 → 退房</th><th>金额</th><th>确认倒计时</th><th></th></tr></thead>
    <tbody>{trs}</tbody>
  </table>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;" class="mt16">
  <div class="card">
    <div class="card-head"><h2>今日入住</h2><span class="sub">核验订单号或手机号后办理</span></div>
    <div class="card-body">
      <div class="row wrap" style="gap:10px;">
        <div class="badge b-checkin"><span class="d"></span>已入住 5</div>
        <div class="badge b-confirmed"><span class="d"></span>待到店 7</div>
      </div>
      <div class="hint mt12">到店时间集中在 18:00–20:00；办理入口见「入住与退房（界面13）」。</div>
    </div>
  </div>
  <div class="card">
    <div class="card-head"><h2>超时预警</h2><span class="sub">30 分钟阈值可配置</span></div>
    <div class="card-body">
      <div class="alert a-warn"><span class="ic">!</span>
        <div>有 <b>1</b> 单剩余不足 5 分钟。超时未确认不会占房：状态转「已取消」、<b>已占用间数 −= 间数</b>、
          给顾客发站内与短信通知；整批扫描由 M10 每 5 分钟触发一次。</div>
      </div>
    </div>
  </div>
</div>
"""
    return shell("10", "酒店端 / 工作台", "酒店工作台",
                 "确认/拒单、今日入住退房、超时预警三件事集中在一屏",
                 body, "M6 履约与调度 · REQ-007 / REQ-011 · 界面10")


# ---------------- 界面11 库存日历（M3） ----------------
def page11() -> str:
    dates = ["11-15 六", "11-16 日", "11-17 一", "11-18 二", "11-19 三", "11-20 四"]
    rooms = [
        ("高级江景大床房", "20", [(12, 10), (12, 11), (12, 12), (12, 8), (12, 6), (12, 4)]),
        ("豪华双床房", "15", [(15, 10), (15, 12), (15, 9), (15, 9), (15, 7), (15, 5)]),
        ("行政套房", "6", [(6, 4), (6, 5), (6, 6), (6, 3), (6, 2), (6, 1)]),
    ]
    head = "".join(f"<th>{d}</th>" for d in dates)
    trs = ""
    for name, total, cells in rooms:
        tds = ""
        for sale, used in cells:
            rem = sale - used
            cls = "rem" if rem > 0 else "odo"
            tds += f"""<td class="cell"><div class="tri"><b>{sale}</b> / {used} / <span class="{cls}">{rem}</span></div></td>"""
        trs += f"""
      <tr>
        <td class="strong">{name}<div class="hint">总房量 {total}</div></td>
        {tds}
      </tr>"""

    body = f"""
<div class="card">
  <div class="card-head">
    <h2>房型 × 日期库存</h2>
    <span class="sub">每格 = <b>可售 / 已占用 / 余量</b>，余量 = 可售 − 已占用（03 §5 口径）</span>
    <div style="flex:1;"></div>
    <span class="btn sm">批量编辑</span><span class="btn sm">导出</span>
  </div>
  <table class="grid matrix">
    <thead><tr><th>房型</th>{head}</tr></thead>
    <tbody>{trs}</tbody>
  </table>
  <div class="card-body" style="border-top:1px solid var(--line);">
    <div class="row wrap" style="gap:18px;">
      <span class="hint"><b>可售</b>：酒店按日挂牌的可售总量，可直接改（维修封房就是调小它，范围 0 ~ 总房量）</span>
      <span class="hint"><b>已占用</b>：待确认 / 已确认 / 已入住三类订单的间数之和，只读</span>
      <span class="hint"><b>余量</b>：派生值，不落库，查询与下单共用同一算法</span>
    </div>
  </div>
</div>

<div class="alert a-danger mt16"><span class="ic">×</span>
  <div><b>改可售低于已占用 → 直接拒绝。</b>例：11-16 豪华双床房已占用 12 间，把可售改成 10 会被拒，
    并回显「该日已占用 12 间，可售不能低于 12」——不允许把已卖出的房间"改没了"。</div>
</div>

<div style="display:grid;grid-template-columns:1.4fr 1fr;gap:16px;" class="mt16">
  <div class="card">
    <div class="card-head"><h2>本次编辑待提交</h2><span class="sub">同事务提交，逐日行级校验</span></div>
    <table class="grid">
      <thead><tr><th>房型</th><th>日期</th><th>可售（原 → 新）</th><th>已占用</th><th>结果</th></tr></thead>
      <tbody>
        <tr><td class="strong">豪华双床房</td><td>11-18 二</td><td class="num">15 → <b>8</b></td><td class="num">9</td>
          <td><span class="badge b-noshow"><span class="d"></span>拒绝</span></td></tr>
        <tr><td class="strong">高级江景大床房</td><td>11-19 三</td><td class="num">12 → <b>14</b></td><td class="num">6</td>
          <td><span class="badge b-checkin"><span class="d"></span>可提交</span></td></tr>
      </tbody>
    </table>
  </div>
  <div class="card">
    <div class="card-head"><h2>批量编辑规则</h2></div>
    <div class="card-body">
      <div class="hint">① 一次可改多天，任一天校验失败则整批回滚（不留"改了一半"的中间态）；<br>
        ② 停售日期要改库存，先恢复销售状态；<br>
        ③ 「改总房量」（房型级：判据 N′ ≥ 各日已占用，通过后把各日可售钳制为 min(可售, N′)）
          与「按日改可售」（本页逐格，只动那一天，不碰总房量）是两条路径，判据不同，别混。</div>
    </div>
  </div>
</div>
"""
    return shell("11", "酒店端 / 库存日历", "库存日历",
                 "按「房型 × 日期」维护可售；已占用只读、余量派生——三者同屏，改错当场被拒",
                 body, "M3 库存与价格 · REQ-003 / REQ-012 · 界面11")


# ---------------- 界面12 价格日历与停售/停业（M3） ----------------
def page12() -> str:
    dates = ["11-15 六", "11-16 日", "11-17 一", "11-18 二", "11-19 三"]
    rooms = [
        ("高级江景大床房", ["880", "880", "720", "720", "720"], False),
        ("豪华双床房", ["960", "960", "800", "800", "800"], False),
        ("行政套房", ["1580", "1580", "1380", "1380", "1380"], True),
    ]
    head = "".join(f"<th>{d}</th>" for d in dates)
    trs = ""
    for name, prices, stopped in rooms:
        tds = "".join(
            f'<td class="cell"><div class="tri">{"—" if stopped else "¥" + p}</div></td>' for p in prices)
        state = ('<span class="badge b-noshow"><span class="d"></span>停售</span>' if stopped
                 else '<span class="badge b-checkin"><span class="d"></span>在售</span>')
        trs += f"""
      <tr>
        <td class="strong">{name}<div class="hint">{state}</div></td>
        {tds}
        <td style="text-align:right;"><span class="btn sm">{'恢复销售' if stopped else '停售'}</span></td>
      </tr>"""

    body = f"""
<div class="card">
  <div class="card-head">
    <h2>房型 × 日期价格</h2>
    <span class="sub">改价只影响<b>新订单</b>，已确认订单按逐晚快照结算</span>
    <div style="flex:1;"></div>
    <span class="btn sm">批量调价</span>
  </div>
  <table class="grid matrix">
    <thead><tr><th>房型 / 状态</th>{head}<th></th></tr></thead>
    <tbody>{trs}</tbody>
  </table>
</div>

<div class="alert a-warn mt16"><span class="ic">!</span>
  <div><b>改价不追改历史。</b>下单那一刻的每晚单价写进 <code>booking_night</code>（订单号 + 日期联合唯一），
    总价 = Σ（单价 × 间数）。所以 11-15 改成 ¥980 之后，已确认订单的 ¥880 不会变——报表里能同时看到"当时价"和"当前价"。</div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;" class="mt16">
  <div class="card">
    <div class="card-head"><h2>停售 / 停业</h2><span class="sub">两个不同动作</span></div>
    <div class="card-body">
      <div class="kv">
        <dt>停售</dt><dd>单房型开关，不改库存数字。页面写「暂停销售」，不是「已订满」——两者含义不同，不能混用一句文案。</dd>
        <dt>停业</dt><dd>整店停止接单（装修/证照/不可抗力）。<b>需二次确认</b>，并提示「已确认订单须逐单协商取消，平台会记录通知与协商结果（REQ-023）」。</dd>
      </div>
      <div class="alert a-danger mt12"><span class="ic">×</span>
        <div>停业前系统先列出受影响的已在店订单数与间夜数，避免"一键停业"造成大批无法履约的订单。</div>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-head"><h2>不可取消区间</h2><span class="sub">由 M3 节假日表驱动，界面只读</span></div>
    <div class="card-body">
      <div class="row wrap" style="gap:8px;">
        <span class="pill">11-14 ~ 11-16 展会</span>
        <span class="pill">12-31 ~ 01-02 元旦</span>
      </div>
      <div class="hint mt12">这些日期内可选「不可取消」政策；顾客端取消页会直接隐藏取消按钮并提示联系酒店，
        不是点了才报错。维护入口见「节假日字典（界面15）」。</div>
    </div>
  </div>
</div>
"""
    return shell("12", "酒店端 / 价格与停售", "价格日历与停售",
                 "逐日改价、单房型停售、整店停业三件事分开做；改价不追改历史",
                 body, "M3 库存与价格 · REQ-024 / REQ-012 / REQ-023 · 界面12")


# ---------------- 界面13 入住 / 退房办理（M6） ----------------
def page13() -> str:
    body = """
<div style="display:grid;grid-template-columns:1fr 1.15fr;gap:16px;">
  <div class="card">
    <div class="card-head"><h2>核对订单</h2><span class="sub">订单号或手机号任一项即可</span></div>
    <div class="card-body">
      <div class="field"><div class="label">订单号</div><div class="input">HT20261108000192</div></div>
      <div class="field"><div class="label">或 手机号后四位</div><div class="input"><span class="ph">8000</span></div></div>
      <div class="row mt12"><span class="btn primary">核验并调出订单</span><span class="btn ghost">扫证件</span></div>
      <div class="alert a-danger mt12"><span class="ic">×</span>
        <div>状态不是「已确认」时不得办理入住：返回 409 并显示当前状态（如「该订单已取消」），库存与状态都不变。</div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-head"><h2>核对结果</h2><span class="sub">核验通过后才出现动作按钮</span></div>
    <div class="card-body">
      <div class="row" style="justify-content:space-between;">
        <div><b>HT20261108000192</b> <span class="badge b-confirmed"><span class="d"></span>已确认</span></div>
        <span class="hint">陈一帆 · 138 0013 8000</span>
      </div>
      <div class="kv mt12">
        <dt>房型</dt><dd>山景双床房 × 2 间</dd>
        <dt>入住 → 退房</dt><dd>2026-11-20 14:00 后 → 2026-11-22 12:00 前</dd>
        <dt>取消政策</dt><dd>入住前 48 小时免费取消</dd>
        <dt>身份核验</dt><dd>已核对 2 位入住人证件</dd>
      </div>
      <div class="row wrap mt16" style="gap:10px;">
        <span class="btn primary">办理入住（T4）</span>
        <span class="btn">办理退房（T8）</span>
        <span class="btn" disabled>标记未入住（T6）</span>
      </div>
      <div class="alert a-warn mt12"><span class="ic">!</span>
        <div><b>「标记未入住」为什么是灰的：</b>现在是入住日 23:59 之后。规则是
          <b>23:59 之前</b>酒店可标记「未入住」并释放房间；<b>过了 23:59 按钮置灰</b>，
          系统会在<b>次日 00:05</b> 把这单自动置为「已入住」（T5）——宁可多算一晚房费，也不误判顾客没来。</div>
      </div>
    </div>
  </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;" class="mt16">
  <div class="card">
    <div class="card-head"><h2>办理入住的副作用</h2></div>
    <div class="card-body"><div class="hint">状态 已确认 → 已入住，库存不变（本来就占着）；写一条审计，记操作人、时间、来源=前台。</div></div>
  </div>
  <div class="card">
    <div class="card-head"><h2>办理退房</h2></div>
    <div class="card-body"><div class="hint">状态 已入住 → 已退房（终态）。房态回「可售」是次日库存行的事，不回补当天的已占用。</div></div>
  </div>
  <div class="card">
    <div class="card-head"><h2>标记未入住</h2></div>
    <div class="card-body"><div class="hint">只在入住日 23:59 前可做：状态 → 未入住、<b>已占用间数 −= 间数</b>、写审计（来源=人工）。</div></div>
  </div>
</div>
"""
    return shell("13", "酒店端 / 入住与退房", "入住 / 退房办理",
                 "先核验后办理；no-show 标记按时间窗开关，过了 23:59 就交回系统兜底",
                 body, "M6 履约与调度 · REQ-013 / REQ-011 · 界面13")


# ---------------- 界面14 入驻申请与审核（M2） ----------------
def page14() -> str:
    rows = [
        ("云栖·苏州平江府", "苏州 · 平江路", "8.5 分 · 4 星", "2026-11-11 09:12", "待审核", "b-pending"),
        ("云栖·成都宽窄巷", "成都 · 青羊区", "8.1 分 · 3 星", "2026-11-10 16:40", "待补充材料", "b-noshow"),
        ("云栖·杭州西溪湿地", "杭州 · 余杭区", "9.0 分 · 5 星", "2026-11-09 11:05", "已通过", "b-checkin"),
    ]
    trs = "".join(
        f"""
      <tr>
        <td class="strong">{name}<div class="hint">{addr}</div></td>
        <td>{level}</td>
        <td>{ts}</td>
        <td><span class="badge {cls}"><span class="d"></span>{st}</span></td>
        <td style="text-align:right;"><span class="btn sm">查看</span><span class="btn sm primary">审核</span></td>
      </tr>""" for name, addr, level, ts, st, cls in rows)

    body = f"""
<div class="card">
  <div class="card-head"><h2>入驻申请</h2><span class="sub">审核通过后自动创建酒店账号并初始化每日库存行</span>
    <div style="flex:1;"></div><span class="btn sm">导出</span></div>
  <table class="grid">
    <thead><tr><th>酒店</th><th>等级</th><th>提交时间</th><th>状态</th><th></th></tr></thead>
    <tbody>{trs}</tbody>
  </table>
</div>

<div style="display:grid;grid-template-columns:1.15fr 1fr;gap:16px;" class="mt16">
  <div class="card">
    <div class="card-head"><h2>资料详情 · 云栖·苏州平江府</h2><span class="sub">只读，来自申请表单</span></div>
    <div class="card-body">
      <div class="kv">
        <dt>营业执照</dt><dd>已上传 · 91320500MA1XXX（与主体名称一致）</dd>
        <dt>消防 / 特种行业</dt><dd>已上传 · 有效期至 2028-06</dd>
        <dt>房型与房量</dt><dd>大床房 12 间 / 双床房 10 间 / 套房 3 间（总房量 25）</dd>
        <dt>联系人</dt><dd>周敏 · 139 0013 9000</dd>
        <dt>结算账户</dt><dd>已核验（开户名与主体一致）</dd>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-head"><h2>审核意见</h2></div>
    <div class="card-body">
      <div class="field"><div class="label">结论</div>
        <div class="row wrap" style="gap:8px;">
          <span class="pill blue">通过</span><span class="pill">驳回</span><span class="pill">要求补充材料</span>
        </div>
      </div>
      <div class="field"><div class="label">理由（驳回 / 补充材料时必填）</div>
        <div class="input" style="height:64px;"><span class="ph">例：消防证已过有效期，请重新上传</span></div>
      </div>
      <div class="hint">通过后：酒店状态 → 已入驻、自动创建酒店账号（角色=酒店工作人员）、
        按总房量为未来 90 天建每日库存行（幂等，重复点不出重复行）。</div>
      <div class="row mt12"><span class="btn primary">提交审核结果</span><span class="btn ghost">退回</span></div>
    </div>
  </div>
</div>
"""
    return shell("14", "平台管理 / 入驻审核", "入驻申请与审核",
                 "审核只改酒店状态与账号，不动业务数据；驳回必须写理由",
                 body, "M2 酒店与房型 · REQ-025 · 界面14")


# ---------------- 界面15 节假日日期表（M3） ----------------
def page15() -> str:
    rows = [
        ("2026-11-14", "2026-11-16", "展会", "不可取消", "启用"),
        ("2026-12-31", "2027-01-02", "元旦", "不可取消", "启用"),
        ("2026-10-01", "2026-10-07", "国庆", "加价 20%", "启用"),
        ("2027-02-06", "2027-02-12", "春节", "加价 30%", "已停用"),
    ]
    trs = "".join(
        f"""
      <tr>
        <td class="strong">{a}</td><td>{b}</td><td>{name}</td><td>{policy}</td>
        <td><span class="badge {'b-checkin' if st == '启用' else 'b-checkout'}"><span class="d"></span>{st}</span></td>
        <td style="text-align:right;"><span class="btn sm">编辑</span><span class="btn sm">{'启用' if st == '已停用' else '停用'}</span></td>
      </tr>""" for a, b, name, policy, st in rows)

    body = f"""
<div style="display:grid;grid-template-columns:1.35fr 1fr;gap:16px;">
  <div class="card">
    <div class="card-head"><h2>节假日日期区间</h2><span class="sub">平台级字典，所有酒店共用（不归属某一家酒店）</span>
      <div style="flex:1;"></div><span class="btn sm">批量导入</span><span class="btn sm primary">新增</span></div>
    <table class="grid">
      <thead><tr><th>开始</th><th>结束</th><th>名称</th><th>默认政策</th><th>状态</th><th></th></tr></thead>
      <tbody>{trs}</tbody>
    </table>
  </div>

  <div class="card">
    <div class="card-head"><h2>新增区间</h2><span class="sub">日期唯一，重复即拒绝</span></div>
    <div class="card-body">
      <div class="field"><div class="label">开始 / 结束日期</div><div class="input">2027-05-01 → 2027-05-05</div></div>
      <div class="field"><div class="label">名称</div><div class="input">劳动节</div></div>
      <div class="field"><div class="label">默认取消政策</div><div class="input">不可取消</div></div>
      <div class="alert a-danger mt12"><span class="ic">×</span>
        <div><b>日期重复 → 拒绝并高亮冲突行。</b>例：2026-12-31 ~ 2027-01-02 已有记录，
          新增与之重叠的 2027-01-01 ~ 2027-01-03 会被拒，提示「与『元旦』重叠」。</div>
      </div>
      <div class="alert a-info mt10"><span class="ic">i</span>
        <div>新增或修改后<b>即刻生效</b>：顾客端取消页的「不可取消区间」、价格日历的默认政策都读这张表。</div>
      </div>
    </div>
  </div>
</div>

<div class="card mt16">
  <div class="card-head"><h2>日期与日历对照（2026-11）</h2><span class="sub">有标记的日期采用该区间的取消政策</span></div>
  <div class="card-body">
    <div class="row wrap" style="gap:8px;">
      <span class="pill">11-11 平日</span><span class="pill">11-12 平日</span><span class="pill">11-13 平日</span>
      <span class="pill blue">11-14 展会</span><span class="pill blue">11-15 展会</span><span class="pill blue">11-16 展会</span>
      <span class="pill">11-17 平日</span><span class="pill">11-18 平日</span>
    </div>
    <div class="alert a-warn mt12"><span class="ic">!</span>
      <div><b>没有「删除」，只有「停用」。</b>区间一旦被历史订单引用过就不能物理删——
        取消政策要按「下单当时」的日历集合追溯，删掉行会让历史订单的「当时为什么不可取消」查不到。
        停用只是不再命中新订单，行还在，可随时启用回来。</div>
    </div>
  </div>
</div>
"""
    return shell("15", "平台管理 / 节假日字典", "节假日日期表维护",
                 "平台级字典，管的是「哪些日子特殊」；酒店的价格与取消政策都从这里取默认值",
                 body, "M3 库存与价格 · REQ-027 · 界面15")


# ---------------- 界面16 统计看板（M8） ----------------
def page16() -> str:
    bars = [("11-06", 62), ("11-07", 74), ("11-08", 58), ("11-09", 81),
            ("11-10", 69), ("11-11", 77), ("11-12", 88)]
    bars_html = "".join(
        f'<div class="b" style="height:{h}%"><span>{h}</span></div>' for _, h in bars)
    labels = "".join(f'<div class="bl">{d}</div>' for d, _ in bars)

    body = f"""
<div class="row" style="justify-content:space-between;align-items:center;">
  <div class="seg" style="margin:0;">
    <span class="s on">本店</span><span class="s">全平台</span>
  </div>
  <div class="row" style="gap:10px;">
    <span class="pill blue">近 7 天</span><span class="pill">近 30 天</span><span class="pill">按日</span><span class="pill">按月</span>
    <span class="btn sm">导出</span>
  </div>
</div>

<div class="stats mt16">
  <div class="stat"><div class="k">入住率</div><div class="v">78.4%</div><div class="d">已住间夜 / 可售间夜</div></div>
  <div class="stat"><div class="k">订单量</div><div class="v">1,246</div><div class="d">较上周期 +12.6%</div></div>
  <div class="stat"><div class="k">取消率</div><div class="v">9.8%</div><div class="d">含超时未确认（T3）</div></div>
  <div class="stat"><div class="k">RevPAR</div><div class="v">¥612</div><div class="d">房费收入 / 可售间夜</div></div>
</div>

<div style="display:grid;grid-template-columns:1.5fr 1fr;gap:16px;" class="mt16">
  <div class="card">
    <div class="card-head"><h2>出租率趋势</h2><span class="sub">按日聚合（I15 指标汇总 → I21 趋势与导出）</span></div>
    <div class="card-body">
      <div class="bars">{bars_html}</div>
      <div class="blrow">{labels}</div>
    </div>
  </div>
  <div class="card">
    <div class="card-head"><h2>指标口径</h2><span class="sub">看板只读，不参与业务决策</span></div>
    <div class="card-body">
      <div class="kv">
        <dt>入住率</dt><dd>已住间夜 ÷ 可售间夜。可售按每日挂牌量算，<b>不是</b>总房量</dd>
        <dt>取消率</dt><dd>取消单 ÷ 全部单，区分顾客取消 / 超时取消 / 酒店原因取消</dd>
        <dt>RevPAR</dt><dd>房费收入 ÷ 可售间夜，只算房费不含服务费</dd>
        <dt>数据来源</dt><dd>只读 M3 / M4 / M5 的仓储接口，不反写业务库</dd>
      </div>
      <div class="alert a-info mt12"><span class="ic">i</span>
        <div>导出走 I21：<b>只有汇总数据</b>（指标、趋势、区间），不含逐条订单明细——明细导出不在 M8 职责内。</div>
      </div>
    </div>
  </div>
</div>

<div class="alert a-warn mt16"><span class="ic">!</span>
  <div>无数据时不留白：空态写明「所选区间没有成交订单」并给出指标口径与最短可选区间，而不是画一条 0 的假趋势线。</div>
</div>
"""
    return shell("16", "酒店端 / 统计报表", "统计看板",
                 "本店与全平台两个视角；只读指标 + 趋势导出，不碰业务数据",
                 body, "M8 报表统计 · REQ-016 · 界面16")


# ---------------- 界面17 审计日志查询（M9） ----------------
def page17() -> str:
    rows = [
        ("2026-11-12 14:31:07", "陈一帆", "顾客", "订单 HT20261108000192", "状态变更",
         "已确认 → 已入住", "前台核验身份证 2 人"),
        ("2026-11-12 14:30:52", "周敏", "酒店工作人员", "库存 豪华双床房 / 11-16", "库存调整",
         "可售 15 → 12（已占用 12）", "维修封房 3 间"),
        ("2026-11-12 14:05:11", "系统", "系统任务", "订单 HT20261112000399", "状态变更",
         "待确认 → 已取消", "超时未确认（T3），回补 1 间"),
        ("2026-11-12 13:58:40", "刘浩然", "平台管理员", "用户 139****9000", "越权尝试",
         "—", "跨店查询被拒 403"),
        ("2026-11-12 11:20:03", "周敏", "酒店工作人员", "价格 行政套房 / 11-19", "价格调整",
         "¥1380 → ¥1280", "周中促销"),
    ]
    trs = "".join(
        f"""
      <tr>
        <td class="hint" style="white-space:nowrap;">{ts}</td>
        <td class="strong">{who}<div class="hint">{role}</div></td>
        <td>{obj}</td>
        <td>{act}</td>
        <td>{chg}</td>
        <td class="hint">{note}</td>
      </tr>""" for ts, who, role, obj, act, chg, note in rows)

    body = f"""
<div class="card">
  <div class="card-head"><h2>查询条件</h2><span class="sub">只读查询：没有编辑、没有删除按钮</span></div>
  <div class="card-body">
    <div class="row wrap" style="gap:10px;">
      <div class="search-mini" style="width:190px;height:34px;">⌕ 操作人</div>
      <div class="search-mini" style="width:150px;height:34px;">角色：全部 ▾</div>
      <div class="search-mini" style="width:210px;height:34px;">对象（订单号 / 房型 / 用户）</div>
      <div class="search-mini" style="width:180px;height:34px;">2026-11-12 ▾</div>
      <div class="search-mini" style="width:150px;height:34px;">动作：全部 ▾</div>
      <span class="btn primary sm">查询</span>
      <span class="btn sm">导出（需申请）</span>
    </div>
  </div>
</div>

<div class="card mt16">
  <div class="card-head"><h2>结果</h2><span class="sub">共 5 条 · 按时间倒序 · 变更前后状态成对出现</span></div>
  <table class="grid">
    <thead><tr><th>时间</th><th>操作人 / 角色</th><th>对象</th><th>动作</th><th>变更</th><th>备注</th></tr></thead>
    <tbody>{trs}</tbody>
  </table>
</div>

<div class="stats mt16">
  <div class="stat"><div class="k">只追加</div><div class="v" style="font-size:15px;line-height:1.6;">不可改、不可删</div>
    <div class="d">写入口径只有 append；改历史只能靠新记录说明</div></div>
  <div class="stat"><div class="k">保留 180 天</div><div class="v" style="font-size:15px;line-height:1.6;">过期转归档</div>
    <div class="d">超期查询提示「已归档，需申请导出」</div></div>
  <div class="stat"><div class="k">越权 403</div><div class="v" style="font-size:15px;line-height:1.6;">按数据归属判定</div>
    <div class="d">酒店只看本店；跨店查询返回 403 并记一条越权尝试</div></div>
</div>

<div class="alert a-warn mt16"><span class="ic">!</span>
  <div>审计里连「被拒绝的请求」也要留痕：越权查询、非法状态转换（409）都会写一条，只是不写业务变更。
    否则事后复盘看不出"有人试图做过什么"。</div>
</div>
"""
    return shell("17", "平台管理 / 审计日志", "审计日志查询",
                 "只追加、保留 180 天、越权 403——三条硬约束写在页面上，不是只写在文档里",
                 body, "M9 审计与日志 · REQ-017 · 界面17")


PAGES = {
    "界面01": page01, "界面02": page02, "界面03": page03, "界面04": page04,
    "界面05": page05, "界面06": page06, "界面07": page07, "界面08": page08,
    "界面09": page09, "界面10": page10, "界面11": page11, "界面12": page12,
    "界面13": page13, "界面14": page14, "界面15": page15, "界面16": page16,
    "界面17": page17,
}


if __name__ == "__main__":
    for name, fn in PAGES.items():
        p = OUT / f"{name}.html"
        p.write_text(fn(), encoding="utf-8")
        print(name, len(p.read_text(encoding="utf-8")), "chars")
