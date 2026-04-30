#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麻雀スコアダッシュボード 自動生成スクリプト
"""
import csv, json, os, glob, sys
from datetime import datetime


def parse_csv_files(score_dir):
    sessions = []
    for filepath in glob.glob(os.path.join(score_dir, "*.csv")):
        try:
            with open(filepath, encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                if not rows:
                    continue
                headers = reader.fieldnames

                # プレイヤー名を抽出（末尾スペースをstripして判定）
                players = []
                for h in headers:
                    if h.strip().endswith('点数'):
                        p = h.strip().replace('点数', '').strip()
                        players.append(p)

                # ヘッダー名を strip して逆引きマップ
                key_map = {}
                for p in players:
                    key_map[p] = {}
                    for h in headers:
                        hs = h.strip()
                        if hs == p + ' スコア':
                            key_map[p]['score'] = h
                        elif hs == p + ' 収支':
                            key_map[p]['payout'] = h
                        elif hs == p + ' チップ':
                            key_map[p]['chip'] = h

                # 日付でグループ化
                date_groups = {}
                for row in rows:
                    date = row.get('日付', '').strip()
                    if date:
                        date_groups.setdefault(date, []).append(row)

                for date, date_rows in date_groups.items():
                    scores, payouts, chips_list = [], [], []
                    for p in players:
                        s_sum = p_sum = c_sum = 0
                        sk = key_map[p].get('score', '')
                        pk = key_map[p].get('payout', '')
                        ck = key_map[p].get('chip', '')
                        for i, row in enumerate(date_rows):
                            try: s_sum += float(row.get(sk, '') or 0)
                            except: pass
                            try: p_sum += int(row.get(pk, '') or 0)
                            except: pass
                            if i == 0:
                                try:
                                    cv = (row.get(ck, '') or '').strip()
                                    if cv and cv != '-':
                                        c_sum = int(cv)
                                except: pass
                        scores.append(round(s_sum))
                        payouts.append(p_sum)
                        chips_list.append(c_sum)
                    sessions.append({
                        'date': date, 'players': players[:],
                        'scores': scores, 'payouts': payouts,
                        'chips': chips_list, 'games': len(date_rows)
                    })
        except Exception as e:
            print(f"警告: {filepath}: {e}", file=sys.stderr)

    # === 重複セッションの除去 ===
    # 「日付・プレイヤー（ソート済み）・スコア合計」が同じものを重複とみなす
    seen = {}
    deduped = []
    removed = 0
    for sess in sessions:
        key = (
            sess['date'],
            tuple(sorted(sess['players'])),
            tuple(sorted(sess['scores']))
        )
        if key not in seen:
            seen[key] = True
            deduped.append(sess)
        else:
            removed += 1
    if removed:
        print(f"  重複セッションを {removed} 件スキップしました", file=sys.stderr)

    deduped.sort(key=lambda s: s['date'])
    return deduped


def generate_html(sessions, output_path):
    updated_at = datetime.now().strftime('%Y/%m/%d %H:%M')
    session_count = len(sessions)
    date_range = (sessions[0]['date'] + ' 〜 ' + sessions[-1]['date']) if sessions else ''
    sessions_json = json.dumps(sessions, ensure_ascii=False)

    # HTMLテンプレート（f-stringを使わずプレースホルダーで安全に組み立て）
    html_parts = []
    html_parts.append("""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🀄 麻雀スコアダッシュボード</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
