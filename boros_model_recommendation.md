# Boros Bot Model Recommendation

## The Core Problem

Your bot doesn't need a model that predicts *where rates will go*. It needs a model that answers one question:

> **"What is the probability my resting order at tick X gets filled in the next N epochs, given the current state of the market?"**

If that probability is low → keep the order, earn rewards.  
If that probability crosses a threshold → cancel, wait, repost.

Everything else — placement logic, purge avoidance, emergency cancellation — flows from the answer to that question.

---

## Why Standard Models Don't Fit

### ❌ Traditional Market-Making Models (Avellaneda-Stoikov, Guéant-Lehalle-Fernandez-Tapia)

These are designed for makers who **profit from fills** by capturing bid-ask spread. Their entire framework optimizes *inventory accumulation and unwinding*. In your strategy, fills are the **loss event**, not the profit event. The objective function is inverted — you want to maximize time-in-range while minimizing fill probability. Avellaneda-Stoikov would tell you to tighten your spread to attract fills. That's the opposite of what you want.

### ❌ Standard Price Prediction / Forecasting Models (ARIMA, LSTM, Prophet)

These predict where a price will be at time T. You don't care where the implied APR will be — you care whether it will *touch a specific level* between now and T. That's a first-passage time problem, not a point forecast problem. A model that tells you "the rate will be -1.1% tomorrow" is useless if it doesn't tell you whether it will *pass through -1.34%* on the way there.

### ❌ Black-Scholes / Traditional IRS Pricing Models (Hull-White, HJM)

These price the fair value of interest rate derivatives. You're not trying to price a swap — you're trying to avoid entering one. These models are also designed for deep, liquid institutional markets. Boros is a thin, crypto-native CLOB with discrete tick levels and an AMM backstop. The liquidity microstructure is completely different.

### ❌ Pure ML / Deep Learning

- **Data scarcity**: Boros launched recently. You have at most a few months of NDJSON data across a handful of markets. Any neural network trained on this will memorize, not generalize.
- **Non-stationarity**: The market structure itself is evolving — new participants, changing incentive ranges, new maturities rolling in. A model trained on April data may be useless by June.
- **Interpretability**: When the model says "cancel now," you need to know *why*. Is it because of rate velocity? Regime shift? Oracle staleness? A black box doesn't give you that, and in a thin market where a single bad fill can wipe weeks of rewards, you can't afford to not understand your own decisions.

---

## Recommended Model: Layered Stochastic + Regime Architecture

Three layers, each simple and interpretable, stacked to give you what you need.

```
┌─────────────────────────────────────────────────────┐
│           LAYER 3: DECISION ENGINE                   │
│  Combine fill probability + regime state             │
│  → place / hold / cancel / emergency                 │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│           LAYER 2: REGIME DETECTOR (HMM)             │
│  Identify market state: Calm / Volatile / Trending   │
│  Condition Layer 1 parameters on current regime      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│           LAYER 1: RATE DYNAMICS (OU PROCESS)        │
│  Model implied APR as mean-reverting process         │
│  Compute P(rate reaches level X within time T)       │
└─────────────────────────────────────────────────────┘
```

---

### Layer 1: Ornstein-Uhlenbeck (OU) Process for Rate Dynamics

#### Why OU?

Funding rates are **mean-reverting by design**. They exist to pull perpetual futures prices back toward spot. When funding deviates significantly, arbitrageurs enter, pushing it back. The implied APR on Boros inherits this property — it's a market consensus on the average *future* funding rate, and extreme deviations attract counterparties.

The Ornstein-Uhlenbeck process is the canonical continuous-time model for mean-reverting processes. It's the backbone of the Vasicek interest rate model, which is literally designed for this exact type of asset — short-term interest rates.

#### The Model

```
dR(t) = θ(μ - R(t))dt + σ dW(t)
```

Where:
- `R(t)` = implied APR at time t
- `μ` = long-term mean APR (estimated from data)
- `θ` = mean-reversion speed (how fast rates pull back to μ)
- `σ` = volatility (how much rates fluctuate around the path)
- `W(t)` = standard Brownian motion

#### What You Get From It

The OU process gives you **closed-form solutions** for the quantities you actually care about:

**1. Fill probability (first-passage time)**

P(R(t) reaches level L at any point before time T | R(0) = current rate)

For an OU process, the first-passage time distribution doesn't have a simple closed form, but excellent approximations exist (Ricciardi & Sato, 1988). For your use case, a **Monte Carlo simulation** of the OU process is perfectly adequate and fast — simulate 10,000 paths per epoch, count how many touch your order level.

