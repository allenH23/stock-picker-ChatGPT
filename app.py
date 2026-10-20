# -*- coding: utf-8 -*-
"""台股智慧選股：免費行情 + FinMind 基本面/技術面/新聞題材原型。"""
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.express as px

VERSION = '0.3.0'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36'}
FINMIND_URL = 'https://api.finmindtrade.com/api/v4/data'
st.set_page_config(page_title='台股智慧選股', page_icon='📈', layout='wide')
st.title('📈 台股智慧選股｜基本面・技術面・市場面・熱門題材')
st.caption(f'版本 {VERSION}｜上市＋上櫃｜免費資料優先｜每日盤後研究工具')
st.warning('研究原型，不構成投資建議。評分只代表本程式定義的量化條件；資料缺漏、財報時差、新聞分類錯誤及市場制度因素都可能影響結果。')


def get_json(url, params=None, headers=None):
    r = requests.get(url, params=params or {}, headers=headers or HEADERS, timeout=18)
    r.raise_for_status()
    return r.json(), r.url


def pick(d, keys, default=None):
    for k in keys:
        if k in d and d[k] is not None and str(d[k]).strip() not in ('', '-', '--', 'N/A'):
            return d[k]
    return default


def num(x):
    if x is None or pd.isna(x): return np.nan
    try: return float(str(x).strip().replace(',', '').replace('+', '').replace('%', ''))
    except Exception: return np.nan


def normalize(rows, market, source):
    out = []
    for r in rows or []:
        if not isinstance(r, dict): continue
        code = pick(r, ['Code','code','證券代號','代號','SecuritiesCompanyCode','股票代號'])
        close = pick(r, ['ClosingPrice','Close','close','收盤價','收盤','成交價'])
        if code is None or close is None: continue
        code = str(code).strip(); close = num(close)
        if not code.isdigit() or len(code) not in (4,5,6) or not np.isfinite(close) or close <= 0: continue
        out.append({'代號':code,'名稱':str(pick(r,['Name','name','證券名稱','名稱','CompanyName','公司名稱'],'')).strip(),'市場':market,
          '日期':str(pick(r,['Date','date','資料日期','日期'],'未知')),
          '開盤':num(pick(r,['OpeningPrice','Open','open','開盤價','開盤'])),'最高':num(pick(r,['HighestPrice','High','high','最高價','最高','max'])),'最低':num(pick(r,['LowestPrice','Low','low','最低價','最低','min'])),'收盤':close,
          '漲跌':num(pick(r,['Change','change','漲跌價差','漲跌','spread'])),'成交股數':num(pick(r,['TradeVolume','Volume','volume','成交股數','成交量','Trading_Volume'])),'成交金額':num(pick(r,['TradeValue','turnover','成交金額','成交值','Trading_money'])),'成交筆數':num(pick(r,['Transaction','transactions','成交筆數','Trading_turnover'])),'資料來源':source})
    return pd.DataFrame(out).drop_duplicates('代號', keep='last') if out else pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_twse():
    errors=[]
    for url,params in [('https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',{}),('https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX',{'date':datetime.now().strftime('%Y%m%d'),'type':'ALLBUT0999','response':'json'})]:
        try:
            data,final=get_json(url,params)
            if isinstance(data,list):
                df=normalize(data,'上市','TWSE OpenAPI')
                if not df.empty:return df,{'來源':'TWSE','成功':True,'筆數':len(df),'網址':final,'錯誤':''}
            if isinstance(data,dict):
                for t in data.get('tables',[]):
                    if not t.get('fields') or not t.get('data'): continue
                    raw=pd.DataFrame(t['data'],columns=t['fields'])
                    if {'證券代號','收盤價'}.issubset(raw.columns):
                        raw=raw.rename(columns={'證券代號':'Code','證券名稱':'Name','收盤價':'ClosingPrice','成交股數':'TradeVolume','成交金額':'TradeValue','成交筆數':'Transaction','漲跌價差':'Change'})
                        df=normalize(raw.to_dict('records'),'上市','TWSE RWD')
                        if not df.empty:return df,{'來源':'TWSE','成功':True,'筆數':len(df),'網址':final,'錯誤':''}
            errors.append(f'{url}: 回應欄位不符預期')
        except Exception as e: errors.append(f'{url}: {type(e).__name__}: {e}')
    return pd.DataFrame(),{'來源':'TWSE','成功':False,'筆數':0,'網址':'','錯誤':'；'.join(errors)}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_tpex():
    errors=[]
    for url in ['https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes','https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes']:
        try:
            data,final=get_json(url); rows=data if isinstance(data,list) else data.get('data',data.get('aaData',[])) if isinstance(data,dict) else []
            df=normalize(rows,'上櫃','TPEx OpenAPI')
            if not df.empty:return df,{'來源':'TPEx','成功':True,'筆數':len(df),'網址':final,'錯誤':''}
            errors.append(f'{url}: 有回應但無法辨識行情欄位')
        except Exception as e: errors.append(f'{url}: {type(e).__name__}: {e}')
    try:
        roc=datetime.now().year-1911; d=f'{roc}/{datetime.now().month:02d}/{datetime.now().day:02d}'
        data,final=get_json('https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes',{'l':'zh-tw','o':'json','d':d,'se':'EW'})
        frame=pd.DataFrame(data.get('aaData',[])) if isinstance(data,dict) else pd.DataFrame(); rows=[]
        for vals in frame.values.tolist():
            if len(vals)>=3: rows.append({'Code':vals[0],'Name':vals[1],'ClosingPrice':vals[2],'TradeVolume':vals[7] if len(vals)>7 else None,'TradeValue':vals[8] if len(vals)>8 else None,'Transaction':vals[9] if len(vals)>9 else None})
        df=normalize(rows,'上櫃','TPEx legacy')
        if not df.empty:return df,{'來源':'TPEx','成功':True,'筆數':len(df),'網址':final,'錯誤':''}
        errors.append(f'{final}: 無可辨識資料')
    except Exception as e: errors.append(f'TPEx legacy: {type(e).__name__}: {e}')
    return pd.DataFrame(),{'來源':'TPEx','成功':False,'筆數':0,'網址':'','錯誤':'；'.join(errors)}