:root{
  --bg:#fff;--bg2:#f5f5f3;--bg3:#eeede8;
  --text:#1a1a18;--text2:#6b6b67;--text3:#9b9b97;
  --border:rgba(0,0,0,0.1);--border2:rgba(0,0,0,0.2);
  --green:#1D9E75;--red:#D85A30;
}
@media(prefers-color-scheme:dark){
  :root{
    --bg:#1c1c1a;--bg2:#252523;--bg3:#2e2e2c;
    --text:#f0efe8;--text2:#9b9b97;--text3:#6b6b67;
    --border:rgba(255,255,255,0.1);--border2:rgba(255,255,255,0.2);
    --green:#5DCAA5;--red:#F0997B;
  }
}
body{font-family:-apple-system,'Hiragino Sans','Yu Gothic',sans-serif;background:var(--bg3);color:var(--text);}
.app{max-width:480px;margin:0 auto;background:var(--bg);min-height:100vh;}
.header{padding:1rem 1rem 0.75rem;background:var(--bg);border-bottom:0.5px solid var(--border);position:sticky;top:0;z-index:10;}
.header h1{font-size:20px;font-weight:600;}
.header p{font-size:12px;color:var(--text2);margin-top:2px;}
.updated{font-size:10px;color:var(--text3);margin-top:2px;}
.tabs{display:flex;gap:4px;padding:0.75rem 1rem;overflow-x:auto;scrollbar-width:none;border-bottom:0.5px solid var(--border);}
.tabs::-webkit-scrollbar{display:none;}
.tab{flex-shrink:0;font-size:13px;padding:6px 14px;border-radius:20px;border:0.5px solid var(--border2);cursor:pointer;color:var(--text2);background:transparent;transition:all 0.15s;font-family:inherit;}
.tab.active{background:var(--text);color:var(--bg);border-color:var(--text);}
.content{padding-bottom:2rem;}
.section{padding:1rem 1rem 0;}
.section-title{font-size:11px;font-weight:600;color:var(--text3);letter-spacing:0.08em;text-transform:uppercase;margin-bottom:0.75rem;}
.grid2{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;}
.metric{background:var(--bg2);border-radius:8px;padding:0.75rem 1rem;}
.metric-label{font-size:11px;color:var(--text2);margin-bottom:4px;}
.metric-value{font-size:22px;font-weight:600;color:var(--text);}
.metric-value.pos{color:var(--green);}.metric-value.neg{color:var(--red);}
.metric-sub{font-size:11px;color:var(--text3);margin-top:2px;}
.ranking{display:flex;flex-direction:column;gap:8px;}
.rank-row{display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--bg);border:0.5px solid var(--border);border-radius:12px;cursor:pointer;}
.rank-row:active{background:var(--bg2);}
.rank-num{font-size:14px;font-weight:600;color:var(--text3);width:20px;flex-shrink:0;text-align:center;}
.rank-num.gold{color:#BA7517;}.rank-num.silver{color:#888780;}.rank-num.bronze{color:#993C1D;}
.rank-avatar{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:600;flex-shrink:0;}
.rank-info{flex:1;min-width:0;}
.rank-name{font-size:15px;font-weight:600;color:var(--text);}
.rank-detail{font-size:11px;color:var(--text2);margin-top:1px;}
.rank-score{text-align:right;flex-shrink:0;}
.rank-score-val{font-size:16px;font-weight:600;}
.rank-score-sub{font-size:11px;color:var(--text2);}
.chart-wrap{position:relative;width:100%;height:240px;margin-top:0.5rem;}
.page{display:none;}.page.show{display:block;}
.detail-view{display:none;}.detail-view.show{display:block;}
.overview-view.hidden{display:none;}
.back-btn{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text2);background:none;border:none;cursor:pointer;padding:0.75rem 1rem 0.25rem;font-family:inherit;}
.stat-row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:0.5px solid var(--border);font-size:13px;}
.stat-row:last-child{border-bottom:none;}
.stat-label{color:var(--text2);}.stat-val{font-weight:600;color:var(--text);}
.stat-val.pos{color:var(--green);}.stat-val.neg{color:var(--red);}
.history-list{display:flex;flex-direction:column;gap:10px;}
.history-card{border:0.5px solid var(--border);border-radius:12px;overflow:hidden;}
.history-header{padding:8px 12px;background:var(--bg2);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;}
.history-date{font-size:12px;color:var(--text2);}.history-games{font-size:11px;color:var(--text3);}
.history-body{padding:8px 12px;}
.history-row{display:flex;justify-content:space-between;align-items:center;font-size:12px;padding:4px 0;border-bottom:0.5px solid var(--border);}
.history-row:last-child{border-bottom:none;}
.badge{display:inline-block;font-size:10px;padding:1px 6px;border-radius:8px;margin-left:4px;font-weight:600;}
.badge-top{background:rgba(29,158,117,0.15);color:var(--green);}
.badge-bot{background:rgba(216,90,48,0.15);color:var(--red);}
.legend-wrap{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:0.75rem;}
.legend-item{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--text2);}
.legend-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0;}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <h1>🀄 麻雀スコア</h1>
    <p>全""")
    html_parts.append(str(session_count))
    html_parts.append("セッション · ")
    html_parts.append(date_range)
    html_parts.append("""</p>
    <p class="updated">更新: """)
    html_parts.append(updated_at)
    html_parts.append("""</p>
  </div>
  <div class="tabs">
    <button class="tab active" onclick="showPage('ranking',this)">ランキング</button>
    <button class="tab" onclick="showPage('trend',this)">推移</button>
    <button class="tab" onclick="showPage('stats',this)">統計</button>
    <button class="tab" onclick="showPage('history',this)">履歴</button>
  </div>
  <div class="content">
    <div id="page-ranking" class="page show">
      <div id="overview-view" class="overview-view">
        <div class="section"><div class="section-title">総合収支ランキング</div><div class="ranking" id="ranking-list"></div></div>
        <div class="section"><div class="section-title">累計収支の推移（円）</div><div id="rank-legend" class="legend-wrap"></div><div class="chart-wrap"><canvas id="rankChart"></canvas></div></div>
      </div>
      <div id="detail-view" class="detail-view">
        <button class="back-btn" onclick="showOverview()">← 一覧へ戻る</button>
        <div class="section"><div class="grid2" id="detail-metrics"></div></div>
        <div class="section"><div class="section-title">対戦成績詳細</div><div id="detail-stats"></div></div>
        <div class="section"><div class="section-title">収支の累計推移</div><div class="chart-wrap"><canvas id="detailChart"></canvas></div></div>
      </div>
    </div>
    <div id="page-trend" class="page">
      <div class="section"><div class="section-title">累計収支の推移</div><div id="trend-legend" class="legend-wrap"></div><div class="chart-wrap" style="height:280px"><canvas id="trendChart"></canvas></div></div>
      <div class="section"><div class="section-title">セッション別 最高/最低収支</div><div class="chart-wrap" style="height:280px"><canvas id="sessionChart"></canvas></div></div>
    </div>
    <div id="page-stats" class="page">
      <div class="section"><div class="section-title">プレイヤー別成績</div><div class="ranking" id="stats-list"></div></div>
      <div class="section" style="margin-top:0.5rem"><div class="section-title">累計チップ</div><div id="chip-stats"></div></div>
      <div class="section"><div class="section-title">順位獲得率（積み上げ）</div><div class="chart-wrap" style="height:220px"><canvas id="winChart"></canvas></div></div>
      <div class="section"><div class="section-title">平均順位（低いほど良い）</div><div class="chart-wrap" style="height:220px"><canvas id="avgRankChart"></canvas></div></div>
    </div>
    <div id="page-history" class="page">
      <div class="section"><div class="section-title">対戦履歴（新しい順）</div><div class="history-list" id="history-list"></div></div>
    </div>
  </div>
