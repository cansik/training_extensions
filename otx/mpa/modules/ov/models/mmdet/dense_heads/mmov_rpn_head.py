# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from copy import deepcopy
from typing import Dict, List, Optional, Union

import torch
from mmdet.models.builder import HEADS
from mmdet.models.dense_heads.rpn_head import RPNHead

from otx.mpa.utils.logger import get_logger

from ...mmov_model import MMOVModel

logger = get_logger()


@HEADS.register_module()
class MMOVRPNHead(RPNHead):
    def __init__(
        self,
        model_path: str,
        weight_path: Optional[str] = None,
        inputs: Optional[Union[Dict[str, Union[str, List[str]]], List[str], str]] = None,
        outputs: Optional[Union[Dict[str, Union[str, List[str]]], List[str], str]] = None,
        init_weight: bool = False,
        verify_shape: bool = True,
        transpose_cls: bool = False,
        transpose_reg: bool = False,
        *args,
        **kwargs,
    ):
        self._model_path = model_path
        self._weight_path = weight_path
        self._inputs = deepcopy(inputs)
        self._outputs = deepcopy(outputs)
        self._init_weight = init_weight
        self._verify_shape = verify_shape
        self._transpose_cls = transpose_cls
        self._transpose_reg = transpose_reg

        # dummy input
        in_channels = 1
        super().__init__(in_channels=in_channels, *args, **kwargs)

    def _init_layers(self):
        self.model = MMOVModel(
            self._model_path,
            self._weight_path,
            inputs=self._inputs,
            outputs=self._outputs,
            remove_normalize=False,
            merge_bn=False,
            paired_bn=False,
            verify_shape=self._verify_shape,
            init_weight=self._init_weight,
        )

    def init_weights(self):
        # TODO
        pass

    def forward_single(self, x):
        rpn_cls_score, rpn_bbox_pred = self.model(x)

        if self._transpose_reg:
            # [B, 4 * num_anchors, H, W] -> [B, num_anchors * 4, H, W]
            shape = rpn_bbox_pred.shape
            rpn_bbox_pred = rpn_bbox_pred.reshape(shape[0], 4, -1, *shape[2:]).transpose(1, 2).reshape(shape)

        if self._transpose_cls:
            # [B, 2 * num_anchors, H, W] -> [B, num_anchors * 2, H, W]
            shape = rpn_cls_score.shape
            rpn_cls_score = rpn_cls_score.reshape(shape[0], 2, -1, *shape[2:]).transpose(1, 2).reshape(shape)

        # We set FG labels to [0, num_class-1] and BG label to
        # num_class in RPN head since mmdet v2.5, which is unified to
        # be consistent with other head since mmdet v2.0. In mmdet v2.0
        # to v2.4 we keep BG label as 0 and FG label as 1 in rpn head.
        bg = rpn_cls_score[:, 0::2]
        fg = rpn_cls_score[:, 1::2]
        rpn_cls_score = torch.flatten(torch.stack([fg, bg], dim=2), 1, 2)

        return rpn_cls_score, rpn_bbox_pred