def finmind_get(dataset, code, start_date, end_date=None, token=''):
    params={'dataset':dataset,'data_id':str(code),'start_date':start_date}
    if end_date: params['end_date']=end_date
    headers=dict(HEADERS)
    if token.strip(): headers['Authorization']='Bearer '+token.strip()
    data,_=get_json(FINMIND_URL,params,headers)
    if not isinstance(data,dict) or data.get('status',200) not in (200,'200'):
        raise ValueError(str(data.get('msg','FinMind API 回傳錯誤')) if isinstance(data,dict) else 'FinMind 回應格式錯誤')
    rows=data.get('data',[])
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=21600, show_spinner=False)
def get_revenue(code, token):
    start=(datetime.now()-timedelta(days=550)).strftime('%Y-%m-%d')
    return finmind_get('TaiwanStockMonthRevenue',code,start,token=token)

@st.cache_data(ttl=21600, show_spinner=False)
def get_per(code, token):
    start=(datetime.now()-timedelta(days=45)).strftime('%Y-%m-%d')
    return finmind_get('TaiwanStockPER',code,start,token=token)

@st.cache_data(ttl=21600, show_spinner=False)
def get_financials(code, token):
    start=(datetime.now()-timedelta(days=550)).strftime('%Y-%m-%d')
    return finmind_get('TaiwanStockFinancialStatements',code,start,token=token)

@st.cache_data(ttl=21600, show_spinner=False)
def get_prices(code, token):
    start=(datetime.now()-timedelta(days=220)).strftime('%Y-%m-%d')
    return finmind_get('TaiwanStockPrice',code,start,token=token)

