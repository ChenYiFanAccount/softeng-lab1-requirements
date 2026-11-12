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
              ("17", "审计日志", "界面17"), ("19", "用户与角色", "界面19"),
              ("20", "运维与对账", "界面20")]),
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
      三端同一套账号体系（M1 统一鉴权）
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
                 body, "M1 账号与权限 · REQ-020 · 界面01", bare=True)


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
      <div><b>无房空态</b>：所选日期已无房时，列表区显示「11-15 至 11-17 已无房」+ 前后 1 天可订日期按钮，
        不隐藏筛选条件；单日余量不足时列表仍展示该酒店，但房型行标「该日余量不足」并禁用「预订」。</div>
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
        <div class="hint mt12" style="text-align:center;">20:00 后到店请联系酒店；入住日当天 24:00 未到店将标记「未入住」</div>
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
          <div><b>为什么「标记未入住」是灰的</b>：那是酒店工作人员的权限（REQ-013），顾客看不到也点不动；
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


PAGES = {
    "界面01": page01, "界面02": page02, "界面03": page03, "界面04": page04,
    "界面05": page05, "界面06": page06, "界面07": page07, "界面08": page08,
    "界面09": page09,
}

if __name__ == "__main__":
    for name, fn in PAGES.items():
        p = OUT / f"{name}.html"
        p.write_text(fn(), encoding="utf-8")
        print(name, len(p.read_text(encoding="utf-8")))
