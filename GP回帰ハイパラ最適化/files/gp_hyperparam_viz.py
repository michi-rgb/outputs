"""
ガウス過程回帰 (GPR: Gaussian Process Regression) の
ハイパーパラメータ最適化の可視化

カーネル: RBF (Radial Basis Function)
  k(x, x') = sigma_f^2 * exp(-(x - x')^2 / (2 * l^2))
観測ノイズ: sigma_n^2

最適化指標: 対数周辺尤度 (LML: Log Marginal Likelihood)
  log p(y|X, theta) = -1/2 y^T (K + sigma_n^2 I)^-1 y
                      -1/2 log|K + sigma_n^2 I| - n/2 log(2*pi)
"""
import numpy as np
from scipy.linalg import cholesky, cho_solve
from scipy.optimize import minimize
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import japanize_matplotlib, os

# matplotlib 3.10 では japanize_matplotlib の自動登録が効かない場合があるため手動登録
_font_path = os.path.join(os.path.dirname(japanize_matplotlib.__file__),
                          'fonts', 'ipaexg.ttf')
fm.fontManager.addfont(_font_path)

rng = np.random.default_rng(42)
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['font.family'] = 'IPAexGothic'

# ---------------------------------------------------------------
# 1. 観測データの生成(真の関数 + ノイズ)
# ---------------------------------------------------------------
def f_true(x):
    return np.sin(3 * x) + 0.5 * x

N = 15
X_train = np.sort(rng.uniform(-3, 3, N))
sigma_true = 0.2
y_train = f_true(X_train) + rng.normal(0, sigma_true, N)
X_test = np.linspace(-3.5, 3.5, 300)

# ---------------------------------------------------------------
# 2. GP の基本計算
# ---------------------------------------------------------------
def rbf(Xa, Xb, ell, sf2):
    d2 = (Xa[:, None] - Xb[None, :]) ** 2
    return sf2 * np.exp(-0.5 * d2 / ell**2)

def log_marginal_likelihood(ell, sf2, sn2, X, y):
    K = rbf(X, X, ell, sf2) + sn2 * np.eye(len(X))
    try:
        L = cholesky(K + 1e-10 * np.eye(len(X)), lower=True)
    except np.linalg.LinAlgError:
        return -np.inf
    alpha = cho_solve((L, True), y)
    lml = (-0.5 * y @ alpha
           - np.sum(np.log(np.diag(L)))
           - 0.5 * len(X) * np.log(2 * np.pi))
    return lml

def gp_predict(ell, sf2, sn2, X, y, Xs):
    K = rbf(X, X, ell, sf2) + sn2 * np.eye(len(X))
    L = cholesky(K + 1e-10 * np.eye(len(X)), lower=True)
    Ks = rbf(X, Xs, ell, sf2)
    alpha = cho_solve((L, True), y)
    mu = Ks.T @ alpha
    v = np.linalg.solve(L, Ks)
    var = sf2 - np.sum(v**2, axis=0)
    return mu, np.sqrt(np.maximum(var, 0))

# ---------------------------------------------------------------
# 3. LML 最大化によるハイパーパラメータ最適化(対数空間で最適化)
# ---------------------------------------------------------------
def neg_lml(log_theta):
    ell, sf2, sn2 = np.exp(log_theta)
    return -log_marginal_likelihood(ell, sf2, sn2, X_train, y_train)

best = None
for x0 in [np.log([1.0, 1.0, 0.1]), np.log([0.1, 1.0, 0.5]), np.log([3.0, 0.5, 0.01])]:
    res = minimize(neg_lml, x0, method='L-BFGS-B')
    if best is None or res.fun < best.fun:
        best = res

ell_opt, sf2_opt, sn2_opt = np.exp(best.x)
lml_opt = -best.fun
print(f"最適化結果: ell={ell_opt:.4f}, sigma_f^2={sf2_opt:.4f}, "
      f"sigma_n^2={sn2_opt:.4f} (sigma_n={np.sqrt(sn2_opt):.4f}), LML={lml_opt:.3f}")
print(f"(参考)真のノイズ標準偏差 sigma_n={sigma_true}")

# ---------------------------------------------------------------
# 図1: 各ハイパーパラメータと対数周辺尤度の関係(1次元断面)
# ---------------------------------------------------------------
fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))

grids = {
    'ell': np.logspace(-1.5, 1.0, 200),
    'sf2': np.logspace(-2, 1.5, 200),
    'sn2': np.logspace(-4, 0.5, 200),
}
labels = {
    'ell': r'長さスケール $\ell$',
    'sf2': r'信号分散 $\sigma_f^2$',
    'sn2': r'ノイズ分散 $\sigma_n^2$',
}
opts = {'ell': ell_opt, 'sf2': sf2_opt, 'sn2': sn2_opt}