@st.cache_data(ttl=21600, show_spinner=False)
def get_news(code, token):
    # 新聞資料集每次查詢量有限；以最近一天資料為主，避免大量呼叫。
    start=(datetime.now()-timedelta(days=5)).strftime('%Y-%m-%d')
    return finmind_get('TaiwanStockNews',code,start,token=token)


def score_revenue(df):
    if df.empty or 'revenue' not in df or 'date' not in df: return np.nan, '月營收資料不足'
    d=df.copy(); d['date']=pd.to_datetime(d['date'],errors='coerce'); d['revenue']=pd.to_numeric(d['revenue'],errors='coerce'); d=d.dropna(subset=['date','revenue']).sort_values('date')
    if len(d)<2: return np.nan,'月營收筆數不足'
    latest=d.iloc[-1]; prior=d[d['date']<=latest['date']-pd.Timedelta(days=330)]
    yoy=np.nan
    if not prior.empty:
        old=prior.iloc[-1]['revenue']
        if old>0:yoy=(latest['revenue']/old-1)*100
    mom=np.nan
    if len(d)>=2 and d.iloc[-2]['revenue']>0:mom=(latest['revenue']/d.iloc[-2]['revenue']-1)*100
    # YoY 主權重，MoM 次權重；不將單月營收當成獲利。
    parts=[]
    if pd.notna(yoy): parts.append(float(np.clip(50+yoy*0.8,0,100)))
    if pd.notna(mom): parts.append(float(np.clip(50+mom*0.35,0,100)))
    score=float(np.mean(parts)) if parts else np.nan
    desc=f"最新月營收年增 {yoy:+.1f}%" if pd.notna(yoy) else '缺少可比去年同期的月營收'
    if pd.notna(mom):desc+=f"、月增 {mom:+.1f}%"
    return score,desc


def score_fundamental(code, token):
    details=[]; scores=[]; values={'營收年增(%)':np.nan,'月營收分數':np.nan,'本益比':np.nan,'股價淨值比':np.nan,'財報指標':np.nan}
    errors=[]
    try:
        rev=get_revenue(code,token); rs,rd=score_revenue(rev); values['月營收分數']=rs; details.append(rd)
        if pd.notna(rs): scores.append((rs,0.50))
    except Exception as e: errors.append('月營收：'+str(e))
    try:
        per=get_per(code,token)
        if not per.empty:
            per=per.copy()
            for c in ['PER','PBR','dividend_yield']:
                if c in per:per[c]=pd.to_numeric(per[c],errors='coerce')
            last=per.sort_values('date').iloc[-1]
            values['本益比']=last.get('PER',np.nan); values['股價淨值比']=last.get('PBR',np.nan)
            val=[]
            if pd.notna(values['本益比']) and 0<values['本益比']<100:
                s=float(np.clip(100-(values['本益比']-10)*1.5,0,100)); val.append(s); details.append(f"本益比 {values['本益比']:.1f} 倍")
            if pd.notna(values['股價淨值比']) and values['股價淨值比']>0:
                s=float(np.clip(100-(values['股價淨值比']-1)*12,0,100)); val.append(s); details.append(f"股價淨值比 {values['股價淨值比']:.2f} 倍")
            if val:scores.append((float(np.mean(val)),0.25))
    except Exception as e: errors.append('PER/PBR：'+str(e))
    try:
        fs=get_financials(code,token)
        if not fs.empty and {'date','type','value'}.issubset(fs.columns):
            fs=fs.copy(); fs['date']=pd.to_datetime(fs['date'],errors='coerce'); fs['value']=pd.to_numeric(fs['value'],errors='coerce')
            latest=fs.sort_values('date').iloc[-1]['date']; q=fs[fs['date']==latest]
            # 以最新一期綜損表營業利益／稅前或稅後淨利是否為正作簡單品質檢查；欄位依供應商版本容錯。
            names=' '.join(q.get('origin_name',pd.Series(dtype=str)).fillna('').astype(str).tolist())
            profits=q[q.get('origin_name',pd.Series(index=q.index,dtype=str)).astype(str).str.contains('營業利益|本期淨利|稅前淨利',regex=True,na=False)]
            if not profits.empty:
                positive=(profits['value']>0).mean()*100; values['財報指標']=positive; scores.append((float(positive),0.25)); details.append('最新一期可辨識獲利科目正值比例 '+f'{positive:.0f}%')
            else: errors.append('財報有回傳，但無法辨識獲利科目')
        else: errors.append('財報資料不足')
    except Exception as e: errors.append('財報：'+str(e))
    total=sum(w for _,w in scores)
    score=sum(s*w for s,w in scores)/total if total else np.nan
    if errors: details.append('資料提醒：'+'；'.join(errors)[:220])
    details.append('評分為營收成長、估值及獲利科目的簡化合成分，不等於完整財務體質分析')
    return score,'；'.join(details),values


