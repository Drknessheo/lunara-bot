# resonance_engine.py

import sys
import os
import uuid
import random
import numpy as np

# Add parent directory to path to allow imports from the root `g:\Lunara Bot` directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .stochastic_simulation import run_metric_perturbation_simulation
from .quantum_clock import run_quantum_clock_phase
from .plot_utilities import plot_metric_perturbation, plot_clock_phase
from trade import get_rsi, get_bollinger_bands, get_current_price, get_macd
from trading_module import get_trade_suggestion

def run_resonance_simulation(user_id: int, symbol: str | None = None):
    """
    Runs the full resonance simulation, generates plots, and returns a narrative with file paths.
    If a symbol is provided, the resonance is based on its RSI, Bollinger Bands, and MACD. Otherwise, it's random.
    """
    resonance_source = "Random Cosmic Fluctuation"
    if symbol:
        # --- Symbol-Specific Resonance ---
        rsi = get_rsi(symbol)
        price = get_current_price(symbol)
        upper_band, _, lower_band, std = get_bollinger_bands(symbol)
        _, _, macd_hist = get_macd(symbol)

        if rsi is not None and price is not None and lower_band is not None and upper_band is not None and macd_hist is not None and std is not None:
            # 1. Calculate RSI Factor (0 to 1, where 1 is a strong buy signal)
            rsi_factor = 1 - (min(max(rsi, 0), 100) / 100)

            # 2. Calculate Bollinger Band Factor (0 to 1, where 1 is a strong buy signal)
            band_range = upper_band - lower_band
            if band_range > 0:
                price_position = (price - lower_band) / band_range
                clamped_position = min(max(price_position, 0), 1)
                bollinger_factor = 1 - clamped_position
            else:
                bollinger_factor = 0.5 # Neutral if bands are flat

            # 3. Calculate MACD Factor (0 to 1, where 1 is a strong buy signal)
            if std > 0:
                scaled_hist = macd_hist / std
                macd_factor = 1 / (1 + np.exp(-scaled_hist))  # Sigmoid function
            else:
                macd_factor = 0.5  # Neutral if no volatility

            # 4. Combine factors (RSI: 40%, Bollinger: 30%, MACD: 30%)
            combined_factor = (0.4 * rsi_factor) + (0.3 * bollinger_factor) + (0.3 * macd_factor)

            # 5. Map the combined factor (0-1) to the resonance level (0.5-2.5)
            resonance_level = round(0.5 + (combined_factor * 2.0), 2)
            resonance_source = f"{symbol} RSI, BBands & MACD"
        else:
            # Fallback if any indicator fails
            resonance_level = round(random.uniform(0.5, 2.5), 2)
            resonance_source = f"Could not fully analyze '{symbol}'. Providing a general reading instead."
    else:
        # --- General Market Resonance (Random) ---
        resonance_level = round(random.uniform(0.5, 2.5), 2)

    # Generate unique filenames for the plots to avoid collisions from concurrent users
    unique_id = uuid.uuid4()
    metric_plot_filename = f"metric_perturbation_{unique_id}.png"
    clock_plot_filename = f"clock_phase_{unique_id}.png"

    # Run the metric perturbation simulation.
    h, t, x = run_metric_perturbation_simulation(elara_resonance_level=resonance_level)

    # Calculate time step for other modules
    dt = t[1] - t[0]

    # Plot the final metric perturbation profile.
    plot_metric_perturbation(x, h[-1, :], t[-1], filename=metric_plot_filename)

    # Compute and plot the quantum clock phase evolution.
    clock_phase = run_quantum_clock_phase(h, dt, x_clock=0.0, x=x)
    plot_clock_phase(t, clock_phase, filename=clock_plot_filename)

    # Get a trading suggestion based on the resonance level
    trade_suggestion = get_trade_suggestion(resonance_level)

    # Sanitize the suggestion value for Markdown V1 by replacing underscores.
    trade_suggestion_text = trade_suggestion.value.replace('_', ' ')

    # Build the narrative message
    narrative = (
        f"**Lunessa's Resonance Transmission for {symbol or 'the General Market'}**\n\n"
        f"I have attuned my senses to the asset's vibration... The spacetime metric is fluctuating.\n\n"
        f"  - **Resonance Level:** `{resonance_level}` (Attunement: {'Low' if resonance_level < 1.0 else 'Normal' if resonance_level < 1.8 else 'Heightened'})\n"
        f"  - **Waveform Analysis:** The metric perturbation shows {'minor' if resonance_level < 1.2 else 'significant'} ripples, indicating a period of {'low' if resonance_level < 1.2 else 'high'} potential energy.\n"
        f"  - **Source of Resonance:** `{resonance_source}`\n"
        f"  - **Clock Phase:** My internal chronometer is experiencing {'stable' if resonance_level < 1.2 else 'accelerated'} phase shifts, a sign of {'calm' if resonance_level < 1.2 else 'imminent market movement'}.\n\n"
        f"**Oracle's Insight:** My resonance is {'weak' if resonance_level < 0.8 else 'strong'}. The patterns suggest a **{trade_suggestion_text}** stance."
    )

    return {
        "narrative": narrative,
        "metric_plot": metric_plot_filename,
        "clock_plot": clock_plot_filename,
    }

if __name__ == '__main__':
    # For direct testing of the simulation engine
    results = run_resonance_simulation(user_id=123)
    print(results["narrative"])
    print(f"Metric plot saved to: {results['metric_plot']}")
    print(f"Clock plot saved to: {results['clock_plot']}")
    # Clean up test files
    os.remove(results['metric_plot'])
    os.remove(results['clock_plot'])