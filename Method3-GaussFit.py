from tkinter import filedialog as fd
import pandas as pd
import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse
from skimage import exposure

from scipy.signal import medfilt

# from scipy.ndimage import gaussian_filter
from skimage.feature import blob_dog, blob_log
from lmfit.models import Gaussian2dModel
from tifffile import imread
from rich.progress import track

####################################
# Parameters
# Denoise
med_size = 3  # pixels
# Gauss_size = 2  # pixels
# DoG detector
blob_LoG_threshold = 0.0005
max_sig = 2
# Gauss Fit
crop_size = 3  # pixels, half size of crop for Gauss fit
chisqr_threshold = 150  # Goodness of fit
Nsigma = 3  # boundary will be Nsigma * sigmax/y, use 2.355 for FWHM

rescale_contrast = True
plow = 0.05  # imshow intensity percentile
phigh = 95

# lst_tifs = list(fd.askopenfilenames())
lst_tifs = [
    "/Volumes/AnalysisGG/PROCESSED_DATA/JPCB-CondensateBoundaryDetection/Real-Data/forFig3-small.tif"
]

####################################
# Main
for fpath in track(lst_tifs):
    img = imread(fpath)
    img_denoised = medfilt(img, med_size)
    # img_denoised = gaussian_filter(img, sigma=Gauss_size)

    blobs = blob_log(
        img_denoised, threshold=blob_LoG_threshold, exclude_border=3, max_sigma=max_sig
    )

    # make local crops around
    lst_GaussCrop = []
    for initial_x, initial_y, initial_sigma in blobs:
        GaussCrop = img_denoised[
            int(initial_x) - crop_size : int(initial_x) + crop_size + 1,
            int(initial_y) - crop_size : int(initial_y) + crop_size + 1,
        ]
        if GaussCrop.size > 0:
            # This mean a large blob is NOT near boundary and a full crop CAN be obtained
            lst_GaussCrop.append(GaussCrop)

    # Gauss Fit
    centerx = []
    centery = []
    sigmax = []
    sigmay = []
    lst_chisqr = []
    fitx = []
    fity = []
    for GaussCrop, blob in zip(lst_GaussCrop, blobs):
        initial_x, initial_y, initial_sigma = blob
        GaussCrop = GaussCrop - GaussCrop.min()
        # call lmfit model
        model = Gaussian2dModel()
        # vectorize image
        xx, yy = np.meshgrid(
            np.arange(GaussCrop.shape[0]), np.arange(GaussCrop.shape[1])
        )
        vev_x = np.reshape(xx, -1)
        vev_y = np.reshape(yy, -1)
        vec_img = np.reshape(GaussCrop, -1)
        # fit with lmfit
        params = model.guess(vec_img, vev_x, vev_y)
        params["centerx"].set(min=0.5 * crop_size, max=1.5 * crop_size)
        params["centery"].set(min=0.5 * crop_size, max=1.5 * crop_size)
        params["sigmax"].set(min=0, max=1.5 * initial_sigma)
        params["sigmay"].set(min=0, max=1.5 * initial_sigma)
        weights = 1 / np.sqrt(vec_img + 1)
        result = model.fit(vec_img, x=vev_x, y=vev_y, params=params, weights=weights)
        # result = model.fit(vec_img, x=vev_x, y=vev_y, params=params)

        lst_chisqr.append(result.chisqr)
        fitx.append(result.best_values["centerx"] + initial_x - crop_size)
        fity.append(result.best_values["centery"] + initial_y - crop_size)
        if result.chisqr < chisqr_threshold:
            # if False:
            centerx.append(result.best_values["centerx"] + initial_x - crop_size)
            centery.append(result.best_values["centery"] + initial_y - crop_size)
            sigmax.append(result.best_values["sigmax"])
            sigmay.append(result.best_values["sigmay"])
        else:
            centerx.append(initial_x)
            centery.append(initial_y)
            # centerx.append(result.best_values["centerx"] + initial_x - crop_size)
            # centery.append(result.best_values["centery"] + initial_y - crop_size)
            sigmax.append(initial_sigma)
            sigmay.append(initial_sigma)

    df_result = pd.DataFrame(
        {
            "centerx": centerx,
            "centery": centery,
            "sigmax": sigmax,
            "sigmay": sigmay,
            "chisqr": lst_chisqr,
            "fitx": fitx,
            "fity": fity,
        },
        dtype=float,
    )
    fpath_save = fpath[:-4] + "_GaussFit.csv"
    df_result.to_csv(fpath_save, index=False)

    fig, ax = plt.subplots()
    if rescale_contrast:
        # Contrast stretching
        p1, p2 = np.percentile(img, (plow, phigh))
        img_rescale = exposure.rescale_intensity(img, in_range=(p1, p2))
        ax.imshow(img_rescale, cmap="gray")
    else:
        ax.imshow(img, cmap="gray")

    for _, row in df_result.iterrows():
        x, y, sigmax, sigmay, _, _, _ = row
        condensate = Ellipse(
            (y, x),
            Nsigma * sigmax,
            Nsigma * sigmay,
            color="firebrick",
            fill=False,
            lw=2,
        )  # plot as FWHM
        ax.add_patch(condensate)

    plt.xlim(0, img_denoised.shape[0])
    plt.ylim(0, img_denoised.shape[1])
    plt.tight_layout()
    plt.axis("scaled")
    plt.axis("off")
    fpath_save = fpath[:-4] + "_GaussFit.png"
    plt.savefig(fpath_save, format="png", bbox_inches="tight", dpi=300)