def score_technical(code, token):
    try:
        d=get_prices(code,token)
        if d.empty: return np.nan,'無歷史日線資料',{}
        d=d.copy(); d['date']=pd.to_datetime(d.get('date'),errors='coerce')
        close_col='close' if 'close' in d else ('Close' if 'Close' in d else None)
        vol_col='Trading_Volume' if 'Trading_Volume' in d else ('volume' if 'volume' in d else ('Trading_Volume' if 'Trading_Volume' in d else None))
        if not close_col: return np.nan,'歷史行情缺少收盤價欄位',{}
        d[close_col]=pd.to_numeric(d[close_col],errors='coerce'); d=d.dropna(subset=['date',close_col]).sort_values('date')
        c=d[close_col].astype(float); v=pd.to_numeric(d[vol_col],errors='coerce') if vol_col else pd.Series(np.nan,index=d.index)
        if len(c)<25:return np.nan,f'歷史日線只有 {len(c)} 筆，至少需要 25 筆',{}
        ma20=c.rolling(20).mean().iloc[-1]; ma60=c.rolling(60).mean().iloc[-1] if len(c)>=60 else np.nan
        ret20=(c.iloc[-1]/c.iloc[-21]-1)*100 if len(c)>=21 else np.nan
        ret60=(c.iloc[-1]/c.iloc[-61]-1)*100 if len(c)>=61 else np.nan
        delta=c.diff(); gain=delta.clip(lower=0).rolling(14).mean(); loss=-delta.clip(upper=0).rolling(14).mean(); rs=gain/(loss.replace(0,np.nan)); rsi=(100-100/(1+rs)).iloc[-1]
        volratio=np.nan
        if v.notna().sum()>=20 and v.tail(20).mean()>0:volratio=v.iloc[-1]/v.tail(20).mean()
        parts=[]
        parts.append(70 if c.iloc[-1]>ma20 else 35)
        if pd.notna(ma60):parts.append(70 if ma20>ma60 else 35)
        if pd.notna(ret20):parts.append(float(np.clip(50+ret20*2,0,100)))
        if pd.notna(rsi):parts.append(float(np.clip(100-abs(rsi-58)*1.5,0,100)))
        if pd.notna(volratio):parts.append(float(np.clip(45+(volratio-1)*25,0,100)))
        score=float(np.mean(parts))
        details=f"20日報酬 {ret20:+.1f}%" if pd.notna(ret20) else '20日報酬缺值'
        details+=f"；收盤 {'高於' if c.iloc[-1]>ma20 else '低於'}20日均線"
        if pd.notna(ma60):details+=f"；20日均線 {'高於' if ma20>ma60 else '低於'}60日均線"
        if pd.notna(rsi):details+=f"；RSI(14) {rsi:.1f}"
        if pd.notna(volratio):details+=f"；當日量／20日均量 {volratio:.2f}"
        return score,details,{'20日報酬(%)':ret20,'60日報酬(%)':ret60,'RSI(14)':rsi,'量比':volratio,'20日均線':ma20,'60日均線':ma60}
    except Exception as e:return np.nan,f'技術資料取得失敗：{type(e).__name__}: {e}',{}

