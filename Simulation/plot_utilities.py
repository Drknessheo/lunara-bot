import matplotlib.pyplot as plt
import numpy as np
from typing import Union

def plot_metric_perturbation(x: np.ndarray, h_final: np.ndarray, t_final: float, filename: str = "metric_perturbation_plot.png"):
    """
    Plots the final metric perturbation h₀₀ versus the spatial coordinate.
    
    Parameters:
        x (ndarray): Spatial coordinate vector.
        h_final (ndarray): Final metric perturbation values.
        t_final (float): Final simulation time in seconds.
        filename (str): File name to save the plot.
    """
    plt.figure(figsize=(8, 6))
    plt.plot(x * 1e6, h_final, label=f't = {t_final * 1e9:.2f} ns')
    plt.xlabel('Position (micrometers)')
    plt.ylabel('Metric Perturbation (arbitrary units)')
    plt.title('Metric Perturbation h₀₀ at Final Time')
    plt.legend()
    plt.grid(True)
    plt.savefig(filename)
    plt.close()

def plot_clock_phase(t: np.ndarray, clock_phase: np.ndarray, filename: str = "clock_phase_plot.png"):
    """
    Plots the quantum clock phase evolution over time.
    
    Parameters:
        t (ndarray): Time vector in seconds.
        clock_phase (ndarray): Clock phase evolution data.
        filename (str): File name to save the plot.
    """
    plt.figure(figsize=(8, 6))
    plt.plot(t * 1e9, clock_phase, label="Quantum Clock Phase")
    plt.xlabel("Time (ns)")
    plt.ylabel("Phase (radians)")
    plt.title("Quantum Clock Phase Evolution")
    plt.legend()
    plt.grid(True)
    plt.savefig(filename)
    plt.close()
