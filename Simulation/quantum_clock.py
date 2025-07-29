# quantum_clock.py

import numpy as np

def run_quantum_clock_phase(h: np.ndarray, dt: float, x: np.ndarray, omega: float = 2 * np.pi * 1e9, x_clock: float = 0.0) -> np.ndarray:
    """
    Computes the phase evolution of a quantum clock in the simulated metric perturbation.

    Parameters:
        h (np.ndarray): 2D array of metric perturbations from the simulation.
        dt (float): Time step from the simulation.
        x (np.ndarray): Spatial coordinate vector from the simulation.
        omega (float): Angular frequency of the clock.
        x_clock (float): Spatial position of the clock.

    Returns:
        np.ndarray: Array storing the clock phase over time.
    """
    nt = h.shape[0]
    clock_phase = np.zeros(nt)

    # Find the index in x closest to the clock position.
    clock_index = np.abs(x - x_clock).argmin()

    # The proper time factor approximates the effect of h on timekeeping.
    for n in range(1, nt):
        proper_time_factor = 1 + h[n, clock_index] / 2.0
        clock_phase[n] = clock_phase[n-1] + omega * dt * proper_time_factor

    return clock_phase