THEMES={
 'AI伺服器/資料中心':['AI伺服器','伺服器','資料中心','GPU','ASIC','液冷','散熱','高速傳輸','AI晶片'],
 '半導體/先進封裝':['半導體','先進封裝','CoWoS','封裝','晶圓代工','HBM','矽光子','設備','測試'],
 '記憶體':['記憶體','DRAM','NAND','NOR Flash','HBM','報價上漲'],
 '電動車/車用電子':['電動車','車用','ADAS','電池','充電樁'],
 '機器人/自動化':['機器人','機器手臂','自動化','人形機器人'],
 '能源/電網':['儲能','電網','重電','變壓器','綠能','太陽能','風電'],
 '軍工/航太':['軍工','國防','航太','無人機'],
 '生技/新藥':['新藥','臨床試驗','生技','藥證','醫材'],
 '金融/高股息':['股利','配息','殖利率','金融股','高股息']}
POS_WORDS=['獲利成長','營收創高','接單','擴產','量產','訂單增加','上修','成長','突破','合作','獲利轉盈','新產品','需求增']
NEG_WORDS=['下修','減產','裁員','虧損擴大','需求疲弱','取消訂單','違約','調查','停工','營收衰退','獲利衰退']

def score_theme(code, token):
    try:
        news=get_news(code,token)
        if news.empty:return np.nan,'近幾日無可用新聞資料，無法判定熱門題材',[]
        title_col='title' if 'title' in news else ('description' if 'description' in news else None)
        if not title_col:return np.nan,'新聞資料缺少標題欄位',[]
        news=news.copy(); news[title_col]=news[title_col].fillna('').astype(str)
        headlines=news[title_col].head(15).tolist(); blob=' '.join(headlines)
        found=[]
        for theme,keys in THEMES.items():
            count=sum(blob.lower().count(k.lower()) for k in keys)
            if count:found.append((theme,count,[k for k in keys if k.lower() in blob.lower()]))
        if not found:return 15,'有新聞，但標題未命中內建題材關鍵字；不代表公司沒有題材',headlines[:5]
        found.sort(key=lambda x:x[1],reverse=True); hits=found[0][1]
        pos=sum(1 for w in POS_WORDS if w in blob); neg=sum(1 for w in NEG_WORDS if w in blob)
        score=float(np.clip(35+hits*12+min(pos,3)*5-min(neg,3)*8,0,100))
        detail='題材關鍵字：'+', '.join(f'{x[0]}（命中{x[1]}次）' for x in found[:3])+f'；正向詞 {pos}、風險詞 {neg}；分析 {len(headlines)} 則新聞標題'
        return score,detail,headlines[:5]
    except Exception as e:return np.nan,f'新聞資料取得失敗：{type(e).__name__}: {e}',[]


def backtest(p,lookback=20,top_n=5,fee_bps=14):
    wide=p.pivot_table(index='date',columns='code',values='close',aggfunc='last').sort_index(); ret=wide.pct_change(); sig=wide.pct_change(lookback).shift(1); held=sig.rank(axis=1,ascending=False,method='first').le(top_n).shift(1).fillna(False)
    daily=(ret.where(held).mean(axis=1)-fee_bps/10000).fillna(0); eq=(1+daily).cumprod(); bench=(1+ret.mean(axis=1).fillna(0)).cumprod(); curve=pd.DataFrame({'日期':eq.index,'策略淨值':eq.values,'等權基準淨值':bench.values}); yrs=max(len(daily)/252,1/252)
    return curve,{'累積報酬':eq.iloc[-1]-1,'年化報酬':eq.iloc[-1]**(1/yrs)-1 if eq.iloc[-1]>0 else np.nan,'年化波動':daily.std()*np.sqrt(252),'最大回撤':(eq/eq.cummax()-1).min()}

