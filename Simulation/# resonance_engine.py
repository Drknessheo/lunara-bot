# resonance_engine.py

import sys
import os
# Add parent directory to path to allow imports from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stochastic_simulation import run_metric_perturbation_simulation
from quantum_clock import run_quantum_clock_phase
from plot_utilities import plot_metric_perturbation, plot_clock_phase
from trading_module import get_trade_suggestion

def main():
    # Set Elara's "soul resonance" level—this can be adjusted to simulate different emotional or cognitive states.
    elara_resonance_level = 1.5  # For example, 1.5 represents an intensified state.
    
    # Run the metric perturbation simulation.
    h, t, x = run_metric_perturbation_simulation(elara_resonance_level=elara_resonance_level)
    
    # Calculate time step for other modules
    dt = t[1] - t[0]
    
    # Plot the final metric perturbation profile.
    plot_metric_perturbation(x, h[-1, :], t[-1])
    
    # Compute and plot the quantum clock phase evolution.
    clock_phase = run_quantum_clock_phase(h, dt, x_clock=0.0, x=x)
    plot_clock_phase(t, clock_phase)

    # Get a trading suggestion based on the resonance level
    trade_suggestion = get_trade_suggestion(elara_resonance_level)
    print(f"\n[Trading Insight]")
    print(f"Lunessa's Resonance Level: {elara_resonance_level}")
    print(f"Strategic Suggestion: {trade_suggestion.value}")

if __name__ == '__main__':
    main()