</div>
<script>
const COLORS={'南':'#378ADD','林':'#1D9E75','関河':'#D85A30','古川':'#D4537E','熊坂':'#7F77DD','矢田':'#BA7517','西村':'#888780','鎌田':'#639922','藤田':'#993C1D'};
const allData=""")
    html_parts.append(sessions_json)
    html_parts.append(""";

const playerTotals={},playerGames={},playerSessions={},playerRanks={},playerRankSum={},playerSessionCount={},playerChips={};
allData.forEach(function(sess){
  var sorted=sess.scores.slice().sort(function(a,b){return b-a;});
  sess.players.forEach(function(p,i){
    if(!playerTotals[p]){
      playerTotals[p]=0;playerGames[p]=0;playerSessions[p]=[];
      playerRanks[p]={1:0,2:0,3:0,4:0};playerRankSum[p]=0;playerSessionCount[p]=0;playerChips[p]=0;
    }
    playerTotals[p]+=sess.payouts[i];
    playerGames[p]+=sess.games;
    var chip=sess.chips&&sess.chips[i]?sess.chips[i]:0;
    playerChips[p]+=chip;
    playerSessions[p].push({date:sess.date,score:sess.scores[i],payout:sess.payouts[i],chip:chip});
    playerSessionCount[p]++;
    var rank=sorted.indexOf(sess.scores[i])+1;
    if(playerRanks[p][rank]!==undefined) playerRanks[p][rank]++;
    playerRankSum[p]+=rank;
  });
});