for ax, key in zip(axes, grids):
    vals = []
    for v in grids[key]:
        p = {'ell': ell_opt, 'sf2': sf2_opt, 'sn2': sn2_opt}
        p[key] = v
        vals.append(log_marginal_likelihood(p['ell'], p['sf2'], p['sn2'],
                                            X_train, y_train))
    vals = np.array(vals)
    ax.plot(grids[key], vals, color='#1f77b4', lw=2)
    ax.axvline(opts[key], color='#d62728', ls='--', lw=1.5,
               label=f'最適値 = {opts[key]:.3f}')
    ax.scatter([opts[key]], [lml_opt], color='#d62728', zorder=5)
    ax.set_xscale('log')
    ax.set_xlabel(labels[key], fontsize=12)
    ax.set_ylabel('対数周辺尤度 LML', fontsize=11)
    ax.set_ylim(max(vals.min(), lml_opt - 60), lml_opt + 5)
    ax.legend(fontsize=10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

fig.suptitle('各ハイパーパラメータと対数周辺尤度の関係(他は最適値に固定した断面)',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('fig1_lml_1d_slices.png', dpi=150, bbox_inches='tight')
plt.close(fig)

# ---------------------------------------------------------------
# 図2: 長さスケール × ノイズ分散 の2次元 LML 等高線
# ---------------------------------------------------------------
ell_grid = np.logspace(-1.5, 1.0, 120)
sn2_grid = np.logspace(-4, 0.5, 120)
LML = np.zeros((len(sn2_grid), len(ell_grid)))
for i, sn2 in enumerate(sn2_grid):
    for j, ell in enumerate(ell_grid):
        LML[i, j] = log_marginal_likelihood(ell, sf2_opt, sn2, X_train, y_train)

fig, ax = plt.subplots(figsize=(8, 6))
levels = np.linspace(lml_opt - 40, lml_opt, 25)
cs = ax.contourf(ell_grid, sn2_grid, np.clip(LML, lml_opt - 40, None),
                 levels=levels, cmap='viridis')
ax.contour(ell_grid, sn2_grid, np.clip(LML, lml_opt - 40, None),
           levels=levels[::4], colors='white', linewidths=0.5, alpha=0.6)
ax.scatter([ell_opt], [sn2_opt], color='#d62728', marker='*', s=250,
           edgecolor='white', zorder=5, label='LML 最大点')
ax.set_xscale('log'); ax.set_yscale('log')
ax.set_xlabel(r'長さスケール $\ell$', fontsize=12)
ax.set_ylabel(r'ノイズ分散 $\sigma_n^2$', fontsize=12)
ax.set_title(r'対数周辺尤度の等高線($\sigma_f^2$ は最適値に固定)',
             fontsize=14, fontweight='bold')
fig.colorbar(cs, ax=ax, label='対数周辺尤度 LML')
ax.legend(fontsize=11)
plt.tight_layout()
plt.savefig('fig2_lml_2d_contour.png', dpi=150, bbox_inches='tight')
plt.close(fig)

# ---------------------------------------------------------------
# 図3: ハイパーパラメータごとの GP 回帰の入出力関係と観測点
#       (過適合 / 最適 / 過平滑 の3ケース比較)
# ---------------------------------------------------------------
cases = [
    (0.1, sf2_opt, 1e-4, '長さスケール小・ノイズ小\n(過適合ぎみ)'),
    (ell_opt, sf2_opt, sn2_opt, 'LML 最大の最適ハイパラ'),
    (3.0, sf2_opt, 0.5, '長さスケール大・ノイズ大\n(過平滑ぎみ)'),
]

fig, axes = plt.subplots(1, 3, figsize=(16, 4.6), sharey=True)
for ax, (ell, sf2, sn2, title) in zip(axes, cases):
    mu, sd = gp_predict(ell, sf2, sn2, X_train, y_train, X_test)
    lml = log_marginal_likelihood(ell, sf2, sn2, X_train, y_train)
    ax.plot(X_test, f_true(X_test), color='gray', ls=':', lw=1.5, label='真の関数')
    ax.fill_between(X_test, mu - 2 * sd, mu + 2 * sd,
                    color='#1f77b4', alpha=0.25, label='予測 ±2σ(95%信頼区間)')
    ax.plot(X_test, mu, color='#1f77b4', lw=2, label='予測平均')
    ax.scatter(X_train, y_train, color='#d62728', s=45, zorder=5,
               edgecolor='white', label='観測点')
    ax.set_title(f'{title}\n'
                 + rf'$\ell$={ell:.2f}, $\sigma_n^2$={sn2:.4f}, LML={lml:.1f}',
                 fontsize=11)
    ax.set_xlabel('入力 x', fontsize=11)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
axes[0].set_ylabel('出力 y', fontsize=11)
axes[0].legend(fontsize=9, loc='upper left')
fig.suptitle('ハイパーパラメータの違いによるガウス過程回帰の予測の変化',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('fig3_gp_fits.png', dpi=150, bbox_inches='tight')
plt.close(fig)

print('図の保存が完了しました')
