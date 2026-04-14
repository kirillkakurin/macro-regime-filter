import os
import math
import time
import pandas as pd
import yfinance as yf
from google import genai
from fredapi import Fred
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv("api.env")

fred_api_key = os.getenv("FRED_API_KEY")
fred = Fred(api_key=fred_api_key)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

output_dir = "outputs"
filename = f"macro_report_{datetime.now().strftime('%Y-%m-%d')}.txt"
filepath = os.path.join(output_dir, filename)

output_file = open(filepath, "w")
report_lines = []

def log_print(text):
    print(text)
    output_file.write(text + "\n")
    report_lines.append(text)

series_ids = ['DGS10', 'DGS5', 'DGS2', 'DGS3MO']
tickers = ['QQQ', 'SPY']

start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')


log_print(f"Run Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

#FRED rates

rate_labels = {
    'DGS10': 'DGS10 (10Y Yield)',
    'DGS5': 'DGS5 (5Y Yield)',
    'DGS2': 'DGS2 (2Y Yield)',
    'DGS3MO': 'DGS3MO (3M Yield)'
}

def pull_yield_data(series_ids, start_date):
    data_frames = []

    def get_fred_series_with_retry(series_id, start_date, retries=3):
        for attempt in range(retries):
            try:
                return fred.get_series(series_id, start=start_date)
            except Exception as e:
                print(f"Retry {attempt+1}/{retries} for {series_id}: {e}")
                time.sleep(2)

        raise Exception(f"Failed to fetch {series_id} after retries")

    for series_id in series_ids:
        data = get_fred_series_with_retry(series_id, start_date)
        data_frames.append(data.rename(series_id))

    df = pd.concat(data_frames, axis=1)
    df.index.name = 'Date'
    df = df.dropna().sort_index()

    return df

rates_df = pull_yield_data(series_ids, start_date)

#yfinance equities

def pull_equity_data(tickers):
    data = yf.download(tickers, period='60d', interval='1d', auto_adjust=False)['Adj Close']
    data = data.dropna().sort_index()
    return data

equity_df = pull_equity_data(tickers)

#rates calculations
rates_pct = rates_df.pct_change()
rates_1d = rates_pct.iloc[-1] * 100
rates_5d = ((rates_df.iloc[-1] / rates_df.iloc[-6]) - 1) * 100
rates_latest = rates_df.iloc[-1]

#yield curve calculations

#create curve
rates_df['curve_10y_2y'] = rates_df['DGS10'] - rates_df['DGS2']

#absolute changes
rates_df['curve_1D'] = rates_df['curve_10y_2y'].diff(1)
rates_df['curve_5D'] = rates_df['curve_10y_2y'].diff(5)

curve_latest = rates_df.iloc[-1]

#equities calculations
equity_df['QQQ_1D'] = equity_df['QQQ'].pct_change(1)
equity_df['QQQ_5D'] = equity_df['QQQ'].pct_change(5)
equity_df['QQQ_10D'] = equity_df['QQQ'].pct_change(10)

equity_df['SPY_1D'] = equity_df['SPY'].pct_change(1)
equity_df['SPY_5D'] = equity_df['SPY'].pct_change(5)
equity_df['SPY_10D'] = equity_df['SPY'].pct_change(10)

equity_df['ratio'] = equity_df['QQQ'] / equity_df['SPY']
equity_df['ratio_1D'] = equity_df['ratio'].pct_change(1)
equity_df['ratio_5D'] = equity_df['ratio'].pct_change(5)

equity_latest = equity_df.iloc[-1]

#output
log_print("\n" + "="*40)
log_print("**MACRO SNAPSHOT**")
log_print("="*40)  

log_print("\n **RATES:**")
for s in series_ids:
    label = rate_labels[s]
    val = rates_latest[s]
    one_d = rates_1d[s]
    five_d = rates_5d[s]

    sign1 = '+' if one_d >= 0 else ''
    sign5 = '+' if five_d >= 0 else ''

    log_print(f"{label}: {val:.2f} | 1D: {sign1}{one_d:.1f}% | 5D: {sign5}{five_d:.1f}%")

log_print("\n **YIELD CURVE (10Y - 2Y):**")

log_print(f"Value: {curve_latest['curve_10y_2y']:.2f} | 1D: {curve_latest['curve_1D']:+.2f} | 5D: {curve_latest['curve_5D']:+.2f}")

log_print("\n **EQUITIES:**")
log_print(f"QQQ: {equity_latest['QQQ']:.2f} | 1D: {equity_latest['QQQ_1D']:.2%} | 5D: {equity_latest['QQQ_5D']:.2%} | 10D: {equity_latest['QQQ_10D']:.2%}")
log_print(f"SPY: {equity_latest['SPY']:.2f} | 1D: {equity_latest['SPY_1D']:.2%} | 5D: {equity_latest['SPY_5D']:.2%} | 10D: {equity_latest['SPY_10D']:.2%}")

log_print("\n **QQQ/SPY (Growth vs Market):**")
log_print(f"Value: {equity_latest['ratio']:.4f} | 1D: {equity_latest['ratio_1D']:.2%} | 5D: {equity_latest['ratio_5D']:.2%}")

#HYG / TLT (сredit vs duration)
credit_tickers = ['HYG', 'TLT']
credit_df = yf.download(credit_tickers, period='60d', interval='1d', auto_adjust=False, progress=False)['Adj Close']
credit_df = credit_df.dropna().sort_index()

#% changes
credit_df['HYG_1D'] = credit_df['HYG'].pct_change(1)
credit_df['HYG_5D'] = credit_df['HYG'].pct_change(5)
credit_df['HYG_10D'] = credit_df['HYG'].pct_change(10)

credit_df['TLT_1D'] = credit_df['TLT'].pct_change(1)
credit_df['TLT_5D'] = credit_df['TLT'].pct_change(5)
credit_df['TLT_10D'] = credit_df['TLT'].pct_change(10)

#ratio
credit_df['hyg_tlt_ratio'] = credit_df['HYG'] / credit_df['TLT']
credit_df['ratio_1D'] = credit_df['hyg_tlt_ratio'].pct_change(1)
credit_df['ratio_5D'] = credit_df['hyg_tlt_ratio'].pct_change(5)
credit_df['ratio_10D'] = credit_df['hyg_tlt_ratio'].pct_change(10)

credit_latest = credit_df.iloc[-1]

#outputs

log_print("\n **CREDIT / DURATION:**")

log_print(f"HYG: {credit_latest['HYG']:.2f} | 1D: {credit_latest['HYG_1D']:.2%} | 5D: {credit_latest['HYG_5D']:.2%} | 10D: {credit_latest['HYG_10D']:.2%}")
log_print(f"TLT: {credit_latest['TLT']:.2f} | 1D: {credit_latest['TLT_1D']:.2%} | 5D: {credit_latest['TLT_5D']:.2%} | 10D: {credit_latest['TLT_10D']:.2%}")

log_print("\n **HYG/TLT (Risk vs Duration):**")
log_print(f"Value: {credit_latest['hyg_tlt_ratio']:.4f} | 1D: {credit_latest['ratio_1D']:.2%} | 5D: {credit_latest['ratio_5D']:.2%} | 10D: {credit_latest['ratio_10D']:.2%}")

#vix (vol)

vix_df = yf.download('^VIX', period='60d', interval='1d', auto_adjust=False, progress=False)['Adj Close']
vix_df = vix_df.dropna().sort_index()

#% changes
vix_df = pd.DataFrame(vix_df)
vix_df.columns = ['VIX']

vix_df['VIX_1D'] = vix_df['VIX'].pct_change(1)
vix_df['VIX_5D'] = vix_df['VIX'].pct_change(5)
vix_df['VIX_10D'] = vix_df['VIX'].pct_change(10)

vix_latest = vix_df.iloc[-1]

#outputs
log_print("\n **VOLATILITY:**")

log_print(f"VIX: {vix_latest['VIX']:.2f} | 1D: {vix_latest['VIX_1D']:.2%} | 5D: {vix_latest['VIX_5D']:.2%} | 10D: {vix_latest['VIX_10D']:.2%}")


#dxy , fx
dollar_tickers = ['UUP', 'EURUSD=X']
dollar_df = yf.download(dollar_tickers, period='60d', interval='1d', auto_adjust=False, progress=False)['Adj Close']
dollar_df = dollar_df.dropna().sort_index()

#% changes
dollar_df['UUP_1D'] = dollar_df['UUP'].pct_change(1)
dollar_df['UUP_5D'] = dollar_df['UUP'].pct_change(5)
dollar_df['UUP_10D'] = dollar_df['UUP'].pct_change(10)

dollar_df['EURUSD_1D'] = dollar_df['EURUSD=X'].pct_change(1)
dollar_df['EURUSD_5D'] = dollar_df['EURUSD=X'].pct_change(5)
dollar_df['EURUSD_10D'] = dollar_df['EURUSD=X'].pct_change(10)

dollar_latest = dollar_df.iloc[-1]

log_print("\n **DOLLAR / FX:**")
log_print(f"UUP (DXY Proxy): {dollar_latest['UUP']:.2f} | 1D: {dollar_latest['UUP_1D']:.2%} | 5D: {dollar_latest['UUP_5D']:.2%}")
log_print(f"EURUSD: {dollar_latest['EURUSD=X']:.4f} | 1D: {dollar_latest['EURUSD_1D']:.2%} | 5D: {dollar_latest['EURUSD_5D']:.2%}")

#lqd, investment grade credit, optional for now

# credit_df['LQD'] = yf.download('LQD', period='60d', interval='1d', auto_adjust=False)['Adj Close']
# credit_df['LQD_1D'] = credit_df['LQD'].pct_change(1)
# credit_df['LQD_5D'] = credit_df['LQD'].pct_change(5)
# credit_df['LQD_10D'] = credit_df['LQD'].pct_change(10)

# log_print("\nINVESTMENT GRADE (LQD):")
# log_print(f"LQD: {credit_df.iloc[-1]['LQD']:.2f} | 1D: {credit_df.iloc[-1]['LQD_1D']:.2%} | 5D: {credit_df.iloc[-1]['LQD_5D']:.2%}")

#scoring functions
def score_rates(rates_1d, rates_5d, curve_latest):
    score = 0

    for key in ['DGS10', 'DGS2']:
        if rates_1d[key] > 0:
            score -= 0.5
        else:
            score += 0.5

        if rates_5d[key] < 0:
            score += 0.25
        else:
            score -= 0.25

    if curve_latest['curve_5D'] > 0:
        score += 0.5
    elif curve_latest['curve_5D'] < 0:
        score -= 0.5

    return max(-1, min(1, score))


def score_equities(equity_latest):
    score = 0

    if equity_latest['QQQ_5D'] > 0:
        score += 0.5
    else:
        score -= 0.5

    if equity_latest['SPY_5D'] > 0:
        score += 0.5
    else:
        score -= 0.5

    return max(-1, min(1, score))


def score_growth(equity_latest):
    if equity_latest['ratio_5D'] > 0:
        return 1
    elif equity_latest['ratio_5D'] < 0:
        return -1
    return 0


def score_credit(credit_latest):
    if credit_latest['ratio_5D'] > 0:
        return 1
    elif credit_latest['ratio_5D'] < 0:
        return -1
    return 0


def score_vix(vix_latest):
    score = 0

    if vix_latest['VIX_5D'] < 0:
        score += 0.7
    else:
        score -= 0.7

    if vix_latest['VIX_1D'] > 0:
        score -= 0.3
    else:
        score += 0.3

    return max(-1, min(1, score))


def score_dollar(dollar_latest):
    if dollar_latest['UUP_5D'] < 0:
        return 1
    elif dollar_latest['UUP_5D'] > 0:
        return -1
    return 0

def compute_macro_regime(
    rates_score,
    vix_score,
    credit_score,
    equities_score,
    growth_score,
    dollar_score
):
    weights = {
        "rates": 0.30,
        "vix": 0.20,
        "credit": 0.15,
        "equities": 0.15,
        "growth": 0.10,
        "dollar": 0.10
    }

    score = (
        rates_score * weights["rates"] +
        vix_score * weights["vix"] +
        credit_score * weights["credit"] +
        equities_score * weights["equities"] +
        growth_score * weights["growth"] +
        dollar_score * weights["dollar"]
    )

    bullish_pct = (score + 1) / 2 * 100
    bullish_pct = max(0, min(100, bullish_pct))

    signals = [rates_score, vix_score, credit_score, equities_score, growth_score, dollar_score]

    bullish = sum(1 for s in signals if s > 0)
    bearish = sum(1 for s in signals if s < 0)
    total = bullish + bearish

    confidence = (max(bullish, bearish) / total * 100) if total > 0 else 0

    if bullish_pct > 60:
        regime = "BULLISH"
    elif bullish_pct < 40:
        regime = "BEARISH"
    else:
        regime = "NEUTRAL"

    return score, bullish_pct, confidence, regime

#scoring & confidence output
def print_macro_summary(score, bullish_pct, confidence, regime, file=None):
    lines = [
        "="*40,
        "**MACRO REGIME SUMMARY**",
        "="*40,
        f"Bias: {regime}",
        f"Bullish Probability: {bullish_pct:.1f}%",
        f"Confidence: {confidence:.1f}%",
        f"Score: {score:.3f}",
        "="*40
    ]   

    for line in lines:
        log_print(line)
        if file:
            file.write(line + "\n")

#scores
rates_score = score_rates(rates_1d, rates_5d, curve_latest)
equities_score = score_equities(equity_latest)
growth_score = score_growth(equity_latest)
credit_score = score_credit(credit_latest)
vix_score = score_vix(vix_latest)
dollar_score = score_dollar(dollar_latest)

#final regime computation
score, bullish_pct, confidence, regime = compute_macro_regime(
    rates_score,
    vix_score,
    credit_score,
    equities_score,
    growth_score,
    dollar_score
)

# OUTPUT SUMMARY FIRST
print_macro_summary(score, bullish_pct, confidence, regime)

# BUILD FULL REPORT TEXT FOR GEMINI
macro_output = "\n".join(report_lines)

# CREATE GEMINI PROMPT
prompt = f"""
You are a professional macro market analyst.

Analyze the following Nasdaq macro dashboard briefly.

Explain:
1. What the current macro regime suggests
2. Whether this is bullish or bearish for NQ
3. Main supporting and opposing forces

Keep response concise and professional.

Dashboard:
{macro_output}
"""

# CALL GEMINI
try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    gemini_analysis = response.text

except Exception as e:
    gemini_analysis = f"Gemini API Error: {e}"

# WRITE GEMINI ANALYSIS TO OUTPUT
log_print("\n" + "=" * 40)
log_print("**AI ANALYSIS**")
log_print("=" * 40)
log_print(gemini_analysis)

# CLOSE FILE
output_file.close()
