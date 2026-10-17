"""Métricas sin números ficticios para muestras vacías."""
from __future__ import annotations

def summarize(trades: list[dict], initial_equity: float, final_equity: float, max_drawdown: float) -> dict:
    wins = [t["pnl_usd"] for t in trades if t["pnl_usd"] > 0]
    losses = [t["pnl_usd"] for t in trades if t["pnl_usd"] < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    pf = gross_win / gross_loss if gross_loss > 0 else None
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100*len(wins)/len(trades), 3) if trades else None,
        "profit_factor": round(pf, 4) if pf is not None else None,
        "expectancy_usd": round(sum(t["pnl_usd"] for t in trades)/len(trades), 4) if trades else None,
        "mean_R": round(sum(t["realized_R"] for t in trades)/len(trades), 4) if trades else None,
        "max_drawdown_pct": round(100*max_drawdown, 3),
        "return_pct": round(100*(final_equity/initial_equity-1), 3),
        "initial_equity": round(initial_equity, 2),
        "final_equity": round(final_equity, 2),
    }