```python
import numpy as np

def fill_probability(current_rate, order_level, mu, theta, sigma, T, n_sims=10000, dt=0.001):
    """
    Monte Carlo estimate of P(OU process starting at current_rate 
    reaches order_level before time T).
    """
    n_steps = int(T / dt)
    hits = 0
    for _ in range(n_sims):
        r = current_rate
        for _ in range(n_steps):
            r += theta * (mu - r) * dt + sigma * np.sqrt(dt) * np.random.randn()
            if (order_level > current_rate and r >= order_level) or \
               (order_level < current_rate and r <= order_level):
                hits += 1
                break
    return hits / n_sims
```

> [!TIP]
> Vectorize with NumPy for speed — simulate all 10k paths simultaneously instead of looping. This brings runtime from seconds to milliseconds.

**2. Expected time to fill**

E[τ | R(0), target level] — how long on average before a fill occurs. This tells you whether you have minutes or days of margin.

**3. Rate distribution at time T**

The conditional distribution R(T) | R(0) is Gaussian for OU:
```
R(T) | R(0) ~ N(μ + (R(0) - μ)e^(-θT), σ²(1 - e^(-2θT)) / (2θ))
```

This lets you compute the probability that the rate will be in a particular range at epoch-end, useful for purge risk estimation.

#### Parameter Estimation

Estimate `μ`, `θ`, `σ` from historical data using **Maximum Likelihood Estimation (MLE)** on discrete observations. For equally-spaced observations of an OU process:

```python
import numpy as np

def estimate_ou_params(rates, dt):
    """
    MLE for OU parameters from discrete observations.
    rates: array of observed implied APR values
    dt: time between observations (in years, or consistent units)
    """
    n = len(rates) - 1
    r = np.array(rates)
    
    # Regression: R(t+1) = a + b * R(t) + noise
    x = r[:-1]
    y = r[1:]
    
    b = np.sum((x - x.mean()) * (y - y.mean())) / np.sum((x - x.mean())**2)
    a = y.mean() - b * x.mean()
    
    # Convert to OU parameters
    theta = -np.log(b) / dt
    mu = a / (1 - b)
    
    residuals = y - (a + b * x)
    sigma_discrete = np.std(residuals)
    sigma = sigma_discrete * np.sqrt(2 * theta / (1 - np.exp(-2 * theta * dt)))
    
    return mu, theta, sigma
```

> [!IMPORTANT]
> Use a **rolling window** (e.g., last 7-14 days) for parameter estimation, not the full history. The market's characteristics drift over time — a static calibration from week 1 won't describe week 8. Re-estimate every epoch or every few hours.

---

### Layer 2: Hidden Markov Model (HMM) for Regime Detection

#### Why Regimes Matter

A single set of OU parameters assumes the market behaves the same way all the time. It doesn't. Crypto funding rates exhibit clear regime shifts:

| Regime | Characteristics | Impact on Your Strategy |
|---|---|---|
| **Calm** | Low volatility, rates hover near mean | Safe to farm. Low fill risk. |
| **Volatile** | High volatility, rates swing widely | Fill risk spikes. May need to cancel one side. |
| **Trending** | Sustained directional move (e.g., persistent negative funding) | One side is at high fill risk. The other side is safe but may get purged. |

An HMM identifies which regime you're currently in, without you having to manually define thresholds. It learns the regimes from data.

#### The Model

Use a 2–3 state Gaussian HMM on the **changes in implied APR** (ΔR per epoch):

```python
from hmmlearn import GaussianHMM

def fit_regime_model(rate_changes, n_regimes=3):
    """
    Fit HMM to rate changes to identify market regimes.
    rate_changes: array of (R(t) - R(t-1)) values
    """
    model = GaussianHMM(
        n_components=n_regimes,
        covariance_type="full",
        n_iter=100,
        random_state=42
    )
    X = rate_changes.reshape(-1, 1)
    model.fit(X)
    
    # Decode most likely state sequence
    states = model.predict(X)
    
    # Get per-state parameters
    for i in range(n_regimes):
        mask = states == i
        print(f"Regime {i}: mean_change={model.means_[i][0]:.6f}, "
              f"volatility={np.sqrt(model.covars_[i][0][0]):.6f}, "
              f"frequency={mask.mean():.1%}")
    
    return model, states
```

#### How It Feeds Layer 1

Each HMM regime gets its **own set of OU parameters**:

```python
# Per-regime OU calibration
for regime_id in range(n_regimes):
    regime_rates = rates[states == regime_id]
    mu_r, theta_r, sigma_r = estimate_ou_params(regime_rates, dt)
    regime_params[regime_id] = (mu_r, theta_r, sigma_r)
```