with st.sidebar:
    st.header('選股設定')
    src=st.radio('行情來源',['連線官方免費行情','示範資料（合成）'],index=0)
    mode=st.selectbox('選股方向',['基本面','技術面','市場面','熱門題材'])
    level=st.selectbox('推薦風格',['穩健','均衡','積極'],index=1)
    batch=st.selectbox('每批顯示',[5,3],index=0)
    token=st.text_input('FinMind API Token（選填）',type='password',help='不填可試用免費匿名額度；註冊 FinMind 帳號可取得 token，提高 API 額度。Token 僅在本次程式執行時使用，不會寫入程式檔。')
    candidate_n=st.select_slider('深入分析候選股數',[10,15,20,25,30],value=20,help='為避免免費 API 額度耗盡，深入分析只對成交金額排名前 N 檔執行。')
    if st.button('重新抓取資料'):st.cache_data.clear(); st.session_state.seen=[]; st.rerun()
if 'seen' not in st.session_state:st.session_state.seen=[]
diags=[]
if src=='連線官方免費行情':
    with st.spinner('連線 TWSE／TPEx 官方免費行情…'):
        tw,dt=fetch_twse(); tp,dp=fetch_tpex()
    raw=pd.concat([x for x in [tw,tp] if not x.empty],ignore_index=True) if not (tw.empty and tp.empty) else pd.DataFrame(); diags=[dt,dp]
else:
    rng=np.random.default_rng(10); n=150
    raw=pd.DataFrame({'代號':[str(1101+i) for i in range(n)],'名稱':[f'示範公司{i+1:03}' for i in range(n)],'市場':rng.choice(['上市','上櫃'],n),'日期':'合成資料','開盤':rng.uniform(20,500,n),'最高':rng.uniform(25,550,n),'最低':rng.uniform(15,450,n),'收盤':rng.uniform(20,500,n),'漲跌':rng.normal(0,3,n),'成交股數':rng.integers(10000,10000000,n),'成交金額':rng.integers(1000000,500000000,n),'成交筆數':rng.integers(100,30000,n),'資料來源':'合成示範資料'})
if diags:
    st.subheader('官方行情連線診斷'); st.dataframe(pd.DataFrame(diags),use_container_width=True,hide_index=True)
    if raw.empty:
        st.error('官方行情來源目前都未回傳可辨識資料。請先解決行情連線，再測試基本面／技術面／題材。')
        with st.expander('完整錯誤訊息'):
            for x in diags:st.code(x['來源']+'\n'+x['錯誤'])

