import h5py
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap, Normalize
from scipy.sparse import coo_matrix
from ...tools.namespace import StandardVariableNames as svn
from ...tools.utils import FIGSIZE_DEFAULT
from sklearn.metrics import confusion_matrix

COLORS_MTBS = [
    (1, 1, 1, 0),  # 0: no data
    (0, 0.391, 0, 1),  # 1: unburnt to low
    (0.498, 1, 0.831, 1),  # 2: low
    (1, 1, 0, 1),  # 3: moderate
    (1, 0, 0, 1),  # 4: high
    (0.498, 1, 0.0039, 1),  # 5: increased greenness
]

LABELS_MTBS = [
    "0: no data",
    "1: unburnt to low",
    "2: low",
    "3: moderate",
    "4: high",
    "5: increased greenness",
]


def global_accuracy(
    filepath_eval: str,
    mtbs_group_path_eval: str,
    filepath_ref: str,
    mtbs_group_path_ref: str,
    figure_name: str = "mtbs_global_accuracy.png",
    fig_dpi: int = 150,
    ignore_greenness: bool = True,
):
    """
    Run the MTBS global accuracy analysis between two datasets.

    The evaluated dataset and the reference dataset are located (respectively) in
    filepath_1/mtbs_group_path_1 (filepath_2/mtbs_group_path_2).

    The mtbs group must contain the following datasets:
    - fire_burn_severity
    - latitude
    - longitude
    and the following attributes:
    - crs
    """
    # Import evaluated dataset
    with h5py.File(filepath_eval, "r") as h5:
        grp_1 = h5[mtbs_group_path_eval]
        lat_1 = grp_1[svn.LATITUDE.value][:, :]
        lon_1 = grp_1[svn.LONGITUDE.value][:, :]
        mtbs_1 = grp_1[svn.FIRE_BURN_SEVERITY.value][:, :]
        crs_1 = grp_1.attrs["crs"]

    # Import reference dataset
    with h5py.File(filepath_ref, "r") as h5:
        grp_2 = h5[mtbs_group_path_ref]
        lat_2 = grp_2[svn.LATITUDE.value][:, :]
        lon_2 = grp_2[svn.LONGITUDE.value][:, :]
        mtbs_2 = grp_2[svn.FIRE_BURN_SEVERITY.value][:, :]
        crs_2 = grp_2.attrs["crs"]

    # TODO: Projection eval -> ref
    # TODO: interpolation nearest

    # process greenness

    # compute confusion matrix
    # Flatten in case your labels are 2D rasters
    y_true = np.asarray(mtbs_2).ravel()
    y_pred = np.asarray(mtbs_1).ravel()

    # If you know your class list; otherwise infer:
    classes = np.unique(np.concatenate([y_true, y_pred]))
    K = classes.size

    # Map labels to 0..K-1 (robust if classes aren’t consecutive)
    to_idx = {c: i for i, c in enumerate(classes)}
    ti = np.vectorize(to_idx.get)(y_true)
    pi = np.vectorize(to_idx.get)(y_pred)

    # bincount trick
    cm = np.bincount(ti * K + pi, minlength=K * K).reshape(K, K)

    # calculate score
    M = 100 * cm / cm.sum(axis=1, keepdims=True).clip(min=1)
    accuracy_per_class_bps = np.zeros(5)
    accuracy_per_class_total = np.zeros(5)

    for k in range(K - 1):
        accuracy_per_class_bps[k] = cm[k + 1, k + 1] / np.sum(cm[k+1, 1:]) if np.sum(cm[k+1, 1:]) > 0 else 0.0
        accuracy_per_class_total[k] = cm[k + 1, k + 1] / (np.sum(cm[k+1, :]) + cm[0, k+1])

    print(accuracy_per_class_bps)
    print(accuracy_per_class_total)

    # or using add.at
    cm = np.zeros((K, K), dtype=int)
    np.add.at(cm, (ti, pi), 1)

    fig, axes = plt.subplots(2, 2, figsize=(5, 6), constrained_layout=True)
    ax1 = axes[0, 0]
    ax2 = axes[0, 1]
    ax3 = axes[1, 0]
    ax4 = axes[1, 1]

    # Build discrete colormap
    cmap = ListedColormap(COLORS_MTBS)
    bounds = np.arange(-0.5, 6.5, 1)
    norm = BoundaryNorm(bounds, cmap.N)

    # panel 2: Evaluated
    im1 = ax1.pcolormesh(lon_1, lat_1, mtbs_1, cmap=cmap, norm=norm, edgecolors="none")

    # panel 2: Reference
    im2 = ax2.pcolormesh(lon_2, lat_2, mtbs_2, cmap=cmap, norm=norm, edgecolors="none")

    # panel 3: Difference
    im3 = ax3.pcolormesh(
        lon_2, lat_2, mtbs_1 - mtbs_2, cmap="RdYlGn_r", norm=Normalize(vmin=-5, vmax=5), edgecolors="none"
    )

    # panel 4: confusion matrix
    im4 = ax4.imshow(M, cmap="Blues", origin="upper", interpolation="nearest")
    ax4.set_xlabel("Evaluated")
    ax4.set_ylabel("Reference")
    ax4.set_xticks(np.arange(K), labels=classes)
    ax4.set_yticks(np.arange(K), labels=classes)

    # Shared colorbar on top of the first row
    cbar = fig.colorbar(
        im1,
        ax=axes[0, :],  # span first row only
        orientation="horizontal",
        location="top",
        fraction=0.08,
        pad=0.05,  # control size/spacing
        ticks=range(6),
    )
    cbar.ax.set_xticklabels(LABELS_MTBS)
    cbar.ax.tick_params(axis="x", rotation=30)
    plt.setp(cbar.ax.get_xticklabels(), ha="left")
    cbar.set_label("MTBS classes", fontsize=10)

    cbar = fig.colorbar(
        im3,
        ax=ax3,
        orientation="horizontal",
        location="bottom",
        ticks=[-5, -2, 0, 2, 5],
        label="Difference [-]",
    )

    for i in range(K):
        for j in range(K):
            val = M[i, j]
            ax4.text(j, i, f"{val:3.0f}", ha="center", va="center", color="black", fontsize=7)

    ax1.text(0.02, 0.9, "Evaluated", fontsize=8, transform=ax1.transAxes)
    ax2.text(0.02, 0.9, "Reference", fontsize=8, transform=ax2.transAxes)
    ax4.text(1.03, 1.02, "BPS", fontsize=8, transform=ax4.transAxes)
    ax4.text(1.20, 1.02, "total", fontsize=8, transform=ax4.transAxes)
    for k in range(K - 1):
        ax4.text(
            1.03, 0.73 - 0.165 * k, f"{accuracy_per_class_bps[k]:.2f}", fontsize=7, transform=ax4.transAxes
        )
        ax4.text(
            1.20,
            0.73 - 0.165 * k,
            f"{accuracy_per_class_total[k]:.2f}",
            fontsize=7,
            transform=ax4.transAxes,
        )
    ax4.text(1.03, 0.01, "__________", fontsize=7, transform=ax4.transAxes)
    ax4.text(1.03, -0.1, f"{np.mean(accuracy_per_class_bps):.2f}", fontsize=7, transform=ax4.transAxes)
    ax4.text(1.20, -0.1, f"{np.mean(accuracy_per_class_total):.2f}", fontsize=7, transform=ax4.transAxes)

    cbar = fig.colorbar(
        im4,
        ax=ax4,
        orientation="horizontal",
        location="bottom",
    )
    cbar.set_label("Fraction")  # or "Proportion" if normalized

    fig.set_constrained_layout_pads(w_pad=0.02, h_pad=0.02, hspace=0.0, wspace=0.0)
    for ax in axes.ravel():
        ax.tick_params(direction="in", top=True, right=True, which="both")

    for ax in [ax1, ax2, ax3]:
        ax.set_xlabel("longitude [deg]")
        ax.set_ylabel("latitude [deg]")

    if not figure_name.endswith(".png"):
        figure_name += ".png"

    fig.savefig(figure_name, dpi=fig_dpi)

    return fig
