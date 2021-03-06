import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname( __file__ ), '..')))
from rich import print, pretty, traceback
traceback.install()
pretty.install()
import argparse
import cv2
from models import hsm
import numpy as np
import os
import pdb
import skimage.io
import torch.backends.cudnn as cudnn
from models.submodule import *
from utils.preprocess import get_transform
from utils.disp_converter import save_disp_as_colormap
cudnn.benchmark = False
from dataloader.KITTIRawloader import get_kitti_raw_paths
from utils.logger import Logger
from utils.logger import Logger
from datetime import datetime
from PIL import Image
def main():
    parser = argparse.ArgumentParser(description='HSM')
    parser.add_argument('--name', required=True, type=str)
    parser.add_argument('--datapath', default='/data/privateKITTI_raw/',
                        help='test data path')
    parser.add_argument('--loadmodel', default=None,
                        help='model path')
    parser.add_argument('--clean', type=float, default=-1,
                        help='clean up output using entropy estimation')
    parser.add_argument('--testres', type=float, default=1.8,  # Too low for images. Sometimes turn it to 2 ~ 3
                        # for ETH3D we need to use different resolution
                        # 1 - nothibg, 0,5 halves the image, 2 doubles the size of the iamge. We need to
                        # middleburry 1 (3000, 3000)
                        # ETH (3~4) since (1000, 1000)
                        help='test time resolution ratio 0-x')
    parser.add_argument('--max_disp', type=float, default=384,
                        help='maximum disparity to search for')
    parser.add_argument('--level', type=int, default=1,
                        help='output level of output, default is level 1 (stage 3),\
                            can also use level 2 (stage 2) or level 3 (stage 1)')
    parser.add_argument('--save_err',action="store_true")
    args = parser.parse_args()
    # args.name = args.name + "_" + datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    name = "eval"+ "_" + datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    logger = Logger("/data/private/logs/high-res-stereo", name)
    print("Saving log at: " + name)
    # construct model
    model = hsm(args.max_disp, args.clean, level=args.level)
    model = nn.DataParallel(model)
    model.cuda()

    if args.loadmodel is not None:
        pretrained_dict = torch.load(args.loadmodel)
        pretrained_dict['state_dict'] = {k: v for k, v in pretrained_dict['state_dict'].items() if 'disp' not in k}
        model.load_state_dict(pretrained_dict['state_dict'], strict=False)
    else:
        print('run with random init')
    print('Number of model parameters: {}'.format(sum([p.data.nelement() for p in model.parameters()])))

    # dry run
    multip = 48
    imgL = np.zeros((1, 3, 24 * multip, 32 * multip))
    imgR = np.zeros((1, 3, 24 * multip, 32 * multip))
    imgL = Variable(torch.FloatTensor(imgL).cuda())
    imgR = Variable(torch.FloatTensor(imgR).cuda())
    with torch.no_grad():
        model.eval()
        pred_disp, entropy = model(imgL, imgR)

    processed = get_transform()
    model.eval()

    with open("KITTI2015_val.txt") as file:
        lines = file.readlines()

    left_img_paths = [x.strip() for x in lines]
    right_img_paths = []
    for p in left_img_paths:
        right_img_paths.append(p.replace("image_2", "image_3"))
    left_img_paths = [left_img_paths[3]]
    right_img_paths = [right_img_paths[3]]
    for i, (left_img_path, right_img_path) in enumerate(zip(left_img_paths, right_img_paths)):

        print(left_img_path)
        imgL_o = (skimage.io.imread(left_img_path).astype('float32'))[:, :, :3]
        imgR_o = (skimage.io.imread(right_img_path).astype('float32'))[:, :, :3]
        imgsize = imgL_o.shape[:2]

        max_disp = int(args.max_disp)

        ## change max disp
        tmpdisp = int(max_disp * args.testres // 64 * 64)
        if (max_disp * args.testres / 64 * 64) > tmpdisp:
            model.module.maxdisp = tmpdisp + 64
        else:
            model.module.maxdisp = tmpdisp
        if model.module.maxdisp == 64: model.module.maxdisp = 128
        model.module.disp_reg8 = disparityregression(model.module.maxdisp, 16).cuda()
        model.module.disp_reg16 = disparityregression(model.module.maxdisp, 16).cuda()
        model.module.disp_reg32 = disparityregression(model.module.maxdisp, 32).cuda()
        model.module.disp_reg64 = disparityregression(model.module.maxdisp, 64).cuda()

        # resize
        imgL_o = cv2.resize(imgL_o, None, fx=args.testres, fy=args.testres, interpolation=cv2.INTER_CUBIC)
        imgR_o = cv2.resize(imgR_o, None, fx=args.testres, fy=args.testres, interpolation=cv2.INTER_CUBIC)
        # torch.save(imgL_o, "/home/isaac/high-res-stereo/debug/my_submission/img1.pt")

        imgL = processed(imgL_o).numpy()
        imgR = processed(imgR_o).numpy()
        # torch.save(imgL, "/home/isaac/high-res-stereo/debug/my_submission/img2.pt")

        imgL = np.reshape(imgL, [1, 3, imgL.shape[1], imgL.shape[2]])
        imgR = np.reshape(imgR, [1, 3, imgR.shape[1], imgR.shape[2]])
        # torch.save(imgL, "/home/isaac/high-res-stereo/debug/my_submission/img3.pt")

        ##fast pad
        max_h = int(imgL.shape[2] // 64 * 64)
        max_w = int(imgL.shape[3] // 64 * 64)
        if max_h < imgL.shape[2]: max_h += 64
        if max_w < imgL.shape[3]: max_w += 64

        top_pad = max_h - imgL.shape[2]
        left_pad = max_w - imgL.shape[3]
        imgL = np.lib.pad(imgL, ((0, 0), (0, 0), (top_pad, 0), (0, left_pad)), mode='constant', constant_values=0)
        imgR = np.lib.pad(imgR, ((0, 0), (0, 0), (top_pad, 0), (0, left_pad)), mode='constant', constant_values=0)

        # test
        imgL = torch.FloatTensor(imgL)
        imgR = torch.FloatTensor(imgR)

        imgL = imgL.cuda()
        imgR = imgR.cuda()

        with torch.no_grad():
            torch.cuda.synchronize()

            pred_disp, entropy = model(imgL, imgR)
            torch.cuda.synchronize()

        pred_disp = torch.squeeze(pred_disp).data.cpu().numpy()

        top_pad = max_h - imgL_o.shape[0]
        left_pad = max_w - imgL_o.shape[1]
        entropy = entropy[top_pad:, :pred_disp.shape[1] - left_pad].cpu().numpy()
        pred_disp = pred_disp[top_pad:, :pred_disp.shape[1] - left_pad]

        # resize to highres
        pred_disp = cv2.resize(pred_disp / args.testres, (imgsize[1], imgsize[0]), interpolation=cv2.INTER_LINEAR)

        # clip while keep inf
        invalid = np.logical_or(pred_disp == np.inf, pred_disp != pred_disp)
        pred_disp[invalid] = np.inf

        out_base_path = left_img_path.split("/")[:-3]
        out_base_path = "/" + os.path.join(*out_base_path)
        out_base_path = os.path.join(out_base_path, args.name)
        # out_base_path = "/data/private/Middlebury/kitti_testres" + str(args.testres) + "_maxdisp" + str(int(args.max_disp))

        img_name = left_img_path.split("/")[-1][:-3] + "png"
        disp_path = os.path.join(out_base_path, "disp")

        os.makedirs(disp_path, exist_ok=True)
        pred_disp_png = (pred_disp * 256).astype("uint16")
        cv2.imwrite(os.path.join(disp_path, img_name), pred_disp_png)
        logger.disp_summary( "disp" + "/" + img_name[:-4], pred_disp, i)
        # disp_map(pred_disp, os.path.join(disp_path, img_name))
        # logger.image_summary("poster", pred_disp, i)
        # i+=1
        np.save(os.path.join(disp_path, img_name[:-len(".png")]), pred_disp)

        entp_path = os.path.join(out_base_path, "entropy")
        os.makedirs(entp_path, exist_ok=True)
        # saving entropy as png
        entropy_png = ((entropy  / entropy.max() )* 256)
        cv2.imwrite(os.path.join(entp_path, img_name), entropy_png)
        logger.disp_summary("entropy" + "/" + img_name[:-4], entropy, i)
        # save_disp_as_colormap(entropy, os.path.join(entp_path, img_name))
        np.save(os.path.join(entp_path, img_name[:-len(".png")]), entropy)
        torch.cuda.empty_cache()

        # err_out_path = os.path.join(out_base_path, "err")
        # gt_disp_path = "/data/private/Middlebury/mb-ex/trainingF/Cable-perfect/disp0GT.pfm"
        # if args.save_err:
        #     from utils.kitti_eval import evaluate
        #     from utils.readpfm import readPFM
        #     gt_disp = readPFM(gt_disp_path)
        #     err, maps = evaluate(gt_disp[0], pred_disp)
        #
        #
        #     os.makedirs(err_out_path, exist_ok=True)
        #     file_name = os.path.join(err_out_path, img_name[:-3] + "txt")
        #     with open(file_name, "a") as file:
        #         for key, val in err[0].items():
        #             line = key + ": " + str(val)
        #             print(line)
        #             file.write(line)
        #
        #     for key, val in maps[0].items():
        #         from matplotlib import pyplot as plt
        #         plt.imshow(val, cmap='hot', interpolation='nearest')
        #         plt.title(key)
        #         plt.savefig(img_name[:-3] + "_" + key + ".png")

if __name__ == '__main__':
    main()