if not raw.empty:
    raw=raw.drop_duplicates(['代號','市場'],keep='last').copy()
    for c in ['成交金額','漲跌','收盤','成交股數']:raw[c]=pd.to_numeric(raw[c],errors='coerce')
    raw['流動性排名']=raw['成交金額'].rank(pct=True); raw['單日漲跌排名']=raw['漲跌'].rank(pct=True)
    raw['市場面分數']=(.6*raw['流動性排名']+.4*raw['單日漲跌排名'])*100
    st.success(f'取得 {len(raw):,} 檔行情｜來源：{", ".join(raw["資料來源"].dropna().unique())}')
    if src=='連線官方免費行情':
        st.caption(f'深入分析範圍：按當日成交金額取前 {candidate_n} 檔；這是免費 API 呼叫量與速度的折衷，不代表其他股票較差。')
        candidates=raw.sort_values('成交金額',ascending=False).head(candidate_n).copy()
        if mode=='市場面':
            raw['分數']=raw['市場面分數']; raw['說明']=raw.apply(lambda r:f"單日漲跌 {r['漲跌']:+.2f}；成交金額約 {r['成交金額']/1e8:.2f} 億。市場面僅反映當日漲跌與流動性，沒有納入多日趨勢或籌碼。",axis=1)
            pool=raw.sort_values('分數',ascending=False)
        else:
            rows=[]
            fn={'基本面':score_fundamental,'技術面':score_technical,'熱門題材':score_theme}[mode]
            with st.spinner(f'透過 FinMind 深入分析候選股（最多 {len(candidates)} 檔），首次執行可能需要數分鐘…'):
                # 最多 6 個並行請求工作，避免對免費 API 突然造成大量併發。
                with ThreadPoolExecutor(max_workers=4) as ex:
                    futures={ex.submit(fn,str(r['代號']),token):(idx,r) for idx,(_,r) in enumerate(candidates.iterrows())}
                    completed={}
                    for fut in as_completed(futures):
                        idx,r=futures[fut]
                        try:completed[idx]=fut.result()
                        except Exception as e:completed[idx]=(np.nan,'分析失敗：'+str(e),{})
                for idx,(_,r) in enumerate(candidates.iterrows()):
                    result=completed.get(idx,(np.nan,'未取得分析結果',{}))
                    score,detail,extra=result
                    row={'代號':r['代號'],'名稱':r['名稱'],'市場':r['市場'],'資料日期':r['日期'],'收盤':r['收盤'],'漲跌':r['漲跌'],'成交金額':r['成交金額'],'分數':round(score,1) if pd.notna(score) else np.nan,'說明':detail}
                    if mode=='基本面' and isinstance(extra,dict):row.update(extra)
                    if mode=='技術面' and isinstance(extra,dict):row.update(extra)
                    if mode=='熱門題材' and extra:row['新聞標題（最多5則）']=' | '.join(extra)
                    rows.append(row)
            pool=pd.DataFrame(rows).sort_values('分數',ascending=False,na_position='last')
            valid=pool['分數'].notna().sum() if '分數' in pool else 0
            if valid==0:st.error(f'{mode}模式沒有取得足夠資料形成有效分數。請檢查 FinMind API 狀態／token／網路連線；不要把未評分股票當成低分股。')
            elif valid<len(pool):st.warning(f'{len(pool)} 檔候選股中只有 {valid} 檔取得可評分資料；缺值股票會排在最後。若出現額度限制，稍後再試或填入 FinMind token。')
        unseen=pool[~pool['代號'].astype(str).isin(st.session_state.seen)] if '代號' in pool else pool
        res=unseen.head(batch)
        st.subheader(f'本批結果｜{mode}・{level}')
        st.dataframe(res,use_container_width=True,hide_index=True)
        if st.button('再推薦下一批（最多 5 檔）',type='primary'):
            st.session_state.seen += res['代號'].astype(str).tolist(); st.rerun()
        st.download_button('下載本次分析 CSV',pool.to_csv(index=False).encode('utf-8-sig'),'taiwan_stock_screen.csv','text/csv')
        with st.expander('分數如何計算？'):
            if mode=='基本面':st.markdown('**基本面簡化分數**：月營收年增／月增（約 50% 權重）、本益比／股價淨值比（約 25%）、最新財報可辨識獲利科目（約 25%，若可取得）。權重會依成功取得的資料重新正規化。這不是完整財報品質模型，尚未充分評估現金流、負債、一次性損益、產業差異與會計期間。')
            elif mode=='技術面':st.markdown('**技術面簡化分數**：收盤價相對 20 日均線、20／60 日均線關係、20 日報酬、RSI(14)、當日量對 20 日均量。資料不足時不給分。')
            elif mode=='熱門題材':st.markdown('**熱門題材簡化分數**：以 FinMind 個股新聞標題匹配內建題材關鍵字，再以標題中少量正向／風險詞調整。這是關鍵字熱度，不是經過訓練的情緒模型；新聞涵蓋不完整，必須點開原文查證。')
            else:st.markdown('**市場面分數**：當日成交金額排名 60%＋單日漲跌排名 40%。這不是多日趨勢或投資報酬預測。')
    else:
        raw['分數']=raw['市場面分數']; raw['說明']='合成示範資料，僅供介面測試，並非真實股票。'
        st.dataframe(raw.head(batch),use_container_width=True,hide_index=True)
        st.info('示範資料不會呼叫 FinMind，也不應用來判斷真實股票。')
    st.download_button('下載目前行情 CSV',raw.to_csv(index=False).encode('utf-8-sig'),'taiwan_stock_snapshot.csv','text/csv')
    with st.expander('完整行情資料'):st.dataframe(raw,use_container_width=True,hide_index=True)