var players=Object.keys(playerTotals).sort(function(a,b){return playerTotals[b]-playerTotals[a];});

function fmt(n){ return (n>=0?'+':'')+n.toLocaleString(); }
function fmtS(n){ return (n>=0?'+':'')+n; }
function avgRank(p){ return (playerRankSum[p]/playerSessionCount[p]).toFixed(2); }
function rankRate(p,r){ return Math.round((playerRanks[p][r]||0)/playerSessionCount[p]*100); }
function col(p){ return COLORS[p]||'#888888'; }

function showPage(name,btn){
  document.querySelectorAll('.page').forEach(function(p){p.classList.remove('show');});
  document.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active');});
  document.getElementById('page-'+name).classList.add('show');
  btn.classList.add('active');
  if(name==='trend') renderTrend();
  if(name==='stats') renderStats();
  if(name==='history') renderHistory();
}

function showOverview(){
  document.getElementById('detail-view').classList.remove('show');
  document.getElementById('overview-view').classList.remove('hidden');
}

function showDetail(player){
  document.getElementById('overview-view').classList.add('hidden');
  document.getElementById('detail-view').classList.add('show');
  var sessions=playerSessions[player];
  var total=playerTotals[player];
  var sc=playerSessionCount[player];
  var posNeg=total>=0?'pos':'neg';
  document.getElementById('detail-metrics').innerHTML=
    '<div class="metric"><div class="metric-label">'+player+'の総収支</div><div class="metric-value '+posNeg+'">'+fmt(total)+'</div><div class="metric-sub">円</div></div>'+
    '<div class="metric"><div class="metric-label">累計チップ</div><div class="metric-value '+(playerChips[player]>=0?'pos':'neg')+'">'+playerChips[player]+'</div><div class="metric-sub">枚</div></div>'+
    '<div class="metric"><div class="metric-label">参加セッション</div><div class="metric-value">'+sc+'</div><div class="metric-sub">回</div></div>'+
    '<div class="metric"><div class="metric-label">平均順位</div><div class="metric-value">'+avgRank(player)+'</div><div class="metric-sub">位</div></div>';
  var payouts=sessions.map(function(s){return s.payout;});
  var best=Math.max.apply(null,payouts);
  var worst=Math.min.apply(null,payouts);
  var scoreSum=sessions.reduce(function(a,s){return a+s.score;},0);
  var r=playerRanks[player];
  document.getElementById('detail-stats').innerHTML=
    '<div class="stat-row"><span class="stat-label">総プレイ対局数</span><span class="stat-val">'+playerGames[player]+'局</span></div>'+
    '<div class="stat-row"><span class="stat-label">累計スコア合計</span><span class="stat-val">'+fmtS(scoreSum)+'</span></div>'+
    '<div class="stat-row"><span class="stat-label">最高収支セッション</span><span class="stat-val pos">'+fmt(best)+'円</span></div>'+
    '<div class="stat-row"><span class="stat-label">最低収支セッション</span><span class="stat-val neg">'+fmt(worst)+'円</span></div>'+
    '<div class="stat-row"><span class="stat-label">🥇 1位獲得率</span><span class="stat-val">'+rankRate(player,1)+'%（'+r[1]+'回）</span></div>'+
    '<div class="stat-row"><span class="stat-label">🥈 2位獲得率</span><span class="stat-val">'+rankRate(player,2)+'%（'+r[2]+'回）</span></div>'+
    '<div class="stat-row"><span class="stat-label">🥉 3位獲得率</span><span class="stat-val">'+rankRate(player,3)+'%（'+r[3]+'回）</span></div>'+
    '<div class="stat-row"><span class="stat-label">💀 4位獲得率</span><span class="stat-val">'+rankRate(player,4)+'%（'+r[4]+'回）</span></div>'+
    '<div class="stat-row"><span class="stat-label">累計チップ</span><span class="stat-val '+(playerChips[player]>=0?'pos':'neg')+'">'+playerChips[player]+'枚</span></div>';
  var ctx=document.getElementById('detailChart').getContext('2d');
  if(window._dc) window._dc.destroy();
  var acc=0;
  var cumData=sessions.map(function(s){acc+=s.payout;return acc;});
  window._dc=new Chart(ctx,{
    type:'line',
    data:{
      labels:sessions.map(function(s){return s.date.slice(5);}),
      datasets:[{label:player,data:cumData,borderColor:col(player),backgroundColor:'transparent',tension:0.3,pointRadius:4,borderWidth:2}]
    },
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:function(v){return v.toLocaleString();}}}}}
  });
}

