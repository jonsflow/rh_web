#!/usr/bin/env python3
"""
Position Enricher - builds a structured markdown report for LLM analysis.
Enriches positions with greeks, IV, underlying price, and DTE.
"""

import datetime
import os
import robin_stocks.robinhood as r
import pytz


def _dte(expiration_date: str) -> int:
    try:
        exp = datetime.datetime.strptime(expiration_date, '%Y-%m-%d').date()
        return max((exp - datetime.date.today()).days, 0)
    except Exception:
        return 0


def _moneyness(underlying: float, strike: float, option_type: str) -> str:
    if underlying <= 0 or strike <= 0:
        return "N/A"
    if option_type.lower() == 'call':
        diff_pct = (underlying - strike) / strike * 100
        label = "ITM" if underlying > strike else "OTM"
    else:
        diff_pct = (strike - underlying) / underlying * 100
        label = "ITM" if underlying < strike else "OTM"
    return f"{label} {abs(diff_pct):.1f}%"


def _fmt_price(val) -> str:
    try:
        return f"${float(val):.2f}"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_pct(val) -> str:
    try:
        return f"{float(val)*100:.1f}%"
    except (TypeError, ValueError):
        return "N/A"


def _fmt_greek(val) -> str:
    try:
        return f"{float(val):.4f}"
    except (TypeError, ValueError):
        return "N/A"


def build_position_report(positions: list, account_prefix: str) -> str:
    """
    Build an enriched markdown position report for LLM analysis.
    positions: list of LongPosition objects
    account_prefix: last-4 digits of account number
    Returns: markdown string
    """
    et = pytz.timezone('America/New_York')
    generated_at = datetime.datetime.now(et).strftime('%Y-%m-%d %H:%M:%S ET')

    # --- Per-Position Enrichment ---
    position_rows = []
    total_open_premium = 0.0
    total_current_value = 0.0

    for pos in positions:
        try:
            option_id = pos.option_ids[0] if pos.option_ids else None
            delta = gamma = theta = vega = iv = bid = ask = oi = "N/A"
            mark = pos.current_price

            if option_id:
                try:
                    md = r.get_option_market_data_by_id(option_id)
                    market_info = md[0] if isinstance(md, list) and md else md or {}
                    delta = _fmt_greek(market_info.get('delta'))
                    gamma = _fmt_greek(market_info.get('gamma'))
                    theta = _fmt_greek(market_info.get('theta'))
                    vega = _fmt_greek(market_info.get('vega'))
                    iv = _fmt_pct(market_info.get('implied_volatility'))
                    bid = _fmt_price(market_info.get('bid_price'))
                    ask = _fmt_price(market_info.get('ask_price'))
                    try:
                        oi = str(int(float(market_info.get('open_interest', 0))))
                    except (TypeError, ValueError):
                        oi = "N/A"
                    mark_raw = market_info.get('adjusted_mark_price')
                    if mark_raw:
                        mark = float(mark_raw)
                except Exception:
                    pass

            underlying_price = 0.0
            try:
                up = r.get_latest_price(pos.symbol, includeExtendedHours=False)
                underlying_price = float(up[0]) if up else 0.0
            except Exception:
                pass

            dte = _dte(pos.expiration_date)
            moneyness = _moneyness(underlying_price, pos.strike_price, pos.option_type)

            open_premium = pos.open_premium
            current_value = mark * pos.quantity * 100
            pnl = current_value - open_premium
            pnl_pct = (pnl / open_premium * 100) if open_premium > 0 else 0.0
            pnl_str = f"{'+' if pnl >= 0 else ''}{pnl_pct:.1f}%"

            total_open_premium += open_premium
            total_current_value += current_value

            exp_short = pos.expiration_date[5:].replace('-', '/')

            position_rows.append(
                f"| {pos.symbol} | {pos.option_type.upper()} | {pos.strike_price} | {pos.expiration_date} | {exp_short} | {dte} | {pos.quantity} "
                f"| ${open_premium:.2f} | ${mark:.2f} | {pnl_str} "
                f"| {delta} | {theta} | {iv} | ${underlying_price:.2f} "
                f"| {moneyness} | {bid} | {ask} | {oi} |"
            )
        except Exception as e:
            position_rows.append(f"| {pos.symbol} | Error: {e} | | | | | | | | | | | | | | | | |")

    if position_rows:
        positions_table = "\n".join([
            "| Symbol | Type | Strike | Expiration | Exp | DTE | Qty | Open Premium | Mark | P&L% | Delta | Theta | IV | Underlying | Moneyness | Bid | Ask | OI |",
            "|--------|------|--------|------------|-----|-----|-----|-------------|------|------|-------|-------|----|-----------|-----------|-----|-----|-----|",
        ] + position_rows)
    else:
        positions_table = "_No positions found._"

    net_pnl = total_current_value - total_open_premium
    net_pnl_pct = (net_pnl / total_open_premium * 100) if total_open_premium > 0 else 0.0
    net_sign = "+" if net_pnl >= 0 else ""

    # Build the YAML template Claude should fill in
    yaml_template_rows = []
    for pos in positions:
        yaml_template_rows.append(f"""  - symbol: {pos.symbol}
    option_type: {pos.option_type.upper()}
    strike: {pos.strike_price}
    expiration: "{pos.expiration_date}"
    action: HOLD            # HOLD | CLOSE | REDUCE
    stop_loss_pct: 20       # trailing stop % drop from current mark price to trigger exit
    take_profit_pct: 50     # % gain from open premium at which to take profit
    notes: "Your rationale here."
""")
    yaml_template = "\n".join(yaml_template_rows)

    report = f"""# Open Positions Report — Account ...{account_prefix}
Generated: {generated_at}

## Open Positions
{positions_table}

## Portfolio Summary
- Total Positions: {len(positions)}
- Total Open Premium: ${total_open_premium:,.2f}
- Total Current Value: ${total_current_value:,.2f}
- Net P&L: {net_sign}${net_pnl:,.2f} ({net_sign}{net_pnl_pct:.1f}%)

---

## Instructions

Analyze the positions above. Consider sector exposure, DTE, IV rank, delta, theta decay, and P&L.

Write your response as a YAML file saved to:
`exports/recommendations_{account_prefix}.yaml`

Use **exactly** this schema (the app parses and renders it):

```yaml
account: "{account_prefix}"
analyzed_at: "YYYY-MM-DD HH:MM:SS"
summary: "1-2 sentence overall portfolio assessment."

positions:
{yaml_template}```

Rules:
- Include a row for **every** position listed above.
- `symbol`, `option_type`, `strike`, and `expiration` must match the table exactly (used to match positions in the app).
- `action`: HOLD = keep monitoring, CLOSE = exit now, REDUCE = consider partial close.
- `stop_loss_pct`: percent drop in option mark price from current value that justifies an exit (e.g. 20 means exit if price falls 20% from here).
- `take_profit_pct`: percent gain from open premium at which to lock in profit (e.g. 50 means exit when position is up 50%).
- `notes`: 1-2 sentences max. Focus on the key risk or opportunity.
"""
    return report


def write_position_report(positions: list, account_prefix: str, exports_dir: str) -> tuple:
    """Build and write position report to disk. Returns (report_str, filepath)."""
    os.makedirs(exports_dir, exist_ok=True)
    report = build_position_report(positions, account_prefix)
    filepath = os.path.join(exports_dir, f"positions_{account_prefix}.md")
    with open(filepath, 'w') as f:
        f.write(report)
    return report, filepath
