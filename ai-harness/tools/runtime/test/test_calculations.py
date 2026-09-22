"""Small real-library checks, not an assertion of Linux/runtime acceptance."""
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp
import sympy as sp


def test_linear_system_residual():
    matrix = np.array([[3., 1.], [1., 2.]])
    rhs = np.array([9., 8.])
    solution = np.linalg.solve(matrix, rhs)
    np.testing.assert_allclose(solution, [2., 3.])
    assert np.linalg.norm(matrix @ solution - rhs) < 1e-12


def test_rc_decay_analytic_and_numerical():
    # R=1000 ohm, C=1 microfarad -> tau=1 millisecond.
    tau_seconds = 1000 * 1e-6
    solution = solve_ivp(lambda _t, v: -v / tau_seconds, (0, tau_seconds), [5.],
                         rtol=1e-9, atol=1e-11)
    assert solution.success
    assert abs(solution.y[0, -1] - 5 / math.e) < 1e-8


def test_symbolic_derivative_and_plot_file(tmp_path):
    t, tau = sp.symbols("t tau", positive=True)
    voltage = 5 * sp.exp(-t / tau)
    assert sp.simplify(sp.diff(voltage, t) + voltage / tau) == 0
    x = np.linspace(0, 5, 101)
    fig, ax = plt.subplots()
    ax.plot(x, 5 * np.exp(-x))
    ax.set(xlabel="Time / tau", ylabel="Voltage (V)")
    output = tmp_path / "rc-decay.png"
    fig.savefig(output)
    plt.close(fig)
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output.stat().st_size > 1000