function renderRanking(){
  var rankClass=['gold','silver','bronze'];
  var html='';
  for(var i=0;i<players.length;i++){
    var p=players[i];
    var rc=rankClass[i]||'';
    var tc=playerTotals[p]>=0?'#1D9E75':'#D85A30';
    html+='<div class="rank-row" data-player="'+p+'" onclick="showDetail(this.dataset.player)">';
    html+='<div class="rank-num '+rc+'">'+(i+1)+'</div>';
    html+='<div class="rank-avatar" style="background:'+col(p)+'22;color:'+col(p)+'">'+p[0]+'</div>';
    html+='<div class="rank-info"><div class="rank-name">'+p+'</div><div class="rank-detail">'+playerSessionCount[p]+'セッション · 平均'+avgRank(p)+'位</div></div>';
    html+='<div class="rank-score"><div class="rank-score-val" style="color:'+tc+'">'+fmt(playerTotals[p])+'</div><div class="rank-score-sub">円</div></div>';
    html+='</div>';
  }
  document.getElementById('ranking-list').innerHTML=html;

  var dateLabels=[...new Set(allData.map(function(d){return d.date;}))].sort();
  var legendHtml='';
  for(var i=0;i<players.length;i++){
    legendHtml+='<span class="legend-item"><span class="legend-dot" style="background:'+col(players[i])+'"></span>'+players[i]+'</span>';
  }
  document.getElementById('rank-legend').innerHTML=legendHtml;

  var datasets=players.map(function(p){
    var acc=0;
    var data=dateLabels.map(function(date){
      var s=null;
      for(var j=0;j<allData.length;j++){
        if(allData[j].date===date && allData[j].players.indexOf(p)>=0){s=allData[j];break;}
      }
      if(s) acc+=s.payouts[s.players.indexOf(p)];
      return acc;
    });
    return {label:p,data:data,borderColor:col(p),backgroundColor:'transparent',tension:0.3,pointRadius:3,borderWidth:2};
  });

  var ctx=document.getElementById('rankChart').getContext('2d');
  if(window._rc) window._rc.destroy();
  window._rc=new Chart(ctx,{
    type:'line',
    data:{labels:dateLabels.map(function(d){return d.slice(5);}),datasets:datasets},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:function(v){return v.toLocaleString();}}}}}
  });
}