When the HMM detects you've transitioned to the "Volatile" regime, the OU fill probability computation uses the higher-σ parameters, correctly inflating the fill risk estimate.

> [!NOTE]
> Start with **2 states** (Calm / Volatile). Only add a third (Trending) if the data clearly supports it. With limited Boros history, 3 states risk overfitting. You can always upgrade later.

#### Augmenting HMM Features

Don't feed the HMM only rate changes. Add:
- **Underlying funding rate** from Binance/OKX/Hyperliquid (the actual rate the IRS references)
- **Basis spread** = Implied APR − Underlying APR (how mispriced the Boros market is vs. the source)
- **Open interest proxy** (if available from order book depth data)

This gives the HMM more signal to identify regimes from.

---

### Layer 3: Decision Engine

This is the simple, rule-based layer that translates model outputs into actions. No ML here — just thresholds and logic you can inspect and tune.

```python
def decide_action(
    fill_prob_bid,      # P(fill on bid side) from Layer 1
    fill_prob_ask,      # P(fill on ask side) from Layer 1
    current_regime,     # from Layer 2
    time_to_maturity,   # days remaining
    oracle_staleness,   # now - fTime
    max_update_delay,   # from market config
    net_balance_ratio,  # net_balance / maintenance_margin
):
    # Circuit breakers (hard stops — override everything)
    if oracle_staleness > max_update_delay:
        return "CANCEL_ALL", "Oracle stale"
    if net_balance_ratio < 1.5:
        return "EMERGENCY_CLOSE", "Margin danger"
    if time_to_maturity < 14:  # days
        return "MIGRATE_MATURITY", "Approaching expiry"
    
    # Regime-based adjustments
    if current_regime == "VOLATILE":
        fill_threshold = 0.05   # Tighter: cancel if >5% fill prob
    elif current_regime == "TRENDING":
        fill_threshold = 0.03   # Even tighter during trends
    else:  # CALM
        fill_threshold = 0.15   # Relaxed: allow up to 15%
    
    actions = []
    
    if fill_prob_bid > fill_threshold:
        actions.append(("CANCEL_BID", f"P(fill)={fill_prob_bid:.1%}"))
    else:
        actions.append(("HOLD_BID", f"P(fill)={fill_prob_bid:.1%}"))
    
    if fill_prob_ask > fill_threshold:
        actions.append(("CANCEL_ASK", f"P(fill)={fill_prob_ask:.1%}"))
    else:
        actions.append(("HOLD_ASK", f"P(fill)={fill_prob_ask:.1%}"))
    
    return actions
```

> [!WARNING]
> The fill probability thresholds (5%, 15%, etc.) are **initial guesses**. These are the primary tuning knobs of the entire system. They must be calibrated through backtesting and then refined during paper trading. Do not go live with untested thresholds.

---

## Why This Architecture Over Alternatives

| Approach | Problem |
|---|---|
| Pure rule-based (no model) | You're flying blind on fill risk. "Cancel if rate moves 0.1%" is arbitrary and either too tight (constant churn, lost reward time) or too loose (unexpected fills). |
| Pure ML (LSTM/transformer) | Data-starved, non-interpretable, overfits on thin market data. When it fails, you won't know why until you've taken a loss. |
| Off-the-shelf MM model | Designed for the wrong objective (profit from fills, not avoidance of fills). |
| Full stochastic model (jump-diffusion, Lévy) | Overkill for this application. OU captures 90% of the dynamics. Jumps in funding rates are real but rare, and your circuit breakers handle them — you don't need the model to predict black swans, just to detect when conditions are deteriorating. |
| **OU + HMM + Rules (recommended)** | Matches the physics of the underlying (mean-reverting rates), adapts to regime changes, stays interpretable, needs minimal data to calibrate. |

---

## Validation Plan

### Phase 1: Historical Backtest (Before Any Live Capital)

**Data**: Download Boros NDJSON from `https://historical-data.boros.finance`. You need:
- Implied APR time series (from OHLCV or order book midpoint)
- Trade data (to verify when orders at CLO edges would have filled)
- Supplementary: Binance/OKX/Hyperliquid funding rate history

**Procedure**:

```
For each market with sufficient history (>30 days):
    1. Split data: 70% train / 30% test (chronological, no shuffle)
    2. On train set:
       a. Estimate OU parameters (rolling 7-day windows)
       b. Fit HMM (2-3 states)
       c. Calibrate per-regime OU parameters
    3. On test set:
       a. Walk-forward: at each epoch, use model to compute P(fill)
       b. Record actual fill events (did implied APR touch CLO edge?)
       c. Compare predicted P(fill) vs actual fill frequency
```