st.divider(); st.header('短期／中長期價格建議')
st.info('正式買賣價模型仍未啟用。本版已接入技術歷史資料，但尚未建立經過驗證的停損、目標價與基本面估值區間模型，因此不會輸出看似精準的買賣價格。')
st.markdown('- **短期（1–4 週）**：可先參考技術面分數、20 日均線、RSI、量比與波動；仍需加入 ATR、支撐壓力及交易成本後才能形成價格區間。\n- **中長期（3–12 個月）**：基本面分數可作初篩，還需要更完整的現金流、負債、獲利率、產業同業估值與情境分析。')

st.divider(); st.header('📊 歷史回測')
st.write('上傳 CSV 可試跑簡化動能回測，需包含 `date, code, close` 三欄，建議使用還原權息價格。')
up=st.file_uploader('上傳歷史行情 CSV',type=['csv'])
if up:
    try:
        p=pd.read_csv(up)
        if not {'date','code','close'}.issubset(p.columns):st.error('CSV 欄位必須是 date, code, close。')
        else:
            p['date']=pd.to_datetime(p['date'],errors='coerce'); p['code']=p['code'].astype(str); p['close']=pd.to_numeric(p['close'],errors='coerce'); p=p.dropna(subset=['date','code','close'])
            if p.date.nunique()<30 or p.code.nunique()<2:st.error('至少需要約 30 個交易日與 2 檔股票。')
            else:
                curve,s=backtest(p); cols=st.columns(4); cols[0].metric('累積報酬',f"{s['累積報酬']:.1%}"); cols[1].metric('年化報酬（粗估）',f"{s['年化報酬']:.1%}"); cols[2].metric('年化波動',f"{s['年化波動']:.1%}"); cols[3].metric('最大回撤',f"{s['最大回撤']:.1%}"); st.plotly_chart(px.line(curve,x='日期',y=['策略淨值','等權基準淨值']),use_container_width=True); st.download_button('下載回測曲線',curve.to_csv(index=False).encode('utf-8-sig'),'backtest_curve.csv','text/csv'); st.warning('簡化教學回測，未完整處理歷史股票名單、下市股、除權息、漲跌停、停牌及實際成交成本，不可視為可交易績效。')
    except Exception as e:st.error(f'回測失敗：{type(e).__name__}: {e}')

with st.expander('資料來源、免費額度與限制'):
    st.markdown('''| 資料 | 來源 | 本版整合狀態 |
|---|---|---|
| 上市／上櫃盤後行情 | TWSE／TPEx 官方公開端點 | 已整合連線診斷；端點欄位仍須以實際環境驗證 |
| 月營收 | FinMind `TaiwanStockMonthRevenue` | 基本面模式按候選股抓取，計算年增／月增 |
| PER／PBR | FinMind `TaiwanStockPER` | 基本面模式按候選股抓取 |
| 季財報 | FinMind `TaiwanStockFinancialStatements` | 嘗試辨識獲利科目；欄位格式或資料缺漏時會顯示提醒 |
| 歷史日線 | FinMind `TaiwanStockPrice` | 技術面模式計算均線、報酬、RSI、量比 |
| 個股新聞 | FinMind `TaiwanStockNews` | 熱門題材模式以標題關鍵字作初步分類，不等於真正新聞情緒模型 |
| 回測 | 使用者上傳歷史 CSV | 簡化動能策略，未達正式研究級 |

**免費額度提醒：** FinMind 文件說明匿名額度約 300 次／小時，註冊 token 可提高至 600 次／小時；免費方案主要供非商業用途。首次深入分析最多對候選股數執行資料抓取，且資料會快取 6 小時。若遇到 402／額度錯誤，請降低候選股數、稍後再試或設定 token。請遵守資料來源授權，不要未經許可對外轉售或大量再散布原始資料。''')
st.caption('資料不足時不應把缺值當成 0 分或宣稱完成分析。熱門題材是關鍵字提示，投資前應確認新聞日期、原文、公告及財報。')