function renderTrend(){
  var dateLabels=[...new Set(allData.map(function(d){return d.date;}))].sort();
  var legendHtml='';
  for(var i=0;i<players.length;i++){
    legendHtml+='<span class="legend-item"><span class="legend-dot" style="background:'+col(players[i])+'"></span>'+players[i]+'</span>';
  }
  document.getElementById('trend-legend').innerHTML=legendHtml;

  var datasets=players.map(function(p){
    var acc=0;
    var data=dateLabels.map(function(date){
      var s=null;
      for(var j=0;j<allData.length;j++){
        if(allData[j].date===date && allData[j].players.indexOf(p)>=0){s=allData[j];break;}
      }
      if(s){acc+=s.payouts[s.players.indexOf(p)];return acc;}
      return null;
    });
    return {label:p,data:data,borderColor:col(p),backgroundColor:'transparent',tension:0.3,pointRadius:3,borderWidth:2,spanGaps:true};
  });

  var ctx1=document.getElementById('trendChart').getContext('2d');
  if(window._tc) window._tc.destroy();
  window._tc=new Chart(ctx1,{
    type:'line',
    data:{labels:dateLabels.map(function(d){return d.slice(5);}),datasets:datasets},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:function(v){return v.toLocaleString();}}}}}
  });

  var ctx2=document.getElementById('sessionChart').getContext('2d');
  if(window._sc) window._sc.destroy();
  window._sc=new Chart(ctx2,{
    type:'bar',
    data:{
      labels:allData.map(function(d){return d.date.slice(5);}),
      datasets:[
        {label:'最高収支',data:allData.map(function(d){return Math.max.apply(null,d.payouts);}),backgroundColor:'rgba(29,158,117,0.5)'},
        {label:'最低収支',data:allData.map(function(d){return Math.min.apply(null,d.payouts);}),backgroundColor:'rgba(216,90,48,0.5)'}
      ]
    },
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:function(v){return v.toLocaleString();}}}}}
  });
}

function renderStats(){
  var rankClass=['gold','silver','bronze'];
  var html='';
  for(var i=0;i<players.length;i++){
    var p=players[i];
    var rc=rankClass[i]||'';
    var tc=playerTotals[p]>=0?'#1D9E75':'#D85A30';
    html+='<div class="rank-row">';
    html+='<div class="rank-num '+rc+'">'+(i+1)+'</div>';
    html+='<div class="rank-avatar" style="background:'+col(p)+'22;color:'+col(p)+'">'+p[0]+'</div>';
    html+='<div class="rank-info"><div class="rank-name">'+p+'</div><div class="rank-detail">🥇'+rankRate(p,1)+'% 🥈'+rankRate(p,2)+'% 🥉'+rankRate(p,3)+'% 💀'+rankRate(p,4)+'% · 平均'+avgRank(p)+'位</div></div>';
    html+='<div class="rank-score"><div class="rank-score-val" style="color:'+tc+'">'+fmt(playerTotals[p])+'</div><div class="rank-score-sub">円</div></div>';
    html+='</div>';
  }
  document.getElementById('stats-list').innerHTML=html;

  var ctx3=document.getElementById('winChart').getContext('2d');
  if(window._wc) window._wc.destroy();
  window._wc=new Chart(ctx3,{
    type:'bar',
    data:{
      labels:players,
      datasets:[
        {label:'🥇1位',data:players.map(function(p){return rankRate(p,1);}),backgroundColor:'rgba(186,117,23,0.85)',borderRadius:3},
        {label:'🥈2位',data:players.map(function(p){return rankRate(p,2);}),backgroundColor:'rgba(136,135,128,0.75)',borderRadius:3},
        {label:'🥉3位',data:players.map(function(p){return rankRate(p,3);}),backgroundColor:'rgba(153,60,29,0.65)',borderRadius:3},
        {label:'💀4位',data:players.map(function(p){return rankRate(p,4);}),backgroundColor:'rgba(90,90,90,0.45)',borderRadius:3}
      ]
    },
    options:{
      responsive:true,maintainAspectRatio:false,indexAxis:'y',
      plugins:{legend:{position:'bottom',labels:{font:{size:11},boxWidth:12}}},
      scales:{
        x:{stacked:true,max:100,ticks:{callback:function(v){return v+'%';}}},
        y:{stacked:true}
      }
    }
  });

  var ctx4=document.getElementById('avgRankChart').getContext('2d');
  if(window._ac) window._ac.destroy();
  window._ac=new Chart(ctx4,{
    type:'bar',
    data:{
      labels:players,
      datasets:[{label:'平均順位',data:players.map(function(p){return parseFloat(avgRank(p));}),backgroundColor:players.map(function(p){return col(p)+'99';}),borderRadius:4}]
    },
    options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{display:false}},scales:{x:{min:1,max:4,ticks:{callback:function(v){return v+'位';}}}}}
  });

  // チップ統計
  var chipHtml='';
  var sorted_chip=players.slice().sort(function(a,b){return playerChips[b]-playerChips[a];});
  for(var i=0;i<sorted_chip.length;i++){
    var p=sorted_chip[i];
    var chips=playerChips[p];
    var pct=Math.max(0,Math.min(100,Math.abs(chips)/Math.max.apply(null,sorted_chip.map(function(q){return Math.abs(playerChips[q]);}||1))*100));
    chipHtml+='<div style="margin-bottom:10px;">';
    chipHtml+='<div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">';
    chipHtml+='<span style="font-weight:600;color:'+col(p)+'">'+p+'</span>';
    chipHtml+='<span style="font-weight:600;color:'+(chips>=0?'var(--green)':'var(--red)')+'">'+fmtS(chips)+'枚</span>';
    chipHtml+='</div>';
    chipHtml+='<div style="height:8px;border-radius:4px;background:var(--bg3);overflow:hidden;">';
    chipHtml+='<div style="height:100%;width:'+pct+'%;border-radius:4px;background:'+(chips>=0?'var(--green)':'var(--red)')+';"></div>';
    chipHtml+='</div></div>';
  }
  document.getElementById('chip-stats').innerHTML=chipHtml;
}