**Metrics to compute**:

| Metric | What It Tells You | Target |
|---|---|---|
| **Brier Score** | Calibration of fill probability predictions. Lower = better calibrated. | < 0.05 |
| **AUC-ROC** | Discrimination — can the model distinguish "will fill" from "won't fill" epochs? | > 0.75 |
| **Precision @ cancel threshold** | When the model says "cancel," how often was a fill actually imminent? | > 50% |
| **Recall @ cancel threshold** | Of all actual fills, how many did the model flag in advance? | > 80% |
| **Reward-hours preserved** | % of total time orders remain in range and earning. | > 85% |
| **Net P&L** | rewards earned − fill losses − gas costs | Positive |

> [!IMPORTANT]
> The single most important validation is **calibration**. If the model says "10% fill probability," then across all epochs where it said 10%, fills should occur roughly 10% of the time. Plot a **reliability diagram** (predicted probability vs. observed frequency). If the curve hugs the diagonal, the model is calibrated. If it's far off, you can't trust the thresholds.

### Phase 2: Parameter Sensitivity Analysis

Sweep the key parameters and measure how sensitive net P&L is:

```
For theta in [0.5x, 1x, 2x baseline]:
  For sigma in [0.5x, 1x, 2x baseline]:
    For fill_threshold in [0.03, 0.05, 0.10, 0.15, 0.20]:
      Run backtest → record net P&L, fill count, reward-hours
```

You want a strategy that is **robust** — if net P&L flips negative when sigma is 1.5x its baseline estimate, the model is too fragile. You want a region of parameter space where the strategy is comfortably positive.

### Phase 3: Paper Trading (2–4 Weeks)

Before live capital:
1. Run the full bot logic against live Boros data feeds
2. Log every decision: "would have placed at tick -135, would have cancelled at epoch 847 because P(fill)=0.12 > threshold 0.10"
3. Compare against what actually happened
4. Track:
   - **Phantom fills**: How many times would your orders have been filled?
   - **Phantom reward time**: How many epochs were your orders in-range?
   - **Decision accuracy**: When the model cancelled, was a fill imminent?

### Phase 4: Live (Small Size → Scale)

1. Start with **minimum viable order size** on a single market
2. Run for 2 weeks. Compare live results to paper trading results
3. If they match (within statistical noise): scale order size
4. If they diverge: something in the live execution pipeline is different from simulation (latency, gas failures, order purge timing). Debug before scaling.

---

## Implementation Dependencies

```
# Core
numpy           # OU simulation, parameter estimation
scipy           # Statistical tests, optimization

# Regime detection  
hmmlearn        # Gaussian HMM (pip install hmmlearn)

# Validation
scikit-learn    # AUC-ROC, Brier score, calibration curves
matplotlib      # Reliability diagrams, regime plots

# Data
requests        # Boros API, Binance API
web3            # On-chain oracle reads (fIndexOracle)
```

---

## Practical Starting Point

Don't try to build all three layers at once. Start here:

### Step 1: Get the data pipeline working
Download Boros NDJSON. Parse implied APR time series. Plot it. Look at it. Develop intuition for how it moves.

### Step 2: Fit OU on a single market
Estimate μ, θ, σ on Binance ETHUSDT 29 May 2026 (your calibrated market). Simulate paths. Do they look like the real data?

### Step 3: Compute fill probabilities and backtest
Using the OU model, compute P(fill at CLO edge) for each historical epoch. Compare to actual fills. Are the probabilities reasonable?

### Step 4: Add HMM
Fit 2-state HMM. Does it identify periods you can visually see as "calm" vs. "volatile"? Do per-regime OU parameters differ meaningfully?

### Step 5: Build the decision engine
Wire everything together. Backtest the full strategy. Tune thresholds.

### Step 6: Paper trade → Live

---

## Summary

| Question | Answer |
|---|---|
| Use an existing model? | No — no off-the-shelf model matches the "avoid fills while farming rewards" objective. |
| Build from scratch with ML? | No — insufficient data, overfitting risk, interpretability loss. |
| What to build? | **OU process** (fill probability) + **HMM** (regime detection) + **rule-based decision engine**. |
| Why? | OU matches the physics of mean-reverting rates. HMM adapts to changing market conditions. Rules stay interpretable. All three are cheap to calibrate on limited data. |
| How to validate? | Backtest on Boros NDJSON with calibration metrics (Brier, AUC-ROC), parameter sensitivity sweep, then 2–4 weeks paper trading before live. |
