"""Quick smoke test: L=4, W in {1, 16, 30}, N=2000.

Expected: gamma_min grows monotonically with W (more disorder -> shorter xi).
At W=1 (weak disorder, ballistic regime) gamma_min tiny.
At W=30 (strongly localised) gamma_min ~ ln(W).
At W=16.5 (near critical) intermediate.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_validation import lyapunov_min

for W in [1.0, 8.0, 16.5, 30.0]:
    t0 = time.time()
    g, ge, d = lyapunov_min(L=4, W=W, N=2000, q=16, n_qr=8, seed=42)
    print(f"L=4 W={W:5.1f}  gamma_min={g:.4e}  err={ge:.2e}  xi={1/g:.3f}  Lambda={1/g/4:.3f}  t={time.time()-t0:.1f}s")
