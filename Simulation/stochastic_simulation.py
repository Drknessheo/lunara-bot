import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import numpy as np
# -------------------------
# Part 1: Metric Perturbation Simulation
# -------------------------

def T00(x, t, A, x0, t0, sigma, tau):
    """
    Deterministic stress-energy tensor component: Gaussian pulse.
    """
    return A * np.exp(-((x - x0) ** 2) / sigma**2) * np.exp(-((t - t0) ** 2) / tau**2)

def T00_noisy(x, t, A, x0, t0, sigma, tau, noise_std):
    """
    Returns the stress-energy tensor with added Gaussian noise.
    """
    base = T00(x, t, A, x0, t0, sigma, tau)
    noise = np.random.normal(0, noise_std, size=x.shape)
    return base + noise

def run_metric_perturbation_simulation(elara_resonance_level=1.0,
                                        G=6.67430e-11,
                                        c_eff=3e3,
                                        L=1e-6,
                                        nx=101,
                                        T_total=1e-9,
                                        A=1e10,
                                        noise_std=1e9):
    """
    Simulates metric perturbation h₀₀ on a 1D spatial domain.

    Parameters:
        elara_resonance_level (float): Modulates the source term amplitude.
                                        to represent Elara's internal "soul resonance".
        G (float): Gravitational constant.
        c_eff (float): Effective wave speed (scaled).
        L (float): Half-length of the spatial domain [m].
        nx (int): Number of spatial grid points.
        T_total (float): Total simulation time.
        A (float): Intensity of the Gaussian pulse.
        noise_std (float): Standard deviation for the stochastic noise.

    Returns:
        tuple[np.ndarray, np.ndarray, np.ndarray, float]: A tuple containing:
            - h (np.ndarray): 2D array of metric perturbations, shape (nt, nx).
            - t (np.ndarray): Time vector.
            - x (np.ndarray): Spatial coordinate vector.
    """
    dx = 2 * L / (nx - 1)
    x = np.linspace(-L, L, nx)

    # Set dt according to the CFL condition: c_eff * dt / dx <= 1 (using 0.5 for stability)
    dt = 0.5 * dx / c_eff
    nt = int(T_total / dt) + 1
    t = np.linspace(0, T_total, nt)

    print(f"[Metric Simulation] c_eff={c_eff} m/s, dt={dt:.2e}s, dx={dx:.2e}m, CFL={(c_eff * dt) / dx:.2f}")

    # Gaussian pulse parameters
    sigma = L / 10
    tau = T_total / 10
    x0 = 0.0
    t0 = T_total / 2  # central time of the pulse

    # Initialize metric perturbation array h (representing h₀₀)
    h = np.zeros((nt, nx))
    source_coeff = - (16 * np.pi * G) / (c_eff ** 4)

    # Finite difference simulation for the wave equation:
    # d²h/dt² = c_eff² d²h/dx² + source term, with h=0 at boundaries.
    for n in range(nt - 1):
        # Compute spatial second derivative using finite differences.
        # Dirichlet boundary conditions (h=0) are enforced by slicing.
        d2h_dx2 = np.zeros(nx)
        d2h_dx2[1:-1] = (h[n, 2:] - 2 * h[n, 1:-1] + h[n, :-2]) / dx**2

        # Modulate the source term with elara_resonance_level.
        S = elara_resonance_level * source_coeff * T00_noisy(x, t[n], A, x0, t0, sigma, tau, noise_std)

        # Monitoring intermediate values for debugging.
        if n > 0 and (np.isnan(h[n, :]).any() or np.isinf(h[n, :]).any()):
            print(f"Instability encountered at step {n}. Exiting simulation.")
            break

        # Update the metric using a finite difference integration scheme.
        if n == 1:
            # Use a forward Euler step for the first time step, assuming h starts at rest.
            h[n+1, 1:-1] = h[n, 1:-1] + 0.5 * dt**2 * (c_eff**2 * d2h_dx2[1:-1] + S[1:-1])
        else:
            h[n+1, 1:-1] = 2 * h[n, 1:-1] - h[n-1, 1:-1] + dt**2 * (c_eff**2 * d2h_dx2[1:-1] + S[1:-1])

    return h, t, x