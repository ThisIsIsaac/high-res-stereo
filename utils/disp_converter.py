import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib import colors
from colorspacious import cspace_converter
import numpy as np
import cv2

# input: unnormalized INT16
def clean_disp(disp):
    max_value = np.iinfo(disp.dtype).max

    disp[disp==np.NINF] = max_value
    disp[disp==np.inf] = max_value
    norm = plt.Normalize()

    return norm(disp)

# Todo: the contrast is too low. Tried multiplying by constant (before & after normalization) but doesn't change anything\
def convert_to_colormap(x):
    x = clean_disp(x)
    rgb = cm.get_cmap("plasma")(x)[:, :, :3]
    lab = cspace_converter("sRGB1", "CAM02-UCS")(rgb)

    return lab