function renderHistory(){
  var sorted=allData.slice().sort(function(a,b){return b.date.localeCompare(a.date);});
  var html='';
  for(var i=0;i<sorted.length;i++){
    var sess=sorted[i];
    var maxP=Math.max.apply(null,sess.payouts);
    var minP=Math.min.apply(null,sess.payouts);
    html+='<div class="history-card">';
    html+='<div class="history-header"><span class="history-date">'+sess.date+'</span><span class="history-games">'+sess.games+'局 · '+sess.players.join('/')+'</span></div>';
    html+='<div class="history-body">';
    for(var j=0;j<sess.players.length;j++){
      var p=sess.players[j];
      var pay=sess.payouts[j];
      var payColor=pay>=0?'#1D9E75':'#D85A30';
      var badge='';
      if(pay===maxP) badge='<span class="badge badge-top">TOP</span>';
      else if(pay===minP) badge='<span class="badge badge-bot">LAST</span>';
      html+='<div class="history-row">';
      html+='<span style="color:'+col(p)+';font-weight:600;font-size:13px">'+p+'</span>';
      html+='<span style="color:#9b9b97">スコア '+fmtS(sess.scores[j])+'</span>';
      html+='<span style="color:'+payColor+';font-weight:600">'+fmt(pay)+'円'+badge+'</span>';
      html+='</div>';
    }
    html+='</div></div>';
  }
  document.getElementById('history-list').innerHTML=html;
}

renderRanking();
</script>
</body>
</html>""")

    html = ''.join(html_parts)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("✅ ダッシュボードを生成しました: " + output_path)
    print("   セッション数: " + str(session_count))
    print("   期間: " + date_range)


if __name__ == '__main__':
    score_dir = sys.argv[1] if len(sys.argv) >= 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SCORE')
    output_path = sys.argv[2] if len(sys.argv) >= 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '麻雀ダッシュボード.html')

    if not os.path.isdir(score_dir):
        print("❌ フォルダが見つかりません: " + score_dir, file=sys.stderr)
        sys.exit(1)

    sessions = parse_csv_files(score_dir)
    if not sessions:
        print("⚠️ CSVが読み込めませんでした", file=sys.stderr)
        sys.exit(1)

    generate_html(sessions, output_path)
