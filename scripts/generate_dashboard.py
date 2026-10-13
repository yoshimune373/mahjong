#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麻雀スコアダッシュボード 自動生成スクリプト

使い方: python generate_dashboard.py <CSVフォルダ> <出力HTML>
"""
import csv, json, os, glob, re, sys
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))


def _num(v, cast=float):
    v = (v or '').strip()
    if not v or v == '-':
        return None
    try:
        return cast(float(v))
    except ValueError:
        return None


def parse_csv_file(filepath):
    """1ファイルを読み、日付ごとのセッションのリストを返す"""
    with open(filepath, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames or []
    if not rows:
        return []

    # プレイヤー名を抽出（ヘッダー末尾の空白は無視）
    players = [h.strip()[:-2].strip() for h in headers if h.strip().endswith('点数')]
    cols = {p: {} for p in players}
    for h in headers:
        hs = h.strip()
        for p in players:
            for key, label in (('pt', '点数'), ('sc', 'スコア'), ('chip', 'チップ'), ('pay', '収支')):
                if hs == p + ' ' + label:
                    cols[p][key] = h

    by_date = {}
    for row in rows:
        date = (row.get('日付') or '').strip()
        if date:
            by_date.setdefault(date, []).append(row)

    sessions = []
    for date, date_rows in by_date.items():
        date_rows.sort(key=lambda r: _num(r.get('回戦数'), int) or 0)
        games, chips = [], [0] * len(players)
        for row in date_rows:
            g = {'pt': [], 'sc': [], 'pay': []}
            for i, p in enumerate(players):
                c = cols[p]
                g['pt'].append(_num(row.get(c.get('pt', '')), int) or 0)
                g['sc'].append(_num(row.get(c.get('sc', ''))) or 0.0)
                g['pay'].append(_num(row.get(c.get('pay', '')), int) or 0)
                chips[i] += _num(row.get(c.get('chip', '')), int) or 0
            games.append(g)
        sessions.append({
            'date': date,
            'players': players[:],
            'games': games,
            'chips': chips,
            'src': os.path.basename(filepath),
        })
    return sessions


def _fix_chips(games, chips):
    """チップ合計がゼロにならない場合、1半荘目の収支から逆算して補正する。
    収支 = スコア×点単価 + チップ×チップ単価 の関係を使い、
    1人分だけ入力ミスしているケースのみ補正する（それ以外はそのまま）。"""
    if sum(chips) == 0 or not games:
        return chips
    # 点単価：チップの載らない2半荘目以降の 収支/スコア から求める
    rate = None
    for g in games[1:]:
        for sc, pay in zip(g['sc'], g['pay']):
            if sc:
                rate = pay / sc
                break
        if rate:
            break
    if not rate:
        return chips
    g0 = games[0]
    chip_yen = [pay - sc * rate for sc, pay in zip(g0['sc'], g0['pay'])]
    # チップ単価：記録と収支が整合しているプレイヤーから求める
    unit = None
    for c, y in zip(chips, chip_yen):
        if c and abs(y / c - round(y / c)) < 1e-6 and round(y / c) > 0:
            cand = round(y / c)
            if all(abs(yy - cc * cand) < 1e-6 for cc, yy in zip(chips, chip_yen) if cc and cc != c) or unit is None:
                unit = cand
    if not unit:
        return chips
    derived = [round(y / unit) for y in chip_yen]
    if sum(derived) != 0 or sum(a != b for a, b in zip(chips, derived)) != 1:
        return chips
    return derived


def _first_game_sig(sess):
    """1半荘目の素点（プレイヤー順に依存しない）"""
    g = sess['games'][0]
    return tuple(sorted(zip(sess['players'], g['pt'])))


def _export_time(sess):
    """ファイル名末尾の出力日時（例: 2026-04-24 18_00_04.332933）"""
    m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}[_:]\d{2}[_:]\d{2}(?:\.\d+)?)', sess['src'])
    return m.group(1).replace(':', '_') if m else ''


def dedupe(sessions):
    """同じセッションが複数のCSVに入っている場合に1つにまとめる。
    同一日・同一メンバーで1半荘目の素点が一致するものは同じセッションとみなし、
    チップ合計がゼロ（差し引きで記録）のものを優先し、その中で出力日時が
    最も新しいもの（同時刻なら半荘数が多いもの）を採用する。
    途中で出力したCSVや、後から点数を修正したCSVもこれで最新版に揃う。"""
    groups = {}
    for s in sessions:
        key = (s['date'], tuple(sorted(s['players'])), _first_game_sig(s))
        groups.setdefault(key, []).append(s)

    kept, removed = [], 0
    for group in groups.values():
        group.sort(key=lambda s: (sum(s['chips']) == 0, _export_time(s), len(s['games'])), reverse=True)
        s = group[0]
        fixed = _fix_chips(s['games'], s['chips'])
        if fixed != s['chips']:
            print(f"  チップ補正: {s['date']} {s['players']} {s['chips']} → {fixed}（収支から逆算）", file=sys.stderr)
            s['chips'] = fixed
        elif sum(s['chips']) != 0:
            print(f"  注意: チップ合計が0になりません: {s['date']} {s['players']} {s['chips']}", file=sys.stderr)
        kept.append(s)
        removed += len(group) - 1
    return kept, removed


def parse_csv_files(score_dir):
    sessions = []
    for filepath in sorted(glob.glob(os.path.join(score_dir, '*.csv'))):
        try:
            sessions.extend(parse_csv_file(filepath))
        except Exception as e:
            print(f"警告: {filepath}: {e}", file=sys.stderr)

    sessions, removed = dedupe(sessions)
    if removed:
        print(f"  重複・途中出力のセッションを {removed} 件スキップしました", file=sys.stderr)

    sessions.sort(key=lambda s: (s['date'], s['src']))
    for s in sessions:
        del s['src']
        # スコアは小数第1位まで（JSONを小さくする）
        for g in s['games']:
            g['sc'] = [round(v, 1) for v in g['sc']]
    return sessions


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>麻雀スコア</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🀄</text></svg>">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
:root{
  --bg:#ffffff;--bg2:#f5f5f2;--bg3:#ecebe6;--page:#e7e6e0;
  --text:#1a1a18;--text2:#5f5f5b;--text3:#8e8e89;
  --border:rgba(0,0,0,0.09);--border2:rgba(0,0,0,0.18);
  --green:#17845F;--red:#C94F27;--gold:#B06E12;--silver:#7d7c76;--bronze:#93401f;
  --green-bg:rgba(23,132,95,0.12);--red-bg:rgba(201,79,39,0.12);
  --accent:#1a1a18;--on-accent:#ffffff;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#1c1c1a;--bg2:#252523;--bg3:#30302d;--page:#121211;
    --text:#f0efe8;--text2:#a8a8a2;--text3:#76766f;
    --border:rgba(255,255,255,0.09);--border2:rgba(255,255,255,0.2);
    --green:#5DCAA5;--red:#F0997B;--gold:#E3A64A;--silver:#b5b4ad;--bronze:#d9825e;
    --green-bg:rgba(93,202,165,0.15);--red-bg:rgba(240,153,123,0.15);
    --accent:#f0efe8;--on-accent:#1c1c1a;
  }
}
html{-webkit-text-size-adjust:100%;}
body{font-family:-apple-system,BlinkMacSystemFont,'Hiragino Sans','Hiragino Kaku Gothic ProN','Yu Gothic UI','Meiryo',sans-serif;background:var(--page);color:var(--text);font-feature-settings:"palt";}
.num{font-variant-numeric:tabular-nums;}
.app{max-width:520px;margin:0 auto;background:var(--bg);min-height:100vh;}
.top{position:sticky;top:0;z-index:10;background:var(--bg);border-bottom:0.5px solid var(--border);}
.header{padding:14px 16px 6px;}
.header h1{font-size:19px;font-weight:700;letter-spacing:0.02em;}
.header .meta{font-size:12px;color:var(--text2);margin-top:3px;}
.tabs{display:flex;gap:6px;padding:8px 16px 10px;overflow-x:auto;scrollbar-width:none;}
.tabs::-webkit-scrollbar{display:none;}
.tab{flex-shrink:0;font-size:13px;padding:6px 14px;border-radius:999px;border:0.5px solid var(--border2);cursor:pointer;color:var(--text2);background:transparent;font-family:inherit;transition:background .15s,color .15s;}
.tab.active{background:var(--accent);color:var(--on-accent);border-color:var(--accent);font-weight:600;}
.content{padding-bottom:40px;}
.section{padding:18px 16px 0;}
.section-title{font-size:12px;font-weight:700;color:var(--text3);letter-spacing:0.06em;margin-bottom:10px;display:flex;justify-content:space-between;align-items:baseline;gap:8px;}
.section-title .hint{font-weight:400;letter-spacing:0;font-size:11px;}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}
.metric{background:var(--bg2);border-radius:10px;padding:12px 14px;}
.metric-label{font-size:11px;color:var(--text2);margin-bottom:4px;}
.metric-value{font-size:22px;font-weight:700;}
.metric-sub{font-size:11px;color:var(--text3);margin-top:2px;}
.pos{color:var(--green);}.neg{color:var(--red);}.zero{color:var(--text2);}
.list{display:flex;flex-direction:column;gap:8px;}
.row{display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--bg);border:0.5px solid var(--border);border-radius:12px;}
.row.click{cursor:pointer;}
.row.click:hover{background:var(--bg2);}
.rank-num{font-size:14px;font-weight:700;color:var(--text3);width:22px;flex-shrink:0;text-align:center;}
.rank-num.r1{color:var(--gold);}.rank-num.r2{color:var(--silver);}.rank-num.r3{color:var(--bronze);}
.avatar{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;flex-shrink:0;}
.info{flex:1;min-width:0;}
.name{font-size:15px;font-weight:700;}
.sub{font-size:11px;color:var(--text2);margin-top:2px;line-height:1.45;}
.right{text-align:right;flex-shrink:0;}
.amount{font-size:16px;font-weight:700;}
.amount small{font-size:11px;font-weight:600;margin-left:1px;}
.chip-pill{display:inline-block;margin-top:3px;font-size:11px;font-weight:600;padding:1px 7px;border-radius:999px;background:var(--bg2);}
.chart-wrap{position:relative;width:100%;height:260px;}
.page{display:none;}.page.show{display:block;}
.hidden{display:none !important;}
.back-btn{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text2);background:none;border:none;cursor:pointer;padding:14px 16px 0;font-family:inherit;}
.stat-row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:0.5px solid var(--border);font-size:13px;gap:8px;}
.stat-row:last-child{border-bottom:none;}
.stat-label{color:var(--text2);}.stat-val{font-weight:700;}
.stat-group{font-size:11px;font-weight:700;color:var(--text3);letter-spacing:0.06em;padding:14px 0 2px;}
.seg{display:inline-flex;background:var(--bg2);border-radius:9px;padding:3px;gap:2px;}
.seg button{border:none;background:transparent;font-family:inherit;font-size:13px;color:var(--text2);padding:6px 12px;border-radius:7px;cursor:pointer;}
.seg button.on{background:var(--bg);color:var(--text);font-weight:700;box-shadow:0 1px 2px rgba(0,0,0,0.12);}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;}
.note{font-size:11px;color:var(--text3);margin-top:8px;line-height:1.6;}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;}
.legend button{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--text2);background:var(--bg2);border:none;border-radius:999px;padding:4px 10px;cursor:pointer;font-family:inherit;}
.legend button.off{opacity:0.4;}
.legend .dot{width:9px;height:9px;border-radius:50%;}
.legend-actions{display:flex;gap:10px;margin-bottom:8px;}
.linkbtn{background:none;border:none;color:var(--text2);font-size:12px;text-decoration:underline;cursor:pointer;font-family:inherit;padding:0;}
.form{display:flex;gap:4px;flex-wrap:wrap;}
.form span{width:24px;height:24px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;}
.f1{background:var(--green-bg);color:var(--green);}.f2,.f3{background:var(--bg2);color:var(--text2);}.f4{background:var(--red-bg);color:var(--red);}
.history-card{border:0.5px solid var(--border);border-radius:12px;overflow:hidden;}
.history-header{padding:8px 12px;background:var(--bg2);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;font-size:12px;}
.history-header .d{font-weight:700;}.history-header .g{color:var(--text3);}
.history-body{padding:4px 12px;}
.history-row{display:grid;grid-template-columns:1fr auto auto;gap:10px;align-items:center;font-size:13px;padding:6px 0;border-bottom:0.5px solid var(--border);}
.history-row:last-child{border-bottom:none;}
.history-row .s{color:var(--text3);font-size:12px;}
.badge{display:inline-block;font-size:10px;padding:1px 6px;border-radius:8px;margin-left:4px;font-weight:700;vertical-align:1px;}
.badge-top{background:var(--green-bg);color:var(--green);}
.badge-bot{background:var(--red-bg);color:var(--red);}
.bar{height:8px;border-radius:4px;background:var(--bg3);overflow:hidden;}
.bar div{height:100%;border-radius:4px;}
.bar-row{margin-bottom:10px;}
.bar-row .top-line{display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;font-weight:700;}
.year-block{margin-bottom:20px;}
.matrix-wrap{overflow-x:auto;margin:0 -4px;}
.matrix{border-collapse:separate;border-spacing:2px;font-size:11px;margin:0 auto;}
.matrix th{font-weight:700;color:var(--text2);padding:2px;white-space:nowrap;}
.matrix thead th{writing-mode:vertical-rl;text-orientation:upright;height:44px;vertical-align:bottom;letter-spacing:-0.05em;}
.matrix tbody th{text-align:right;padding-right:6px;}
.matrix td{width:30px;height:34px;min-width:30px;text-align:center;border-radius:6px;cursor:pointer;line-height:1;}
.matrix td .fe{display:block;font-size:16px;}
.matrix td .fn{display:block;font-size:8px;color:var(--text2);margin-top:2px;font-variant-numeric:tabular-nums;}
.face-legend{font-size:11px;color:var(--text2);margin-bottom:8px;line-height:1.8;}
.awards{display:grid;grid-template-columns:1fr;gap:8px;}
.award{border-radius:14px;padding:12px 14px;background:var(--bg2);position:relative;overflow:hidden;}
.award .ic{font-size:26px;position:absolute;right:12px;top:10px;opacity:0.9;}
.award .lb{font-size:11px;font-weight:700;color:var(--text3);letter-spacing:0.04em;}
.award .who{font-size:17px;font-weight:800;margin-top:4px;padding-right:36px;}
.award .who .vs{font-size:12px;color:var(--text3);font-weight:600;margin:0 4px;}
.award .cm{font-size:12px;color:var(--text2);margin-top:4px;line-height:1.6;}
.award .st{font-size:11px;color:var(--text3);margin-top:6px;}
.mini-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:12px;}
.mini{background:var(--bg2);border-radius:10px;padding:8px;text-align:center;}
.mini .e{font-size:20px;}
.mini .n{font-size:13px;font-weight:800;margin-top:2px;}
.mini .r{font-size:11px;color:var(--text3);font-variant-numeric:tabular-nums;}
.aisho-group{font-size:12px;font-weight:700;margin:12px 0 6px;}
details.more{margin-top:10px;}
details.more summary{font-size:12px;color:var(--text2);cursor:pointer;padding:6px 0;}
.matrix td.self{background:var(--bg3);cursor:default;}
.matrix td.few{color:var(--text3);background:var(--bg2);font-weight:400;}
.matrix td.sel{outline:2px solid var(--text);outline-offset:-1px;}
.aisho-pick{margin-top:10px;padding:10px 12px;background:var(--bg2);border-radius:10px;font-size:13px;line-height:1.6;min-height:44px;color:var(--text2);}
.aisho-pick b{color:var(--text);}
.dv{position:relative;height:8px;border-radius:4px;background:var(--bg3);}
.dv::after{content:"";position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--border2);}
.dv div{position:absolute;top:0;bottom:0;border-radius:4px;}
.year-title{font-size:13px;font-weight:700;color:var(--text2);margin-bottom:6px;}
</style>
</head>
<body>
<div class="app">
  <div class="top">
    <div class="header">
      <h1>🀄 麻雀スコア</h1>
      <div class="meta num">全__SESSION_COUNT__セッション · __DATE_RANGE__</div>
      <div class="meta num" style="color:var(--text3);font-size:11px">更新 __UPDATED_AT__</div>
    </div>
    <div class="tabs" id="tabs">
      <button class="tab active" data-page="ranking">ランキング</button>
      <button class="tab" data-page="recent">直近成績</button>
      <button class="tab" data-page="trend">推移</button>
      <button class="tab" data-page="stats">統計</button>
      <button class="tab" data-page="yearly">年度別</button>
      <button class="tab" data-page="aisho">相性</button>
      <button class="tab" data-page="history">履歴</button>
    </div>
  </div>
  <div class="content">
    <div id="page-ranking" class="page show">
      <div id="overview-view">
        <div class="section"><div class="section-title"><span>総合収支ランキング</span><span class="hint">タップで個人成績</span></div><div class="list" id="ranking-list"></div></div>
      </div>
      <div id="detail-view" class="hidden">
        <button class="back-btn" id="back-btn">← 一覧へ戻る</button>
        <div class="section"><div class="grid2" id="detail-metrics"></div></div>
        <div class="section"><div class="section-title">直近10半荘の着順（右が最新）</div><div class="form" id="detail-form"></div></div>
        <div class="section"><div class="section-title">対戦成績詳細</div><div id="detail-stats"></div></div>
        <div class="section"><div class="section-title">収支の累計推移</div><div class="chart-wrap"><canvas id="detailChart"></canvas></div></div>
        <div class="section"><div class="section-title"><span>🔮 相性診断</span></div><div id="detail-aisho"></div></div>
        <div class="section"><div class="section-title">年度別収支</div><div id="detail-yearly"></div></div>
      </div>
    </div>

    <div id="page-recent" class="page">
      <div class="section">
        <div class="controls">
          <div class="seg" id="recent-n"><button data-v="10" class="on">直近10</button><button data-v="30">30</button><button data-v="50">50</button><button data-v="0">全部</button></div>
          <div class="seg" id="recent-unit"><button data-v="game" class="on">半荘</button><button data-v="session">セッション</button></div>
        </div>
      </div>
      <div class="section">
        <div class="section-title"><span id="recent-title"></span>
          <span class="seg" id="recent-sort" style="font-size:12px"><button data-v="pay" class="on">収支</button><button data-v="avg">着順</button><button data-v="chip">チップ</button></span>
        </div>
        <div class="list" id="recent-list"></div>
        <p class="note" id="recent-note"></p>
      </div>
    </div>

    <div id="page-trend" class="page">
      <div class="section">
        <div class="section-title"><span>累計収支の推移（円）</span></div>
        <div class="legend-actions"><button class="linkbtn" data-legend-all="trend">全員表示</button><button class="linkbtn" data-legend-top="trend">参加の多い6人</button></div>
        <div class="legend" id="trend-legend"></div>
        <div class="chart-wrap" style="height:300px"><canvas id="trendChart"></canvas></div>
      </div>
      <div class="section"><div class="section-title">セッション別 最高 / 最低収支</div><div class="chart-wrap" style="height:240px"><canvas id="sessionChart"></canvas></div></div>
    </div>

    <div id="page-stats" class="page">
      <div class="section"><div class="section-title"><span>プレイヤー別成績</span><span class="hint">着順率は半荘単位</span></div><div class="list" id="stats-list"></div></div>
      <div class="section"><div class="section-title">累計チップ</div><div id="chip-stats"></div></div>
      <div class="section"><div class="section-title">着順率（半荘単位）</div><div class="chart-wrap" id="winChartWrap"><canvas id="winChart"></canvas></div></div>
      <div class="section"><div class="section-title">平均着順（低いほど良い）</div><div class="chart-wrap" id="avgChartWrap"><canvas id="avgRankChart"></canvas></div></div>
    </div>

    <div id="page-yearly" class="page">
      <div class="section"><div class="section-title">年度別収支</div><div id="yearly-content"></div></div>
    </div>

    <div id="page-aisho" class="page">
      <div class="section">
        <div class="section-title"><span>🔮 今日の相性診断</span></div>
        <div class="awards" id="aisho-awards"></div>
      </div>
      <div class="section">
        <div class="section-title"><span>相性マップ</span><span class="hint">タップで詳しく</span></div>
        <div class="face-legend">😎 カモにしてる　😊 得意　😐 互角　😓 ちょい苦手　😱 天敵</div>
        <div class="matrix-wrap"><table class="matrix" id="aisho-matrix"></table></div>
        <div class="aisho-pick" id="aisho-pick">👆 気になる組み合わせをタップ！（行の人から見た相性です）</div>
        <p class="note" id="aisho-note"></p>
      </div>
      <div class="section"><div class="section-title"><span>🦆 天敵とお得意様の関係</span><span class="hint">同卓20局以上</span></div><div class="list" id="aisho-pairs"></div></div>
    </div>

    <div id="page-history" class="page">
      <div class="section"><div class="section-title">対戦履歴（新しい順）</div><div class="list" id="history-list"></div></div>
    </div>
  </div>
</div>
<script>
const DATA = __DATA__;

// ---------- 共通 ----------
const BASE_COLORS = {'南':'#378ADD','林':'#1D9E75','関河':'#D85A30','古川':'#D4537E','熊坂':'#7F77DD','矢田':'#BA7517','西村':'#8A8A82','鎌田':'#639922','藤田':'#B0472A'};
const EXTRA_COLORS = ['#0F9DAA','#C23B8E','#5B6CD6','#A0861A','#2F8F4E','#E0703A','#7A5BC4','#3A86A8','#B5566E','#4E9A2A','#C77D16','#6B6BB5'];
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const yen = n => (n > 0 ? '+' : n < 0 ? '−' : '±') + Math.abs(n).toLocaleString();
const sgn = n => (n > 0 ? '+' : n < 0 ? '−' : '±') + Math.abs(Math.round(n * 10) / 10);
const cls = n => n > 0 ? 'pos' : n < 0 ? 'neg' : 'zero';
const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

// ---------- 集計 ----------
// プレイヤーごとの半荘・セッション明細（古い順）
const P = {};
function ensure(p) {
  return P[p] || (P[p] = {name: p, games: [], sessions: []});
}
// H[a][b]: aがbと同卓した半荘での成績（n=同卓数, win=aがbより上の回数, rsum=aの着順合計, pay=aの収支）
const H = {};
function pair(a, b) {
  H[a] = H[a] || {};
  return H[a][b] || (H[a][b] = {n: 0, win: 0, rsum: 0, pay: 0});
}
const PAIR_MIN = 10; // これ未満の同卓数は参考外
function ranksOf(arr) { // 大きい順の順位（同点は同順位）
  return arr.map(v => 1 + arr.filter(x => x > v).length);
}
DATA.forEach((s, si) => {
  const n = s.players.length;
  const pay = Array(n).fill(0), sc = Array(n).fill(0);
  s.games.forEach((g, gi) => {
    const rk = ranksOf(g.sc);
    s.players.forEach((p, i) => {
      pay[i] += g.pay[i]; sc[i] += g.sc[i];
      ensure(p).games.push({si, date: s.date, rank: rk[i], sc: g.sc[i], pay: g.pay[i],
        chip: gi === 0 ? s.chips[i] : 0, tobi: g.pt[i] < 0 ? 1 : 0});
      // 相性：同卓した相手ごとの対戦成績
      s.players.forEach((q, j) => {
        if (i === j) return;
        const h = pair(p, q);
        h.n++; h.rsum += rk[i]; h.pay += g.pay[i];
        h.win += g.sc[i] > g.sc[j] ? 1 : g.sc[i] === g.sc[j] ? 0.5 : 0;
      });
    });
  });
  s.pay = pay; s.sc = sc.map(v => Math.round(v * 10) / 10);
  const srk = ranksOf(s.sc);
  s.players.forEach((p, i) => {
    ensure(p).sessions.push({si, date: s.date, rank: srk[i], sc: s.sc[i], pay: pay[i], chip: s.chips[i], games: s.games.length});
  });
});

// 半荘明細から成績をまとめる
function summarize(games) {
  const r = {n: games.length, pay: 0, chip: 0, sc: 0, tobi: 0, rk: {1:0,2:0,3:0,4:0}, rsum: 0};
  games.forEach(g => {
    r.pay += g.pay; r.chip += g.chip; r.sc += g.sc; r.tobi += g.tobi;
    r.rk[g.rank] = (r.rk[g.rank] || 0) + 1; r.rsum += g.rank;
  });
  r.avg = r.n ? r.rsum / r.n : 0;
  return r;
}

const ALL = {};
Object.values(P).forEach(p => { ALL[p.name] = summarize(p.games); ALL[p.name].sessions = p.sessions.length; });
const players = Object.keys(P).sort((a, b) => ALL[b].pay - ALL[a].pay);

// 色：既定色＋参加数の多い順に追加色
const COLORS = Object.assign({}, BASE_COLORS);
let ci = 0;
Object.keys(P).sort((a, b) => P[b].games.length - P[a].games.length).forEach(p => {
  if (!COLORS[p]) COLORS[p] = EXTRA_COLORS[ci++ % EXTRA_COLORS.length];
});
const col = p => COLORS[p] || '#888888';

function avatar(p, size) {
  const st = size ? 'width:' + size + 'px;height:' + size + 'px;font-size:' + Math.round(size * 0.4) + 'px;' : '';
  return '<div class="avatar" style="' + st + 'background:' + col(p) + '22;color:' + col(p) + '">' + esc(p[0]) + '</div>';
}
function chipPill(c) {
  return '<span class="chip-pill num ' + cls(c) + '">チップ ' + sgn(c) + '枚</span>';
}
function rankNum(i) {
  return '<div class="rank-num num ' + (i < 3 ? 'r' + (i + 1) : '') + '">' + (i + 1) + '</div>';
}

// ---------- Chart.js 共通設定 ----------
const charts = {};
function chartBase() {
  Chart.defaults.color = css('--text2');
  Chart.defaults.borderColor = css('--border');
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
}
function makeChart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  chartBase();
  charts[id] = new Chart(document.getElementById(id), cfg);
  return charts[id];
}
const yenAxis = {ticks: {callback: v => v.toLocaleString()}};
const dateTicks = {maxRotation: 0, autoSkip: true, autoSkipPadding: 16, maxTicksLimit: 5};

// ---------- タブ ----------
const rendered = {};
function showPage(name) {
  document.querySelectorAll('.page').forEach(el => el.classList.toggle('show', el.id === 'page-' + name));
  document.querySelectorAll('.tab').forEach(el => el.classList.toggle('active', el.dataset.page === name));
  if (name === 'ranking') showOverview();
  const fn = {recent: renderRecent, trend: renderTrend, stats: renderStats, yearly: renderYearly, aisho: renderAisho, history: renderHistory}[name];
  if (fn && !rendered[name]) { fn(); rendered[name] = true; }
  window.scrollTo(0, 0);
}
document.getElementById('tabs').addEventListener('click', e => {
  const b = e.target.closest('.tab'); if (b) showPage(b.dataset.page);
});

// ---------- ランキング ----------
function renderRanking() {
  document.getElementById('ranking-list').innerHTML = players.map((p, i) => {
    const a = ALL[p];
    return '<div class="row click" data-player="' + esc(p) + '">' + rankNum(i) + avatar(p) +
      '<div class="info"><div class="name">' + esc(p) + '</div><div class="sub num">' + a.sessions + '回 · ' + a.n + '半荘 · 平均' + a.avg.toFixed(2) + '着</div></div>' +
      '<div class="right"><div class="amount num ' + cls(a.pay) + '">' + yen(a.pay) + '<small>円</small></div>' + chipPill(a.chip) + '</div></div>';
  }).join('');
}
document.getElementById('ranking-list').addEventListener('click', e => {
  const r = e.target.closest('[data-player]'); if (r) showDetail(r.dataset.player);
});
document.getElementById('back-btn').addEventListener('click', showOverview);

function showOverview() {
  document.getElementById('detail-view').classList.add('hidden');
  document.getElementById('overview-view').classList.remove('hidden');
}

function byYear(list) {
  const y = {};
  list.forEach(s => { const k = s.date.slice(0, 4); y[k] = (y[k] || 0) + s.pay; });
  return y;
}
function barRows(entries, colorFn) {
  const max = Math.max(1, ...entries.map(e => Math.abs(e.v)));
  return entries.map(e =>
    '<div class="bar-row"><div class="top-line"><span style="color:' + (colorFn ? colorFn(e) : 'var(--text2)') + '">' + esc(e.label) + '</span><span class="num ' + cls(e.v) + '">' + e.text + '</span></div>' +
    '<div class="bar"><div style="width:' + (Math.abs(e.v) / max * 100) + '%;background:var(--' + (e.v >= 0 ? 'green' : 'red') + ')"></div></div></div>'
  ).join('');
}

function showDetail(p) {
  document.getElementById('overview-view').classList.add('hidden');
  document.getElementById('detail-view').classList.remove('hidden');
  window.scrollTo(0, 0);
  const a = ALL[p], ss = P[p].sessions, gs = P[p].games;
  const metric = (label, val, sub, c) => '<div class="metric"><div class="metric-label">' + label + '</div><div class="metric-value num ' + (c || '') + '">' + val + '</div><div class="metric-sub">' + sub + '</div></div>';
  document.getElementById('detail-metrics').innerHTML =
    metric(esc(p) + 'の総収支', yen(a.pay), '円', cls(a.pay)) +
    metric('累計チップ', sgn(a.chip), '枚', cls(a.chip)) +
    metric('参加', a.sessions, 'セッション / ' + a.n + '半荘') +
    metric('平均着順', a.avg.toFixed(2), '位（半荘単位）');

  document.getElementById('detail-form').innerHTML = gs.slice(-10).map(g => '<span class="num f' + g.rank + '" title="' + g.date + '">' + g.rank + '</span>').join('');

  const pays = ss.map(s => s.pay);
  const sr = {1:0,2:0,3:0,4:0}; ss.forEach(s => sr[s.rank]++);
  const row = (l, v, c) => '<div class="stat-row"><span class="stat-label">' + l + '</span><span class="stat-val num ' + (c || '') + '">' + v + '</span></div>';
  const medal = ['', '🥇', '🥈', '🥉', '💀'];
  let h = '<div class="stat-group">半荘単位</div>';
  for (let r = 1; r <= 4; r++) h += row(medal[r] + ' ' + r + '着率', pct(a.rk[r], a.n) + '%（' + a.rk[r] + '回）');
  h += row('飛び率', pct(a.tobi, a.n) + '%（' + a.tobi + '回）', a.tobi ? 'neg' : '');
  h += row('累計スコア', sgn(a.sc));
  h += '<div class="stat-group">セッション単位</div>';
  for (let r = 1; r <= 4; r++) h += row(medal[r] + ' ' + r + '位率', pct(sr[r], ss.length) + '%（' + sr[r] + '回）');
  h += row('最高収支', yen(Math.max(...pays)) + '円', 'pos');
  h += row('最低収支', yen(Math.min(...pays)) + '円', 'neg');
  document.getElementById('detail-stats').innerHTML = h;

  let acc = 0;
  makeChart('detailChart', {
    type: 'line',
    data: {labels: ss.map(s => s.date.slice(2)), datasets: [{data: ss.map(s => acc += s.pay), borderColor: col(p), backgroundColor: col(p) + '22', fill: true, tension: 0.25, pointRadius: 3, borderWidth: 2}]},
    options: {responsive: true, maintainAspectRatio: false, plugins: {legend: {display: false}}, scales: {y: yenAxis, x: {ticks: dateTicks}}}
  });

  const y = byYear(ss);
  document.getElementById('detail-aisho').innerHTML = aishoRows(p);
  document.getElementById('detail-yearly').innerHTML = barRows(Object.keys(y).sort().map(k => ({label: k + '年', v: y[k], text: yen(y[k]) + '円'})));
}

// ---------- 直近成績 ----------
const recentState = {n: 10, unit: 'game', sort: 'pay'};
function bindSeg(id, key, cast) {
  document.getElementById(id).addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    e.currentTarget.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    recentState[key] = cast ? cast(b.dataset.v) : b.dataset.v;
    renderRecent();
  });
}
bindSeg('recent-n', 'n', Number); bindSeg('recent-unit', 'unit'); bindSeg('recent-sort', 'sort');

function renderRecent() {
  const {n, unit, sort} = recentState;
  const unitLabel = unit === 'game' ? '半荘' : 'セッション';
  const rows = Object.keys(P).map(p => {
    let r;
    if (unit === 'game') {
      const g = n ? P[p].games.slice(-n) : P[p].games;
      r = summarize(g); r.count = g.length; r.from = g.length ? g[0].date : '';
    } else {
      const s = n ? P[p].sessions.slice(-n) : P[p].sessions;
      r = {pay: 0, chip: 0, rk: {1:0,2:0,3:0,4:0}, rsum: 0, count: s.length, from: s.length ? s[0].date : ''};
      s.forEach(x => { r.pay += x.pay; r.chip += x.chip; r.rk[x.rank]++; r.rsum += x.rank; });
      r.avg = r.count ? r.rsum / r.count : 0;
    }
    r.name = p; r.full = !n || r.count >= n;
    return r;
  });
  const key = {pay: (a, b) => b.pay - a.pay, avg: (a, b) => a.avg - b.avg, chip: (a, b) => b.chip - a.chip}[sort];
  rows.sort((a, b) => (b.full - a.full) || key(a, b));

  document.getElementById('recent-title').textContent = (n ? '直近' + n + unitLabel : '全期間') + 'の成績';
  document.getElementById('recent-list').innerHTML = rows.map((r, i) => {
    const short = !r.full;
    return '<div class="row" style="' + (short ? 'opacity:0.55' : '') + '">' + rankNum(i) + avatar(r.name) +
      '<div class="info"><div class="name">' + esc(r.name) + '</div>' +
      '<div class="sub num">' + r.count + unitLabel + (short ? '（不足）' : '') + ' · 平均' + r.avg.toFixed(2) + ' · トップ' + pct(r.rk[1], r.count) + '% · ラス' + pct(r.rk[4], r.count) + '%</div></div>' +
      '<div class="right"><div class="amount num ' + cls(r.pay) + '">' + yen(r.pay) + '<small>円</small></div>' + chipPill(r.chip) + '</div></div>';
  }).join('');
  document.getElementById('recent-note').textContent = n
    ? '各プレイヤー本人の直近' + n + unitLabel + 'で集計しています。' + n + unitLabel + 'に満たないプレイヤーは薄く表示し、下にまとめています。'
      + (unit === 'game' ? 'チップはセッション単位の記録のため、そのセッションの1半荘目が範囲に入っている場合に加算しています。' : '')
    : '全期間の成績です。';
}

// ---------- 推移 ----------
const legendState = {};
function topPlayers(k) {
  return Object.keys(P).sort((a, b) => P[b].sessions.length - P[a].sessions.length).slice(0, k);
}
function renderLegend(id, chartId) {
  const vis = legendState[chartId];
  document.getElementById(id).innerHTML = players.map(p =>
    '<button data-p="' + esc(p) + '" class="' + (vis.has(p) ? '' : 'off') + '"><span class="dot" style="background:' + col(p) + '"></span>' + esc(p) + '</button>').join('');
}
function applyLegend(chartId) {
  const c = charts[chartId], vis = legendState[chartId];
  c.data.datasets.forEach(d => d.hidden = !vis.has(d.label));
  c.update();
  renderLegend('trend-legend', chartId);
}
document.getElementById('trend-legend').addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  const vis = legendState.trendChart;
  vis.has(b.dataset.p) ? vis.delete(b.dataset.p) : vis.add(b.dataset.p);
  applyLegend('trendChart');
});
document.querySelector('[data-legend-all]').addEventListener('click', () => { legendState.trendChart = new Set(players); applyLegend('trendChart'); });
document.querySelector('[data-legend-top]').addEventListener('click', () => { legendState.trendChart = new Set(topPlayers(6)); applyLegend('trendChart'); });

function renderTrend() {
  legendState.trendChart = legendState.trendChart || new Set(topPlayers(6));
  const labels = DATA.map(s => s.date.slice(2));
  const datasets = players.map(p => {
    let acc = 0;
    const data = DATA.map(s => {
      const i = s.players.indexOf(p);
      if (i < 0) return null;
      return acc += s.pay[i];
    });
    return {label: p, data, borderColor: col(p), backgroundColor: col(p), tension: 0.25, pointRadius: 2, borderWidth: 2, spanGaps: true, hidden: !legendState.trendChart.has(p)};
  });
  makeChart('trendChart', {
    type: 'line', data: {labels, datasets},
    options: {responsive: true, maintainAspectRatio: false, interaction: {mode: 'nearest', intersect: false},
      plugins: {legend: {display: false}, tooltip: {callbacks: {label: c => c.dataset.label + ' ' + yen(c.parsed.y) + '円'}}},
      scales: {y: yenAxis, x: {ticks: dateTicks}}}
  });
  renderLegend('trend-legend', 'trendChart');

  makeChart('sessionChart', {
    type: 'bar',
    data: {labels, datasets: [
      {label: '最高収支', data: DATA.map(s => Math.max(...s.pay)), backgroundColor: css('--green') + 'aa', borderRadius: 2},
      {label: '最低収支', data: DATA.map(s => Math.min(...s.pay)), backgroundColor: css('--red') + 'aa', borderRadius: 2}]},
    options: {responsive: true, maintainAspectRatio: false, plugins: {legend: {display: false}}, scales: {y: yenAxis, x: {stacked: true, ticks: dateTicks}}}
  });
}

// ---------- 統計 ----------
function renderStats() {
  document.getElementById('stats-list').innerHTML = players.map((p, i) => {
    const a = ALL[p];
    return '<div class="row">' + rankNum(i) + avatar(p) +
      '<div class="info"><div class="name">' + esc(p) + '</div><div class="sub num">🥇' + pct(a.rk[1], a.n) + '% 🥈' + pct(a.rk[2], a.n) + '% 🥉' + pct(a.rk[3], a.n) + '% 💀' + pct(a.rk[4], a.n) + '% · 飛' + pct(a.tobi, a.n) + '%</div></div>' +
      '<div class="right"><div class="amount num">' + a.avg.toFixed(2) + '<small>位</small></div><div class="sub">' + a.n + '半荘</div></div></div>';
  }).join('');

  const chips = players.slice().sort((a, b) => ALL[b].chip - ALL[a].chip);
  document.getElementById('chip-stats').innerHTML = barRows(chips.map(p => ({label: p, v: ALL[p].chip, text: sgn(ALL[p].chip) + '枚'})), e => col(e.label));

  const h = Math.max(220, players.length * 24 + 70);
  document.getElementById('winChartWrap').style.height = h + 'px';
  document.getElementById('avgChartWrap').style.height = h + 'px';
  const rateSet = (r, label, color) => ({label, data: players.map(p => pct(ALL[p].rk[r], ALL[p].n)), backgroundColor: color, borderRadius: 2});
  makeChart('winChart', {
    type: 'bar',
    data: {labels: players, datasets: [rateSet(1, '1着', css('--green')), rateSet(2, '2着', css('--silver') + 'aa'), rateSet(3, '3着', css('--silver') + '66'), rateSet(4, '4着', css('--red'))]},
    options: {responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: {legend: {position: 'bottom', labels: {boxWidth: 12}}, tooltip: {callbacks: {label: c => c.dataset.label + ' ' + c.parsed.x + '%'}}},
      scales: {x: {stacked: true, max: 100, ticks: {callback: v => v + '%'}}, y: {stacked: true}}}
  });
  const byAvg = players.slice().sort((a, b) => ALL[a].avg - ALL[b].avg);
  makeChart('avgRankChart', {
    type: 'bar',
    data: {labels: byAvg, datasets: [{data: byAvg.map(p => +ALL[p].avg.toFixed(2)), backgroundColor: byAvg.map(p => col(p) + 'bb'), borderRadius: 3}]},
    options: {responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: {legend: {display: false}}, scales: {x: {min: 1, max: 4, ticks: {callback: v => v + '位'}}}}
  });
}

// ---------- 相性 ----------
const winRate = h => h.n ? h.win / h.n : 0;
const FACES = [[0.65, '😎', 'カモにしてる'], [0.56, '😊', '得意'], [0.445, '😐', '互角'], [0.35, '😓', 'ちょい苦手'], [-1, '😱', '天敵']];
const face = w => FACES.find(f => w >= f[0]);
function aishoColor(w) { // 50%を中心に緑（得意）/赤（苦手）。顔文字が読めるよう薄めに
  const a = Math.min(1, Math.abs(w - 0.5) / 0.25);
  const hex = Math.round(0x14 + a * (0x66 - 0x14)).toString(16).padStart(2, '0');
  return css(w >= 0.5 ? '--green' : '--red') + hex;
}
// 名前の組み合わせで決まる擬似乱数（再読み込みしてもコメントが変わらないように）
function seedOf(s) { let h = 0; for (const ch of s) h = (h * 31 + ch.codePointAt(0)) >>> 0; return h; }
const pick = (arr, key) => arr[seedOf(key) % arr.length];
const san = p => esc(p) + 'さん';
// g が l より上になりやすい関係へのひとこと
function quip(g, l, w) {
  const G = san(g), L = san(l);
  const t = w >= 0.68 ? [
    L + '、' + G + 'の前だと借りてきた猫🐱',
    G + 'にとって' + L + 'との卓はボーナスステージ🎰',
    L + 'の点棒、' + G + 'の財布に直行中💸',
    G + 'が' + L + 'を見つけると目の色が変わる👀',
  ] : w >= 0.6 ? [
    G + '、' + L + 'と同卓だとちょっとニヤけてる説',
    L + '、そろそろ' + G + '対策を練るべき🤔',
    G + 'の機嫌が良い日は、だいたい' + L + 'がいる',
    L + '、' + G + 'の待ちだけは読めない模様',
  ] : [
    G + 'がわずかにリード。まだまだ逆転ある！',
    'ほぼ互角だけど、' + G + 'がちょっとだけ上手',
  ];
  return pick(t, g + l);
}
function opponents(p, min) {
  return Object.keys(H[p] || {}).map(q => ({q, h: H[p][q], w: winRate(H[p][q])})).filter(o => o.h.n >= (min || PAIR_MIN));
}
function allPairs(min) {
  const list = [];
  Object.keys(H).forEach(a => Object.keys(H[a]).forEach(b => {
    if (a < b && H[a][b].n >= min) list.push({a, b, h: H[a][b], w: winRate(H[a][b])});
  }));
  return list;
}
function award(icon, label, who, comment, stat) {
  return '<div class="award"><div class="ic">' + icon + '</div><div class="lb">' + label + '</div><div class="who">' + who + '</div>' +
    '<div class="cm">' + comment + '</div><div class="st num">' + stat + '</div></div>';
}
const nm = p => '<span style="color:' + col(p) + '">' + esc(p) + '</span>';

// 個人画面：お得意様・天敵・ライバルのカード＋全員との相性（折りたたみ）
function aishoRows(p) {
  const ok = opponents(p).sort((a, b) => b.w - a.w);
  const few = Object.keys(H[p] || {}).filter(q => H[p][q].n < PAIR_MIN);
  if (!ok.length) return '<p class="note">同卓' + PAIR_MIN + '局以上の相手がまだいません。もっと打ちましょう🀄</p>';
  const best = ok[0], worst = ok[ok.length - 1];
  const rival = ok.slice().sort((a, b) => (Math.abs(a.w - 0.5) - Math.abs(b.w - 0.5)) || (b.h.n - a.h.n))[0];
  const mini = (e, label, o) => '<div class="mini"><div class="e">' + e + '</div><div class="r">' + label + '</div><div class="n">' + nm(o.q) + '</div><div class="r">' + Math.round(o.w * 100) + '% · ' + o.h.n + '局</div></div>';
  let html = '<div class="mini-cards">' + mini('🦆', 'お得意様', best) + mini('😱', '天敵', worst) + mini('⚔️', 'ライバル', rival) + '</div>';
  html += '<p class="note" style="margin-top:0">' + (best.w > 0.55 ? '・' + quip(p, best.q, best.w) + '<br>' : '') +
    (worst.w < 0.45 ? '・' + quip(worst.q, p, 1 - worst.w) : '') + '</p>';

  const base = ALL[p].avg;
  const rows = ok.map(o => {
    const avg = o.h.rsum / o.h.n, diff = base - avg, f = face(o.w);
    const left = o.w >= 0.5 ? 50 : o.w * 100, width = Math.abs(o.w - 0.5) * 100;
    return '<div class="bar-row"><div class="top-line"><span>' + f[1] + ' ' + nm(o.q) +
      ' <span style="color:var(--text3);font-weight:400;font-size:11px">' + o.h.n + '局 · 平均' + avg.toFixed(2) + '着（' + (diff >= 0 ? '+' : '−') + Math.abs(diff).toFixed(2) + '）· ' + yen(o.h.pay) + '円</span></span>' +
      '<span class="num ' + (o.w > 0.5 ? 'pos' : o.w < 0.5 ? 'neg' : 'zero') + '">' + Math.round(o.w * 100) + '%</span></div>' +
      '<div class="dv"><div style="left:' + left + '%;width:' + width + '%;background:var(--' + (o.w >= 0.5 ? 'green' : 'red') + ')"></div></div></div>';
  }).join('');
  html += '<details class="more"><summary>全員との相性を見る（' + ok.length + '人）</summary>' + rows +
    '<p class="note">％は同じ卓で打った半荘のうち' + san(p) + 'が相手より上の着順だった割合（50%で互角）。カッコ内は通算の平均着順との差で、＋ならその相手がいると調子が良い。' +
    (few.length ? '同卓' + PAIR_MIN + '局未満（' + few.map(esc).join('・') + '）は省略。' : '') + '</p></details>';
  return html;
}

function renderAisho() {
  const regs = players.filter(p => ALL[p].n >= 30).sort((a, b) => ALL[b].n - ALL[a].n);

  // --- 診断カード ---
  const cards = [];
  const strong = allPairs(20).sort((x, y) => Math.abs(y.w - 0.5) - Math.abs(x.w - 0.5))[0];
  if (strong) {
    const [g, l, w] = strong.w >= 0.5 ? [strong.a, strong.b, strong.w] : [strong.b, strong.a, 1 - strong.w];
    cards.push(award('😱', '最恐の天敵コンビ', nm(g) + '<span class="vs">→</span>' + nm(l), quip(g, l, w),
      '同卓' + strong.h.n + '局で' + esc(g) + 'が上だったのは' + Math.round(w * strong.h.n) + '回（' + Math.round(w * 100) + '%）'));
  }
  const rival = allPairs(50).sort((x, y) => (Math.abs(x.w - 0.5) - Math.abs(y.w - 0.5)) || (y.h.n - x.h.n))[0];
  if (rival) {
    const wa = Math.round(rival.h.win), wb = rival.h.n - wa;
    cards.push(award('⚔️', '宿命のライバル', nm(rival.a) + '<span class="vs">vs</span>' + nm(rival.b),
      rival.h.n + '局戦ってもほぼ五分。決着の日は来るのか…', esc(rival.a) + 'が上 ' + wa + '回 / ' + esc(rival.b) + 'が上 ' + wb + '回'));
  }
  // 卓の支配者：勝ち越している相手の割合が最も高い人
  const dom = regs.map(p => { const o = opponents(p); return {p, o, m: o.filter(x => x.w > 0.5).length}; })
    .filter(x => x.o.length >= 4).sort((a, b) => (b.m / b.o.length - a.m / a.o.length) || (b.m - a.m))[0];
  if (dom) cards.push(award('👑', '卓の支配者', nm(dom.p), '同卓した相手のほとんどに勝ち越し。この人がいる卓は覚悟して！',
    dom.o.length + '人中' + dom.m + '人に勝ち越し'));
  // みんなのお得意様：対戦相手から見た勝率（同卓数で加重）が最も高い人
  const kamo = regs.map(p => {
    const o = opponents(p); const n = o.reduce((s, x) => s + x.h.n, 0);
    return {p, n, w: n ? o.reduce((s, x) => s + x.h.n * (1 - x.w), 0) / n : 0};
  }).filter(x => x.n >= 50).sort((a, b) => b.w - a.w)[0];
  if (kamo) cards.push(award('🦆', 'みんなのお得意様', nm(kamo.p), '卓に来てくれるとみんな笑顔に☺️ いつもありがとうございます！',
    '同卓相手が' + esc(kamo.p) + 'より上だった割合 平均' + Math.round(kamo.w * 100) + '%'));
  // ラッキーパーソン：その人がいると平均着順が一番良くなる組み合わせ
  let lucky = null;
  regs.forEach(p => opponents(p, 20).forEach(o => {
    const d = ALL[p].avg - o.h.rsum / o.h.n;
    if (!lucky || d > lucky.d) lucky = {p, q: o.q, d, n: o.h.n};
  }));
  if (lucky && lucky.d > 0.1) cards.push(award('🍀', 'ラッキーパーソン', nm(lucky.p) + '<span class="vs">にとっての</span>' + nm(lucky.q),
    san(lucky.q) + 'がいると' + san(lucky.p) + 'の調子が上がる！ 次も誘いましょう', '同卓' + lucky.n + '局で平均着順が' + lucky.d.toFixed(2) + '良くなる'));
  document.getElementById('aisho-awards').innerHTML = cards.join('');

  // --- 相性マップ ---
  let t = '<thead><tr><th></th>' + regs.map(q => '<th style="color:' + col(q) + '">' + esc(q) + '</th>').join('') + '</tr></thead><tbody>';
  regs.forEach(p => {
    t += '<tr><th style="color:' + col(p) + '">' + esc(p) + '</th>';
    regs.forEach(q => {
      if (p === q) { t += '<td class="self"></td>'; return; }
      const h = (H[p] || {})[q];
      if (!h || h.n < PAIR_MIN) { t += '<td class="few" data-a="' + esc(p) + '" data-b="' + esc(q) + '">' + (h ? '·' : '') + '</td>'; return; }
      const w = winRate(h);
      t += '<td data-a="' + esc(p) + '" data-b="' + esc(q) + '" style="background:' + aishoColor(w) + '"><span class="fe">' + face(w)[1] + '</span><span class="fn">' + Math.round(w * 100) + '</span></td>';
    });
    t += '</tr>';
  });
  document.getElementById('aisho-matrix').innerHTML = t + '</tbody>';
  document.getElementById('aisho-note').textContent = '半荘30局以上のメンバーで作っています。小さい数字は「行の人が列の人より上の着順だった割合（%）」。同卓' + PAIR_MIN + '局未満は「·」。全員との相性はランキングから各プレイヤーを開くと見られます。';

  // --- 天敵とお得意様 ---
  document.getElementById('aisho-pairs').innerHTML = allPairs(20).filter(x => Math.abs(x.w - 0.5) >= 0.1)
    .sort((x, y) => Math.abs(y.w - 0.5) - Math.abs(x.w - 0.5)).slice(0, 10).map(x => {
      const [g, l, w] = x.w >= 0.5 ? [x.a, x.b, x.w] : [x.b, x.a, 1 - x.w];
      return '<div class="row">' + avatar(g, 30) +
        '<div class="info"><div class="name" style="font-size:14px">' + nm(g) + ' <span style="color:var(--text3);font-weight:400">は</span> ' + nm(l) + ' <span style="color:var(--text3);font-weight:400">の天敵</span></div>' +
        '<div class="sub">' + quip(g, l, w) + '</div><div class="sub num" style="color:var(--text3)">同卓' + x.h.n + '局 · ' + Math.round(w * x.h.n) + '回上</div></div>' +
        '<div class="right"><div class="amount num pos">' + Math.round(w * 100) + '<small>%</small></div></div></div>';
    }).join('');
}
document.getElementById('aisho-matrix').addEventListener('click', e => {
  const td = e.target.closest('td[data-a]'); if (!td) return;
  document.querySelectorAll('.matrix td.sel').forEach(x => x.classList.remove('sel'));
  td.classList.add('sel');
  const a = td.dataset.a, b = td.dataset.b, h = (H[a] || {})[b], box = document.getElementById('aisho-pick');
  if (!h) { box.innerHTML = san(a) + 'と' + san(b) + 'はまだ同卓したことがありません。次回ぜひ！🀄'; return; }
  const w = winRate(h), hb = H[b][a], f = face(w);
  const line = w >= 0.5 ? quip(a, b, w) : quip(b, a, 1 - w);
  box.innerHTML = '<b>' + san(a) + '</b>から見た<b>' + san(b) + '</b>は… <b>' + f[1] + ' ' + f[2] + '</b>' + (h.n < PAIR_MIN ? '（データ少なめ）' : '') + '<br>' +
    line + '<br><span style="font-size:12px">同卓' + h.n + '局で' + esc(a) + 'が上 ' + Math.round(h.win) + '回（' + Math.round(w * 100) + '%） · 収支 ' + esc(a) + ' <span class="' + cls(h.pay) + '">' + yen(h.pay) + '円</span> / ' + esc(b) + ' <span class="' + cls(hb.pay) + '">' + yen(hb.pay) + '円</span></span>';
});

// ---------- 年度別 ----------
function renderYearly() {
  const y = {};
  DATA.forEach(s => { const k = s.date.slice(0, 4); y[k] = y[k] || {}; s.players.forEach((p, i) => y[k][p] = (y[k][p] || 0) + s.pay[i]); });
  document.getElementById('yearly-content').innerHTML = Object.keys(y).sort().reverse().map(k => {
    const ps = Object.keys(y[k]).sort((a, b) => y[k][b] - y[k][a]);
    return '<div class="year-block"><div class="year-title">' + k + '年</div><div class="list">' + ps.map((p, i) =>
      '<div class="row">' + rankNum(i) + avatar(p, 30) + '<div class="info"><div class="name" style="font-size:14px">' + esc(p) + '</div></div><div class="right"><div class="amount num ' + cls(y[k][p]) + '" style="font-size:15px">' + yen(y[k][p]) + '<small>円</small></div></div></div>').join('') + '</div></div>';
  }).join('');
}

// ---------- 履歴 ----------
function renderHistory() {
  document.getElementById('history-list').innerHTML = DATA.slice().reverse().map(s => {
    const maxP = Math.max(...s.pay), minP = Math.min(...s.pay);
    const order = s.players.map((p, i) => i).sort((a, b) => s.pay[b] - s.pay[a]);
    return '<div class="history-card"><div class="history-header"><span class="d num">' + s.date + '</span><span class="g">' + s.games.length + '半荘</span></div><div class="history-body">' +
      order.map(i => {
        const p = s.players[i], pay = s.pay[i];
        const badge = pay === maxP ? '<span class="badge badge-top">TOP</span>' : pay === minP ? '<span class="badge badge-bot">LAST</span>' : '';
        return '<div class="history-row"><span style="color:' + col(p) + ';font-weight:700">' + esc(p) + badge + '</span>' +
          '<span class="s num">スコア ' + sgn(s.sc[i]) + ' · チップ ' + sgn(s.chips[i]) + '</span>' +
          '<span class="num ' + cls(pay) + '" style="font-weight:700;text-align:right;min-width:72px">' + yen(pay) + '円</span></div>';
      }).join('') + '</div></div>';
  }).join('');
}

renderRanking();
// ダークモード切替時はグラフを描き直す
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  Object.keys(rendered).forEach(k => rendered[k] = false);
  const active = document.querySelector('.tab.active').dataset.page;
  if (active !== 'ranking') showPage(active);
});
</script>
</body>
</html>
"""


def generate_html(sessions, output_path):
    updated_at = datetime.now(JST).strftime('%Y/%m/%d %H:%M')
    date_range = (sessions[0]['date'] + ' 〜 ' + sessions[-1]['date']) if sessions else ''
    data_json = json.dumps(sessions, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = (TEMPLATE
            .replace('__SESSION_COUNT__', str(len(sessions)))
            .replace('__DATE_RANGE__', date_range)
            .replace('__UPDATED_AT__', updated_at)
            .replace('__DATA__', data_json))
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("✅ ダッシュボードを生成しました: " + output_path)
    print("   セッション数: " + str(len(sessions)))
    print("   期間: " + date_range)


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    score_dir = sys.argv[1] if len(sys.argv) >= 2 else os.path.join(here, 'SCORE')
    output_path = sys.argv[2] if len(sys.argv) >= 3 else os.path.join(here, 'mahjong_dashboard.html')

    if not os.path.isdir(score_dir):
        print("❌ フォルダが見つかりません: " + score_dir, file=sys.stderr)
        sys.exit(1)

    sessions = parse_csv_files(score_dir)
    if not sessions:
        print("⚠️ CSVが読み込めませんでした", file=sys.stderr)
        sys.exit(1)

    generate_html(sessions, output_path)
